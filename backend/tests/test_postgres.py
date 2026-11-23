import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from monitoring import api
from monitoring.checker import Observation, claim_due, probe, record
from monitoring.db import session

ROOT = Path(__file__).resolve().parents[1]
START = datetime(2026, 1, 1, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def migrated_database():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")

    schema = f"monitor_tests_{uuid4().hex}"
    admin = create_engine(database_url)
    test_url = make_url(database_url).update_query_dict({"options": f"-csearch_path={schema}"})
    with admin.begin() as db:
        db.execute(text(f"CREATE SCHEMA {schema}"))
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT, check=True,
            env={**os.environ, "DATABASE_URL": test_url.render_as_string(hide_password=False)},
        )
        yield test_url
    finally:
        with admin.begin() as db:
            db.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.fixture
async def setup(migrated_database, monkeypatch):
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as db:
        await db.execute(text("TRUNCATE notifications, incidents, check_results, monitors RESTART IDENTITY"))

    async def provide_session():
        async with sessions() as db:
            yield db

    monkeypatch.setattr(api, "utcnow", lambda: START)
    monkeypatch.setenv("ALLOWED_MONITOR_HOSTS", "demo")
    api.app.dependency_overrides[session] = provide_session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
            yield client, sessions
    finally:
        api.app.dependency_overrides.clear()
        await engine.dispose()


async def create(client, **fields):
    payload = {
        "name": "Orders API", "url": "http://demo:8001/health",
        "interval_seconds": 5, "timeout_seconds": 2, **fields,
    }
    response = await client.post("/api/monitors", json=payload)
    assert response.status_code == 201, response.text
    return f"/api/monitors/{response.json()['id']}"


async def claim(sessions, elapsed):
    async with sessions() as db:
        jobs = await claim_due(db, START + timedelta(seconds=elapsed), 4, set())
    assert len(jobs) == 1
    return jobs[0]


async def save(sessions, job, status, milliseconds=20):
    start = job.scheduled_at
    reason = {None: "Request timed out.", 503: "Expected HTTP 200, received 503."}.get(status)
    observation = Observation(start, start + timedelta(milliseconds=milliseconds), milliseconds, status, reason)
    async with sessions() as db:
        saved = await record(db, job, observation)
    return saved, observation.finished_at


async def test_outage_replay_and_recovery(setup):
    client, sessions = setup
    path = await create(client)
    assert (await client.get(path)).json()["latest_check"] is None
    assert not (await client.get(path)).json()["overdue"]
    for index, status in enumerate([503, 503, 503, 503, 200, 503, 200, 200], 1):
        job = await claim(sessions, (index - 1) * 5)
        if index == 3:
            attempts = await asyncio.gather(save(sessions, job, status), save(sessions, job, status))
            assert sorted(saved for saved, _ in attempts) == [False, True]
            confirmed = attempts[0][1]
        else:
            _, finished = await save(sessions, job, status)
            if index == 1:
                first = finished
        monitor = (await client.get(path)).json()
        assert (monitor["open_incident"] is not None) == (3 <= index < 8)
        assert monitor["awaiting_recovery"] == (index in (5, 7))
        assert monitor["latest_check"]["http_status"] == status

    events = (await client.get("/api/notifications")).json()
    incidents = (await client.get(f"{path}/incidents")).json()
    assert len(incidents) == 1
    incident = incidents[0]
    assert [event["event_type"] for event in events] == ["recovery", "outage"]
    assert all(event["incident_id"] == incident["id"] for event in events)
    assert incident["first_failure_at"] == first.isoformat()
    assert incident["confirmed_at"] == confirmed.isoformat()
    assert incident["resolved_at"] == finished.isoformat()
    checks = (await client.get(f"{path}/checks", params={"to": (START + timedelta(hours=1)).isoformat()})).json()
    assert len(checks["items"]) == 8
    assert checks["items"][0]["scheduled_at"].endswith("+00:00")
    assert len((await client.get("/api/monitors")).json()) == 1


async def test_pause_during_probe_and_missed_slot(setup, monkeypatch):
    client, sessions = setup
    path = await create(client)
    for elapsed in (0, 5, 10):
        await save(sessions, await claim(sessions, elapsed), 503)
    await save(sessions, await claim(sessions, 15), 200)
    in_flight = await claim(sessions, 20)
    monkeypatch.setattr(api, "utcnow", lambda: START + timedelta(seconds=21))
    paused = (await client.patch(path, json={"enabled": False})).json()
    assert paused["open_incident"] and not paused["awaiting_recovery"]
    async with sessions() as db:
        assert await claim_due(db, START + timedelta(seconds=40), 4, set()) == []
    assert (await save(sessions, in_flight, 200))[0]

    monkeypatch.setattr(api, "utcnow", lambda: START + timedelta(seconds=40))
    resumed = (await client.patch(path, json={"enabled": True})).json()
    assert resumed["next_run_at"] == (START + timedelta(seconds=40)).isoformat()
    await save(sessions, await claim(sessions, 40), 200)
    assert (await client.get(path)).json()["awaiting_recovery"]
    assert (await client.get(path)).json()["latest_check"]["gap_before"]

    # The checker advanced the schedule and then shut down before recording the request.
    interrupted = await claim(sessions, 45)
    monkeypatch.setattr(api, "utcnow", lambda: START + timedelta(seconds=56))
    assert (await client.get(path)).json()["overdue"]
    current = await claim(sessions, 56)
    assert current.scheduled_at == interrupted.scheduled_at + timedelta(seconds=10)
    await save(sessions, current, 200)
    assert (await client.get(path)).json()["awaiting_recovery"]
    assert (await client.get(path)).json()["latest_check"]["gap_before"]
    await save(sessions, await claim(sessions, 60), 200)
    assert (await client.get(path)).json()["open_incident"] is None
    assert len((await client.get("/api/notifications")).json()) == 2


async def test_window_metrics_pagination_and_validation(setup):
    client, sessions = setup
    path = await create(client)
    for index, (status, elapsed) in enumerate([(200, 100), (200, 200), (503, 300), (None, 2000), (200, 500)]):
        await save(sessions, await claim(sessions, index * 5), status, elapsed)
    window = {"from": START.isoformat(), "to": (START + timedelta(seconds=20)).isoformat()}
    response = (await client.get(f"{path}/metrics", params=window)).json()
    assert response["availability_percent"] == 50
    assert response["mean_ms"] == 200
    assert response["p95_ms"] == 300
    assert [point["response_ms"] for point in response["points"]] == [100, 200, 300, None]
    history = (await client.get(f"{path}/checks", params={**window, "page_size": 2})).json()
    assert history["has_more"]
    assert [item["elapsed_ms"] for item in history["items"]] == [2000, 300]
    page_two = (await client.get(f"{path}/checks", params={**window, "page": 2, "page_size": 2})).json()
    assert not page_two["has_more"]
    assert [item["elapsed_ms"] for item in page_two["items"]] == [200, 100]
    assert (await client.get(f"{path}/incidents")).json() == []
    for endpoint in ("checks", "metrics"):
        assert (await client.get(f"{path}/{endpoint}", params={"from": window["to"], "to": window["to"]})).status_code == 422
        assert (await client.get(f"{path}/{endpoint}", params={"from": "2026-01-01T12:00:00"})).status_code == 422
        assert (await client.get(f"/api/monitors/999/{endpoint}")).status_code == 404
    assert (await client.get("/api/monitors/999")).status_code == 404

    invalid_fields = [
        ({"timeout_seconds": 5}, "timeout_seconds"), ({"interval_seconds": 4}, "interval_seconds"),
        ({"url": "http://elsewhere/health"}, "url"), ({"url": "http://user@demo:8001/health"}, "url"),
        ({"expected_status": 600}, "expected_status"), ({"name": " "}, "name"),
        ({"method": "CONNECT"}, "method"), ({"request_headers": {"Host": "other"}}, "request_headers"),
        ({"request_headers": {"X-Value": "first\r\nsecond"}}, "request_headers"),
        ({"request_headers": {"Accept": "a", "accept": "b"}}, "request_headers"),
        ({"request_body": "a\x00b"}, "request_body"),
    ]
    for change, field in invalid_fields:
        payload = {"name": "Valid", "url": "http://demo/health", "interval_seconds": 5, "timeout_seconds": 2, **change}
        rejected = await client.post("/api/monitors", json=payload)
        assert rejected.status_code == 422
        assert rejected.json()["detail"][0]["loc"] == ["body", field]

    nonfinite = await client.post(
        "/api/monitors", headers={"Content-Type": "application/json"},
        content='{"name":"Valid","url":"http://demo/health","timeout_seconds":1e900}',
    )
    assert nonfinite.status_code == 422
    assert nonfinite.json()["detail"][0]["loc"] == ["body", "timeout_seconds"]

    for payload in ({"name": None}, {"url": "http://demo/other"}, {"expected_status": 503}):
        assert (await client.patch(path, json=payload)).status_code == 422
    assert (await client.patch(path, json={"name": "Updated", "interval_seconds": 7, "timeout_seconds": 6})).status_code == 200


async def test_saved_request_reaches_probe_and_edits_start_a_new_generation(setup):
    client, sessions = setup
    path = await create(
        client, url="http://demo:8001/health?check=1", method="POST", expected_status=201,
        request_headers={"Content-Type": "application/json", "Authorization": "Bearer test-token"},
        request_body='{"text":"café"}',
    )
    monitor = (await client.get(path)).json()
    assert monitor["method"] == "POST"
    assert monitor["has_request_headers"] and monitor["has_request_body"]
    assert "request_headers" not in monitor and "request_body" not in monitor
    assert "test-token" not in (await client.get("/api/monitors")).text

    assert (await client.patch(path, json={"name": "Renamed"})).status_code == 200
    original = await claim(sessions, 0)

    def endpoint(request):
        assert request.method == "POST"
        assert request.url.params["check"] == "1"
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.headers["content-type"] == "application/json"
        assert request.headers["user-agent"].startswith("api-monitoring-dashboard/")
        assert request.content == '{"text":"café"}'.encode()
        return httpx.Response(201)

    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as target:
        observation = await probe(target, original)
    assert observation.http_status == 201 and observation.failure_reason is None

    updated = (await client.patch(path, json={
        "method": "HEAD", "request_headers": {}, "request_body": None,
    })).json()
    assert updated["method"] == "HEAD"
    assert not updated["has_request_headers"] and not updated["has_request_body"]
    async with sessions() as db:
        assert await record(db, original, observation)
    current = await claim(sessions, 5)
    assert current.generation == original.generation + 1
    assert current.method == "HEAD" and current.request_headers == {} and current.request_body is None
    await save(sessions, current, 201)
    latest = (await client.get(path)).json()["latest_check"]
    assert latest["success"] and latest["gap_before"]


@pytest.mark.skipif(os.getenv("RUN_LIVE_API_TESTS") != "1", reason="Live APIs are opt-in.")
@pytest.mark.parametrize("name,host,fields", [
    ("GitHub Markdown", "api.github.com", {
        "url": "https://api.github.com/markdown/raw", "method": "POST",
        "request_headers": {"Content-Type": "text/plain"},
        "request_body": "**API Monitoring Dashboard smoke test**",
    }),
    ("Google Public DNS", "dns.google", {
        "url": "https://dns.google/resolve?name=example.com&type=A", "method": "GET",
        "request_headers": {"Accept": "application/dns-json"},
    }),
])
async def test_live_api_check(setup, monkeypatch, name, host, fields):
    client, sessions = setup
    monkeypatch.setenv("ALLOWED_MONITOR_HOSTS", host)
    path = await create(client, name=name, interval_seconds=300, timeout_seconds=15, **fields)
    job = await claim(sessions, 0)
    async with httpx.AsyncClient(trust_env=False, timeout=None) as target:
        observation = await probe(target, job)
    assert observation.http_status == 200, observation
    async with sessions() as db:
        assert await record(db, job, observation)
    latest = (await client.get(path)).json()["latest_check"]
    assert latest["http_status"] == 200 and latest["success"]

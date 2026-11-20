import asyncio
import logging
import os
import signal
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import validate_target
from .db import Session, engine, utcnow
from .domain import Streak, next_streak, schedule_slot
from .models import CheckResult, Incident, Monitor, Notification

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    monitor_id: int
    url: str
    expected_status: int
    timeout_seconds: float
    scheduled_at: datetime
    generation: int
    missed_slot: bool


@dataclass(frozen=True)
class Observation:
    started_at: datetime
    finished_at: datetime
    elapsed_ms: int
    http_status: int | None
    failure_reason: str | None


async def claim_due(
    db: AsyncSession, now: datetime, capacity: int, active_ids: set[int]
) -> list[Job]:
    statement = (
        select(Monitor)
        .where(Monitor.enabled, Monitor.next_run_at <= now)
        .order_by(Monitor.next_run_at, Monitor.id)
        .limit(capacity)
        .with_for_update(skip_locked=True)
    )
    if active_ids:
        statement = statement.where(Monitor.id.not_in(active_ids))

    async with db.begin():
        jobs = []
        for monitor in await db.scalars(statement):
            due = monitor.next_run_at
            scheduled_at, monitor.next_run_at = schedule_slot(due, now, monitor.interval_seconds)
            missed_slot = scheduled_at != due or monitor.awaiting_since is not None
            monitor.awaiting_since = monitor.awaiting_since or due
            if missed_slot:
                monitor.failure_streak = monitor.recovery_streak = 0
                monitor.first_failure_at = None
            jobs.append(Job(
                monitor.id, monitor.url, monitor.expected_status, monitor.timeout_seconds,
                scheduled_at, monitor.generation, missed_slot,
            ))
        return jobs


async def probe(client: httpx.AsyncClient, job: Job) -> Observation:
    started_at = utcnow()
    start = perf_counter()
    status = None
    reason = None
    response = None
    try:
        url = validate_target(job.url)
        async with asyncio.timeout(job.timeout_seconds):
            response = await client.send(httpx.Request("GET", url), stream=True, follow_redirects=False)
            status = response.status_code
            if status != job.expected_status:
                reason = f"Expected HTTP {job.expected_status}, received {status}."
    except (TimeoutError, httpx.TimeoutException):
        reason = f"Request timed out after {job.timeout_seconds:g} s."
    except httpx.ConnectError:
        reason = "Connection failed."
    except httpx.RemoteProtocolError:
        reason = "Invalid or incomplete HTTP response."
    except httpx.HTTPError:
        reason = "HTTP request failed."
    except ValueError as exc:
        reason = str(exc)

    observation = Observation(started_at, utcnow(), round((perf_counter() - start) * 1000), status, reason)
    # A probe has no session state. Closing the streamed response discards its body.
    client.cookies.clear()
    if response is not None:
        with suppress(httpx.HTTPError):
            await response.aclose()
    return observation


async def record(db: AsyncSession, job: Job, observation: Observation) -> bool:
    async with db.begin():
        monitor = await db.get(Monitor, job.monitor_id, with_for_update=True)
        if monitor is None:
            return False
        previous_generation = await db.scalar(
            select(CheckResult.generation)
            .where(CheckResult.monitor_id == monitor.id, CheckResult.scheduled_at < job.scheduled_at)
            .order_by(CheckResult.scheduled_at.desc())
            .limit(1)
        )
        gap_before = job.missed_slot or (
            previous_generation is not None and previous_generation != job.generation
        )
        success = observation.http_status == job.expected_status
        check_id = await db.scalar(
            insert(CheckResult)
            .values(
                monitor_id=monitor.id,
                scheduled_at=job.scheduled_at,
                started_at=observation.started_at,
                finished_at=observation.finished_at,
                elapsed_ms=observation.elapsed_ms,
                success=success,
                http_status=observation.http_status,
                failure_reason=observation.failure_reason,
                generation=job.generation,
                gap_before=gap_before,
            )
            .on_conflict_do_nothing(constraint="uq_check_monitor_slot")
            .returning(CheckResult.id)
        )
        if check_id is None:
            return False
        if not monitor.enabled or monitor.generation != job.generation:
            return True

        monitor.awaiting_since = None
        incident = await db.scalar(
            select(Incident).where(Incident.monitor_id == monitor.id, Incident.resolved_at.is_(None))
        )
        next_state = next_streak(
            Streak(monitor.failure_streak, monitor.first_failure_at, monitor.recovery_streak),
            incident_open=incident is not None,
            success=success,
            finished_at=observation.finished_at,
        )
        monitor.failure_streak = next_state.failures
        monitor.first_failure_at = next_state.first_failure_at
        monitor.recovery_streak = next_state.recoveries

        if next_state.event == "outage":
            incident = Incident(
                monitor_id=monitor.id,
                first_failure_at=next_state.first_failure_at,
                confirmed_at=observation.finished_at,
            )
            db.add(incident)
            await db.flush()
        elif next_state.event == "recovery":
            incident.resolved_at = observation.finished_at

        if next_state.event:
            message = (
                f"{monitor.name} has an outage."
                if next_state.event == "outage" else f"{monitor.name} recovered."
            )
            db.add(Notification(
                incident_id=incident.id, event_type=next_state.event,
                created_at=observation.finished_at, message=message,
            ))
        return True


async def run_check(client: httpx.AsyncClient, job: Job):
    try:
        observation = await probe(client, job)
        async with Session() as db:
            await record(db, job, observation)
    except Exception:
        logger.exception("Check could not be recorded for monitor %s at %s", job.monitor_id, job.scheduled_at)


async def run():
    concurrency = int(os.getenv("CHECKER_CONCURRENCY", "8"))
    if concurrency < 1:
        raise ValueError("CHECKER_CONCURRENCY must be positive")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    active: dict[int, asyncio.Task] = {}
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(
        follow_redirects=False, trust_env=False, timeout=None, limits=limits
    ) as client:
        try:
            while not stop.is_set():
                active = {key: task for key, task in active.items() if not task.done()}
                capacity = concurrency - len(active)
                if capacity:
                    try:
                        async with Session() as db:
                            jobs = await claim_due(db, utcnow(), capacity, set(active))
                        for job in jobs:
                            active[job.monitor_id] = asyncio.create_task(run_check(client, job))
                    except SQLAlchemyError:
                        logger.exception("Could not claim scheduled checks")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=0.25)
                except TimeoutError:
                    pass
        finally:
            for task in active.values():
                task.cancel()
            await asyncio.gather(*active.values(), return_exceptions=True)
            await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(run())

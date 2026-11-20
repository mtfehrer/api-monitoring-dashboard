import asyncio
from datetime import UTC, datetime

import httpx

from monitoring.checker import Job, probe


class UnreadBody(httpx.AsyncByteStream):
    closed = False

    async def __aiter__(self):
        raise AssertionError("The checker should never read the body.")
        yield b""

    async def aclose(self):
        self.closed = True


async def test_redirect_is_an_observation_and_body_is_discarded():
    body = UnreadBody()
    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(
            302, headers={"Location": "http://demo:8001/other"}, stream=body,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect)) as client:
        observed = await probe(client, Job(1, "http://demo:8001/health", 200, 1, datetime.now(UTC), 0, False))
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert observed.http_status == 302
    assert observed.failure_reason == "Expected HTTP 200, received 302."
    assert body.closed


async def test_total_deadline_leaves_other_probes_free():
    entered = asyncio.Event()

    async def respond(request):
        if request.url.path == "/slow":
            entered.set()
            await asyncio.sleep(1)
        return httpx.Response(200)

    now = datetime.now(UTC)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        slow = asyncio.create_task(probe(client, Job(1, "http://demo/slow", 200, 0.08, now, 0, False)))
        await asyncio.wait_for(entered.wait(), timeout=1)
        fast = await probe(client, Job(2, "http://demo/fast", 200, 1, now, 0, False))
        assert fast.http_status == 200
        assert not slow.done()
        timed_out = await slow
    assert timed_out.http_status is None
    assert "timed out" in timed_out.failure_reason
    assert timed_out.elapsed_ms >= 70


async def test_connection_failure():
    def connect(request):
        raise httpx.ConnectError("test failure", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(connect)) as client:
        observed = await probe(client, Job(1, "http://demo/health", 200, 1, datetime.now(UTC), 0, False))
    assert observed.http_status is None
    assert observed.failure_reason == "Connection failed."

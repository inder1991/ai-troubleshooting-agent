"""Stage K.11 — traceparent stamped on every outbound request."""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from src.integrations import http_clients
from src.observability.trace_context import (
    TRACEPARENT_HEADER,
    TraceContext,
    set_context,
)


@pytest_asyncio.fixture(autouse=True)
async def _reset():
    await http_clients.reset_for_tests()
    yield
    await http_clients.reset_for_tests()


@pytest.mark.asyncio
async def test_traceparent_injected_when_context_is_set():
    set_context(TraceContext(trace_id="a" * 32, parent_id="b" * 16))
    client = http_clients.get_client("prometheus")

    captured: dict = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["traceparent"] = request.headers.get(TRACEPARENT_HEADER)
        return httpx.Response(200, text="ok")

    # Swap the singleton's transport to a MockTransport for the duration
    # of the test. Keeps the event_hooks pipeline in play.
    client._transport = httpx.MockTransport(_handler)
    await client.get("http://unused/api/v1/query")
    assert captured["traceparent"] is not None
    assert "a" * 32 in captured["traceparent"]


@pytest.mark.asyncio
async def test_existing_traceparent_not_overwritten():
    client = http_clients.get_client("prometheus")
    captured: dict = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["traceparent"] = request.headers.get(TRACEPARENT_HEADER)
        return httpx.Response(200, text="ok")

    client._transport = httpx.MockTransport(_handler)
    caller_header = f"00-{'c' * 32}-{'d' * 16}-01"
    await client.get(
        "http://unused/",
        headers={TRACEPARENT_HEADER: caller_header},
    )
    assert captured["traceparent"] == caller_header

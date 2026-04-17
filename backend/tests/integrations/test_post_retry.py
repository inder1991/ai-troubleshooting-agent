"""K.6 — idempotent_post retry + idempotency-key integration."""
from __future__ import annotations

import httpx
import pytest

from src.integrations.post_retry import idempotent_post
from src.network.idempotency import IDEMPOTENCY_KEY_HEADER


def _capture_handler(log: list) -> "httpx.MockTransport":
    """Build a mock transport whose handler records each inbound request."""

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        return httpx.Response(201, json={"id": "TICKET-1"})

    return httpx.MockTransport(handler)


def _retry_handler(log: list, first_status: int, retry_after: str | None = None) -> "httpx.MockTransport":
    """Return `first_status` once, then 201 forever."""
    state = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        state["count"] += 1
        if state["count"] == 1:
            headers = {}
            if retry_after is not None:
                headers["Retry-After"] = retry_after
            return httpx.Response(first_status, headers=headers, json={"err": "x"})
        return httpx.Response(201, json={"id": "TICKET-1"})

    return httpx.MockTransport(handler)


class TestIdempotencyKeyInjected:
    @pytest.mark.asyncio
    async def test_post_includes_idempotency_key(self):
        log: list = []
        async with httpx.AsyncClient(transport=_capture_handler(log)) as client:
            await idempotent_post(client, "http://x/issues", json={"a": 1})
        assert IDEMPOTENCY_KEY_HEADER in log[0].headers
        assert len(log[0].headers[IDEMPOTENCY_KEY_HEADER]) >= 32


class TestRetryUsesSameKey:
    @pytest.mark.asyncio
    async def test_429_retry_reuses_key(self):
        log: list = []
        async with httpx.AsyncClient(
            transport=_retry_handler(log, 429, retry_after="0"),
        ) as client:
            resp = await idempotent_post(
                client, "http://x/issues", json={"a": 1}, base_delay_s=0.01
            )
        assert resp.status_code == 201
        assert len(log) == 2
        keys = [r.headers[IDEMPOTENCY_KEY_HEADER] for r in log]
        assert len(set(keys)) == 1

    @pytest.mark.asyncio
    async def test_503_retry_reuses_key(self):
        log: list = []
        async with httpx.AsyncClient(transport=_retry_handler(log, 503)) as client:
            resp = await idempotent_post(
                client, "http://x/issues", json={"a": 1}, base_delay_s=0.01
            )
        assert resp.status_code == 201
        keys = [r.headers[IDEMPOTENCY_KEY_HEADER] for r in log]
        assert len(set(keys)) == 1


class TestCallerKeyWins:
    @pytest.mark.asyncio
    async def test_caller_supplied_key_preserved(self):
        log: list = []
        caller_key = "a" * 40
        async with httpx.AsyncClient(transport=_capture_handler(log)) as client:
            await idempotent_post(
                client,
                "http://x/issues",
                json={"a": 1},
                headers={IDEMPOTENCY_KEY_HEADER: caller_key},
            )
        assert log[0].headers[IDEMPOTENCY_KEY_HEADER] == caller_key


class TestSuccessNoRetry:
    @pytest.mark.asyncio
    async def test_2xx_first_try_no_retry(self):
        log: list = []
        async with httpx.AsyncClient(transport=_capture_handler(log)) as client:
            resp = await idempotent_post(client, "http://x/issues", json={"a": 1})
        assert resp.status_code == 201
        assert len(log) == 1

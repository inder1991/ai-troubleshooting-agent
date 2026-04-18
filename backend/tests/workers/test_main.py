"""Worker dispatcher unit tests — pure logic only (no real Postgres/Redis)."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.workers.main import (
    _Lifecycle,
    _redact,
    _supervised,
)


# ─── _redact() — log hygiene ─────────────────────────────────────────────────


def test_redact_postgres_url():
    assert _redact("postgresql+asyncpg://ai:secret@db:5432/app") \
        == "postgresql+asyncpg://ai:***@db:5432/app"


def test_redact_redis_url():
    assert _redact("redis://:hunter2@redis:6379/0") \
        == "redis://:***@redis:6379/0"


def test_redact_url_without_creds_is_passthrough():
    assert _redact("redis://redis:6379/0") == "redis://redis:6379/0"


def test_redact_garbage_is_passthrough():
    assert _redact("not a url") == "not a url"


# ─── _Lifecycle — drain semantics ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lifecycle_starts_undrained():
    lc = _Lifecycle()
    # Should NOT be set until request_drain is called.
    waiter = asyncio.create_task(lc.wait_for_drain())
    await asyncio.sleep(0.01)
    assert not waiter.done()
    waiter.cancel()
    try:
        await waiter
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_lifecycle_request_drain_unblocks_waiter():
    lc = _Lifecycle()
    waiter = asyncio.create_task(lc.wait_for_drain())
    await asyncio.sleep(0)  # give waiter a chance to schedule
    lc.request_drain()
    await asyncio.wait_for(waiter, timeout=1.0)


@pytest.mark.asyncio
async def test_lifecycle_request_drain_idempotent():
    lc = _Lifecycle()
    lc.request_drain()
    lc.request_drain()  # second call must not raise
    waiter = asyncio.create_task(lc.wait_for_drain())
    await asyncio.wait_for(waiter, timeout=1.0)


# ─── _supervised — restart-on-crash ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_supervised_propagates_cancellation():
    """CancelledError must propagate (drain path); we can't swallow it."""
    async def loop_forever():
        while True:
            await asyncio.sleep(0.1)

    task = asyncio.create_task(_supervised(loop_forever, "test"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_supervised_restarts_on_crash(caplog):
    """A failing subsystem must NOT take down the worker — log + retry."""
    calls = {"n": 0}

    async def crashy():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError(f"boom #{calls['n']}")
        # Third call: hang so we can cancel cleanly.
        await asyncio.sleep(10)

    # Replace the supervisor's backoff sleep with a near-zero yield so the
    # test runs in milliseconds. Patches the real asyncio.sleep call site.
    real_sleep = asyncio.sleep

    async def fast_sleep(_):
        await real_sleep(0)  # cooperative yield, no actual delay

    with patch("src.workers.main.asyncio.sleep", new=fast_sleep), \
         caplog.at_level(logging.ERROR):
        task = asyncio.create_task(_supervised(crashy, "crashy"))
        # Wait until the third call is in the long sleep.
        for _ in range(200):
            if calls["n"] >= 3:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert calls["n"] >= 3
    # Both crashes were logged.
    crash_logs = [r for r in caplog.records if "crashy crashed" in r.message]
    assert len(crash_logs) >= 2

"""Sprint H.0b Story 10 — with_retry decorator (Q17 P)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_with_retry_succeeds_first_attempt() -> None:
    from src.utils.http import with_retry

    counter = {"calls": 0}

    @with_retry()
    async def fn() -> int:
        counter["calls"] += 1
        return 1

    assert await fn() == 1
    assert counter["calls"] == 1


@pytest.mark.asyncio
async def test_with_retry_retries_on_transient_failure() -> None:
    import httpx
    from src.utils.http import with_retry

    counter = {"calls": 0}

    @with_retry(initial_delay=0.001, max_delay=0.005)
    async def fn() -> int:
        counter["calls"] += 1
        if counter["calls"] < 3:
            raise httpx.NetworkError("boom")
        return 42

    assert await fn() == 42
    assert counter["calls"] == 3


@pytest.mark.asyncio
async def test_with_retry_gives_up_after_max_attempts() -> None:
    import httpx
    from src.utils.http import with_retry

    counter = {"calls": 0}

    @with_retry(initial_delay=0.001, max_delay=0.005)
    async def fn() -> int:
        counter["calls"] += 1
        raise httpx.NetworkError("always boom")

    with pytest.raises(httpx.NetworkError):
        await fn()
    assert counter["calls"] == 3   # max_attempts default = 3

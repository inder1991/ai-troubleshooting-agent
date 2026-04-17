"""Task 3.17 — honour Retry-After on 429."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from src.network.retry_after import (
    RetryableStatusError,
    parse_retry_after,
    retry_with_retry_after,
)


class TestParseRetryAfter:
    def test_integer_seconds(self):
        assert parse_retry_after("2") == 2.0

    def test_float_seconds(self):
        assert parse_retry_after("2.5") == 2.5

    def test_http_date(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=5)
        header = format_datetime(future, usegmt=True)
        v = parse_retry_after(header)
        assert v is not None
        assert 4 <= v <= 6  # tolerance for clock skew

    def test_past_http_date_returns_zero(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        v = parse_retry_after(format_datetime(past, usegmt=True))
        assert v == 0.0

    def test_empty_returns_none(self):
        assert parse_retry_after("") is None
        assert parse_retry_after(None) is None

    def test_garbage_returns_none(self):
        assert parse_retry_after("forty-two") is None


class TestRetryWithRetryAfter:
    @pytest.mark.asyncio
    async def test_retry_after_seconds_respected(self):
        slept_for: list[float] = []

        async def fake_sleep(s: float) -> None:
            slept_for.append(s)

        attempts = {"n": 0}

        async def call():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RetryableStatusError(429, headers={"Retry-After": "2"})
            return "ok"

        result = await retry_with_retry_after(
            call, max_attempts=3, sleep=fake_sleep
        )
        assert result == "ok"
        assert slept_for == [2.0]

    @pytest.mark.asyncio
    async def test_429_without_retry_after_uses_backoff(self):
        slept_for: list[float] = []

        async def fake_sleep(s: float) -> None:
            slept_for.append(s)

        attempts = {"n": 0}

        async def call():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RetryableStatusError(429, headers={})
            return "ok"

        await retry_with_retry_after(
            call, max_attempts=3, base_delay_s=0.5, sleep=fake_sleep
        )
        # Backoff: base_delay * 2^0 + jitter(0..0.5) = 0.5..1.0
        assert 0.5 <= slept_for[0] <= 1.0

    @pytest.mark.asyncio
    async def test_retry_after_capped_at_60s(self):
        slept_for: list[float] = []

        async def fake_sleep(s: float) -> None:
            slept_for.append(s)

        attempts = {"n": 0}

        async def call():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RetryableStatusError(429, headers={"Retry-After": "3600"})
            return "ok"

        await retry_with_retry_after(
            call, max_attempts=3, sleep=fake_sleep
        )
        assert slept_for == [60.0]

    @pytest.mark.asyncio
    async def test_503_retries_with_backoff(self):
        slept_for: list[float] = []

        async def fake_sleep(s: float) -> None:
            slept_for.append(s)

        attempts = {"n": 0}

        async def call():
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise RetryableStatusError(503, headers={})
            return "ok"

        result = await retry_with_retry_after(
            call, max_attempts=4, base_delay_s=0.1, sleep=fake_sleep
        )
        assert result == "ok"
        assert len(slept_for) == 2

    @pytest.mark.asyncio
    async def test_exhausts_retries_and_raises(self):
        async def call():
            raise RetryableStatusError(503, headers={})

        async def fake_sleep(s: float) -> None:
            return None

        with pytest.raises(RetryableStatusError) as exc:
            await retry_with_retry_after(
                call, max_attempts=2, sleep=fake_sleep
            )
        assert exc.value.status == 503

    @pytest.mark.asyncio
    async def test_non_retryable_exception_propagates(self):
        async def call():
            raise ValueError("nope")

        with pytest.raises(ValueError):
            await retry_with_retry_after(call, max_attempts=3)

    @pytest.mark.asyncio
    async def test_success_first_try_no_sleep(self):
        slept_for: list[float] = []

        async def fake_sleep(s: float) -> None:
            slept_for.append(s)

        async def call():
            return "ok"

        assert await retry_with_retry_after(call, sleep=fake_sleep) == "ok"
        assert slept_for == []


class TestIntegrationRealSleep:
    @pytest.mark.asyncio
    async def test_actually_sleeps_when_honouring_retry_after(self):
        """Integration: verify real asyncio.sleep path works."""
        attempts = {"n": 0}

        async def call():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RetryableStatusError(429, headers={"Retry-After": "0.05"})
            return "ok"

        import time
        t0 = time.monotonic()
        result = await retry_with_retry_after(call, max_attempts=3)
        elapsed = time.monotonic() - t0
        assert result == "ok"
        assert elapsed >= 0.05

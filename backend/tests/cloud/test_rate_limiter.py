"""Tests for adaptive per-service rate limiter."""
import asyncio
import time
import pytest
from src.cloud.sync.rate_limiter import AdaptiveRateLimiter, _AWS_SERVICE_LIMITS


class TestAdaptiveRateLimiter:
    def test_default_limits_loaded(self):
        limiter = AdaptiveRateLimiter()
        assert "ec2" in limiter._limits
        assert "iam" in limiter._limits

    @pytest.mark.asyncio
    async def test_acquire_respects_interval(self):
        limiter = AdaptiveRateLimiter(
            service_limits={"test": {"base_rate": 100, "burst": 200, "throttle_backoff": 0.01}}
        )
        start = time.monotonic()
        await limiter.acquire("test")
        await limiter.acquire("test")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.009

    @pytest.mark.asyncio
    async def test_on_throttle_backs_off(self):
        limiter = AdaptiveRateLimiter(
            service_limits={"test": {"base_rate": 10, "burst": 50, "throttle_backoff": 0.01}}
        )
        start = time.monotonic()
        await limiter.on_throttle("test")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.01

    def test_on_success_resets_throttle(self):
        limiter = AdaptiveRateLimiter()
        limiter._throttle_counts["ec2"] = 5
        limiter.on_success("ec2")
        assert limiter._throttle_counts["ec2"] == 0

    @pytest.mark.asyncio
    async def test_unknown_service_uses_defaults(self):
        limiter = AdaptiveRateLimiter()
        await limiter.acquire("unknown_service")

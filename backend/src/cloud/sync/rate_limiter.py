"""Adaptive per-service rate limiter with exponential backoff + jitter."""
from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict

_AWS_SERVICE_LIMITS: dict[str, dict] = {
    "ec2": {"base_rate": 20, "burst": 100, "throttle_backoff": 1.0},
    "elasticloadbalancing": {"base_rate": 10, "burst": 40, "throttle_backoff": 2.0},
    "iam": {"base_rate": 5, "burst": 15, "throttle_backoff": 3.0},
    "directconnect": {"base_rate": 5, "burst": 10, "throttle_backoff": 2.0},
    "sts": {"base_rate": 10, "burst": 50, "throttle_backoff": 1.0},
}

_DEFAULT_LIMIT = {"base_rate": 10, "burst": 50, "throttle_backoff": 1.0}


class AdaptiveRateLimiter:
    def __init__(self, service_limits: dict[str, dict] | None = None):
        self._limits = service_limits if service_limits is not None else _AWS_SERVICE_LIMITS
        self._throttle_counts: dict[str, int] = defaultdict(int)
        self._last_call: dict[str, float] = {}

    async def acquire(self, service: str) -> None:
        limit = self._limits.get(service, _DEFAULT_LIMIT)
        min_interval = 1.0 / limit["base_rate"]
        last = self._last_call.get(service, 0)
        elapsed = time.monotonic() - last
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_call[service] = time.monotonic()

    async def on_throttle(self, service: str) -> None:
        self._throttle_counts[service] += 1
        limit = self._limits.get(service, _DEFAULT_LIMIT)
        base = limit["throttle_backoff"]
        delay = min(base * (2 ** self._throttle_counts[service]), 60.0)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        await asyncio.sleep(delay + jitter)

    def on_success(self, service: str) -> None:
        self._throttle_counts[service] = 0

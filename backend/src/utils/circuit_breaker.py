import logging
import os

import redis.asyncio as redis

logger = logging.getLogger(__name__)

FAILURE_WINDOW = 60
RECOVERY_TIMEOUT = int(os.getenv("CIRCUIT_BREAKER_RECOVERY_S", "120"))


class RedisCircuitBreaker:
    def __init__(self, redis_client: redis.Redis, failure_threshold: int = 3, recovery_timeout: int = RECOVERY_TIMEOUT):
        self._redis = redis_client
        self._threshold = failure_threshold
        self._recovery = recovery_timeout

    def _state_key(self, service: str) -> str:
        return f"cb:{service}:state"

    def _fail_key(self, service: str) -> str:
        return f"cb:{service}:failures"

    async def is_open(self, service: str) -> bool:
        state = await self._redis.get(self._state_key(service))
        if state and state in (b"open", "open"):
            return True
        return False

    async def record_failure(self, service: str) -> None:
        key = self._fail_key(service)
        count = await self._redis.incr(key)
        await self._redis.expire(key, FAILURE_WINDOW)
        if count >= self._threshold:
            await self._redis.set(self._state_key(service), "open", ex=self._recovery)
            await self._redis.delete(key)
            logger.warning(f"Circuit OPEN for {service} — {count} failures in {FAILURE_WINDOW}s")

    async def record_success(self, service: str) -> None:
        await self._redis.delete(self._fail_key(service))
        await self._redis.delete(self._state_key(service))

    async def get_retry_after(self, service: str) -> int | None:
        ttl = await self._redis.ttl(self._state_key(service))
        return ttl if ttl > 0 else None

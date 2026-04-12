import json
import os
import logging
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_SESSION_TTL = int(os.getenv("SESSION_TTL_S", "3600"))


async def get_redis_client() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=False)


class RedisSessionStore:
    def __init__(self, redis_client: redis.Redis, ttl: int = DEFAULT_SESSION_TTL):
        self._redis = redis_client
        self._ttl = ttl

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def save(self, session_id: str, state: dict[str, Any]) -> None:
        key = self._key(session_id)
        mapping = {field: json.dumps(value) for field, value in state.items()}
        await self._redis.hset(key, mapping=mapping)
        await self._redis.expire(key, self._ttl)

    async def load(self, session_id: str) -> dict[str, Any] | None:
        raw = await self._redis.hgetall(self._key(session_id))
        if not raw:
            return None
        return {
            (k.decode() if isinstance(k, bytes) else k): json.loads(
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in raw.items()
        }

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def extend_ttl(self, session_id: str) -> None:
        await self._redis.expire(self._key(session_id), self._ttl)

    def acquire_lock(self, session_id: str, timeout: float = 10.0):
        return self._redis.lock(f"lock:{session_id}", timeout=timeout)

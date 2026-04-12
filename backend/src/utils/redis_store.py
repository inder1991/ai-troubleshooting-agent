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

    # ── PendingAction helpers ──────────────────────────────────────────

    async def save_pending_action(self, session_id: str, action: "PendingAction") -> None:
        key = f"pending_action:{session_id}"
        await self._redis.set(key, json.dumps(action.to_dict()), ex=3600)

    async def load_pending_action(self, session_id: str):
        from src.models.pending_action import PendingAction

        key = f"pending_action:{session_id}"
        raw = await self._redis.get(key)
        if not raw:
            return None
        data = json.loads(raw if isinstance(raw, str) else raw.decode())
        return PendingAction.from_dict(data)

    async def clear_pending_action(self, session_id: str) -> None:
        key = f"pending_action:{session_id}"
        await self._redis.delete(key)

    def acquire_lock(self, session_id: str, timeout: float = 10.0):
        return self._redis.lock(f"lock:{session_id}", timeout=timeout)

import hashlib
import json
import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)

CACHE_TTL = 300


class ToolResultCache:
    def __init__(self, redis_client: redis.Redis, ttl: int = CACHE_TTL):
        self._redis = redis_client
        self._ttl = ttl

    def _cache_key(self, session_id: str, tool_name: str, params: dict) -> str:
        param_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
        return f"tool_cache:{session_id}:{tool_name}:{param_hash}"

    async def get_or_execute(self, session_id: str, tool_name: str, params: dict, executor) -> dict:
        key = self._cache_key(session_id, tool_name, params)
        cached = await self._redis.get(key)
        if cached:
            logger.debug(f"Cache hit: {tool_name}")
            return json.loads(cached)
        result = await executor(tool_name, params)
        try:
            await self._redis.setex(key, self._ttl, json.dumps(result))
        except (TypeError, ValueError):
            pass
        return result

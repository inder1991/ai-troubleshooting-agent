import asyncio
import os
import random
import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)

MAX_CONCURRENT_LLM = int(os.getenv("MAX_CONCURRENT_LLM_CALLS", "10"))
SEMAPHORE_KEY = "llm:semaphore"
SEMAPHORE_TTL = 60


class RedisLLMSemaphore:
    def __init__(self, redis_client: redis.Redis, max_concurrent: int = MAX_CONCURRENT_LLM):
        self._redis = redis_client
        self._max = max_concurrent

    async def acquire(self, timeout: float = 30.0) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            count = await self._redis.incr(SEMAPHORE_KEY)
            await self._redis.expire(SEMAPHORE_KEY, SEMAPHORE_TTL)
            if count <= self._max:
                return True
            await self._redis.decr(SEMAPHORE_KEY)
            await asyncio.sleep(0.5 + random.uniform(0, 0.5))
        return False

    async def release(self) -> None:
        val = await self._redis.decr(SEMAPHORE_KEY)
        if val < 0:
            await self._redis.set(SEMAPHORE_KEY, 0)

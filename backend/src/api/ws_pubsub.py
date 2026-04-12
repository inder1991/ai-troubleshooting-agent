import json
import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisPubSubBridge:
    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client
        self._pubsub = redis_client.pubsub()

    def _channel(self, session_id: str) -> str:
        return f"ws:session:{session_id}"

    async def publish(self, session_id: str, message: dict) -> None:
        await self._redis.publish(self._channel(session_id), json.dumps(message))

    async def subscribe(self, session_id: str) -> None:
        await self._pubsub.subscribe(self._channel(session_id))

    async def unsubscribe(self, session_id: str) -> None:
        await self._pubsub.unsubscribe(self._channel(session_id))

    async def get_message(self, timeout: float = 0.1) -> dict | None:
        msg = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        if msg and msg["type"] == "message":
            return json.loads(msg["data"])
        return None

    async def close(self) -> None:
        await self._pubsub.aclose()

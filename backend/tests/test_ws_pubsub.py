import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.ws_pubsub import RedisPubSubBridge


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    pubsub = AsyncMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.get_message = AsyncMock(return_value=None)
    r.pubsub = MagicMock(return_value=pubsub)
    r.publish = AsyncMock()
    return r, pubsub


@pytest.mark.asyncio
async def test_publish_event(mock_redis):
    redis_client, pubsub = mock_redis
    bridge = RedisPubSubBridge(redis_client)
    await bridge.publish("sess-1", {"event_type": "finding", "data": {}})
    redis_client.publish.assert_called_once()
    call_args = redis_client.publish.call_args
    assert call_args[0][0] == "ws:session:sess-1"


@pytest.mark.asyncio
async def test_subscribe_and_unsubscribe(mock_redis):
    redis_client, pubsub = mock_redis
    bridge = RedisPubSubBridge(redis_client)
    await bridge.subscribe("sess-1")
    pubsub.subscribe.assert_called_once_with("ws:session:sess-1")
    await bridge.unsubscribe("sess-1")
    pubsub.unsubscribe.assert_called_once_with("ws:session:sess-1")

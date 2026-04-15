import json
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_campaign_save_load():
    from src.utils.redis_store import RedisSessionStore

    campaign_data = {
        "total_count": 3,
        "approved_count": 1,
        "repos": [
            {"repo_url": "repo1", "status": "approved"},
            {"repo_url": "repo2", "status": "pending"},
        ],
    }

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(campaign_data))
    store = RedisSessionStore(mock_redis)

    await store.save_campaign("sess-1", campaign_data)
    mock_redis.set.assert_called_once()

    loaded = await store.load_campaign("sess-1")
    assert loaded["total_count"] == 3
    assert loaded["approved_count"] == 1


@pytest.mark.asyncio
async def test_campaign_load_returns_none_when_missing():
    from src.utils.redis_store import RedisSessionStore

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    store = RedisSessionStore(mock_redis)

    loaded = await store.load_campaign("nonexistent")
    assert loaded is None

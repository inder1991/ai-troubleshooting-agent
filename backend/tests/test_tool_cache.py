import pytest
import json
from unittest.mock import AsyncMock

from src.utils.tool_cache import ToolResultCache


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_cache_miss_executes_and_stores(mock_redis):
    cache = ToolResultCache(mock_redis)
    executor = AsyncMock(return_value={"data": "pod logs here"})
    result = await cache.get_or_execute("sess-1", "fetch_pod_logs", {"pod": "xyz"}, executor)
    assert result == {"data": "pod logs here"}
    executor.assert_called_once()
    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_cache_hit_skips_execution(mock_redis):
    mock_redis.get.return_value = json.dumps({"data": "cached"}).encode()
    cache = ToolResultCache(mock_redis)
    executor = AsyncMock()
    result = await cache.get_or_execute("sess-1", "fetch_pod_logs", {"pod": "xyz"}, executor)
    assert result == {"data": "cached"}
    executor.assert_not_called()

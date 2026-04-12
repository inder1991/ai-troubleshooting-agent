import pytest
import time
from unittest.mock import AsyncMock

from src.utils.circuit_breaker import RedisCircuitBreaker


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.incr = AsyncMock(return_value=1)
    r.expire = AsyncMock()
    r.set = AsyncMock()
    r.delete = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_closed_by_default(mock_redis):
    cb = RedisCircuitBreaker(mock_redis)
    assert await cb.is_open("elasticsearch") is False


@pytest.mark.asyncio
async def test_opens_after_threshold(mock_redis):
    cb = RedisCircuitBreaker(mock_redis, failure_threshold=3)
    mock_redis.incr.return_value = 3
    await cb.record_failure("elasticsearch")
    mock_redis.set.assert_called()


@pytest.mark.asyncio
async def test_open_circuit_blocks(mock_redis):
    cb = RedisCircuitBreaker(mock_redis)
    mock_redis.get.return_value = b"open"
    assert await cb.is_open("elasticsearch") is True


@pytest.mark.asyncio
async def test_success_resets_failures(mock_redis):
    cb = RedisCircuitBreaker(mock_redis)
    await cb.record_success("elasticsearch")
    mock_redis.delete.assert_called()

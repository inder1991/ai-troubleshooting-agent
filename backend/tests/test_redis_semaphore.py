import pytest
from unittest.mock import AsyncMock

from src.utils.redis_semaphore import RedisLLMSemaphore


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.incr = AsyncMock(return_value=1)
    r.decr = AsyncMock(return_value=0)
    r.expire = AsyncMock()
    r.get = AsyncMock(return_value=b"0")
    return r


@pytest.mark.asyncio
async def test_acquire_under_limit(mock_redis):
    sem = RedisLLMSemaphore(mock_redis, max_concurrent=10)
    acquired = await sem.acquire(timeout=5.0)
    assert acquired is True
    mock_redis.incr.assert_called_once_with("llm:semaphore")


@pytest.mark.asyncio
async def test_acquire_at_limit_fails(mock_redis):
    mock_redis.incr.return_value = 11
    sem = RedisLLMSemaphore(mock_redis, max_concurrent=10)
    acquired = await sem.acquire(timeout=0.1)
    assert acquired is False
    mock_redis.decr.assert_called()  # rolled back


@pytest.mark.asyncio
async def test_release(mock_redis):
    sem = RedisLLMSemaphore(mock_redis, max_concurrent=10)
    await sem.release()
    mock_redis.decr.assert_called_once_with("llm:semaphore")

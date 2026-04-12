import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

from src.utils.redis_store import RedisSessionStore


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.hset = AsyncMock()
    r.hgetall = AsyncMock(return_value={})
    r.delete = AsyncMock()
    r.expire = AsyncMock()
    r.lock = MagicMock(return_value=AsyncMock())
    return r


@pytest.fixture
def store(mock_redis):
    return RedisSessionStore(redis_client=mock_redis, ttl=3600)


@pytest.mark.asyncio
async def test_save_and_load(store, mock_redis):
    state = {"phase": "INITIAL", "confidence": 0.0, "findings": []}
    await store.save("sess-1", state)
    mock_redis.hset.assert_called_once()

    mock_redis.hgetall.return_value = {
        b"phase": b'"INITIAL"',
        b"confidence": b"0.0",
        b"findings": b"[]",
    }
    result = await store.load("sess-1")
    assert result["phase"] == "INITIAL"
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_load_missing_session(store, mock_redis):
    mock_redis.hgetall.return_value = {}
    result = await store.load("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete(store, mock_redis):
    await store.delete("sess-1")
    mock_redis.delete.assert_called_once_with("session:sess-1")


@pytest.mark.asyncio
async def test_extend_ttl(store, mock_redis):
    await store.extend_ttl("sess-1")
    mock_redis.expire.assert_called_once_with("session:sess-1", 3600)


@pytest.mark.asyncio
async def test_acquire_lock(store, mock_redis):
    lock = store.acquire_lock("sess-1")
    mock_redis.lock.assert_called_once()

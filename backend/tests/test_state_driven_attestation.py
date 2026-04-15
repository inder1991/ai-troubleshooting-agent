import json
import pytest
from unittest.mock import AsyncMock
from src.models.pending_action import PendingAction
from src.utils.redis_store import RedisSessionStore


@pytest.mark.asyncio
async def test_pending_action_saved_to_redis():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    store = RedisSessionStore(mock_redis)

    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject", "details"],
        expires_at=None,
        context={"findings_count": 4, "confidence": 0.87},
        version=1,
    )

    await store.save_pending_action("sess-1", pa)
    mock_redis.set.assert_called_once()
    call_key = mock_redis.set.call_args[0][0]
    assert "pending_action" in call_key
    assert "sess-1" in call_key


@pytest.mark.asyncio
async def test_pending_action_load_roundtrip():
    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=None,
        context={"diff_summary": "2 files changed"},
        version=1,
    )

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(pa.to_dict()))
    store = RedisSessionStore(mock_redis)

    loaded = await store.load_pending_action("sess-1")
    assert loaded is not None
    assert loaded.type == "fix_approval"
    assert loaded.context["diff_summary"] == "2 files changed"


@pytest.mark.asyncio
async def test_clear_pending_action():
    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock()
    store = RedisSessionStore(mock_redis)

    await store.clear_pending_action("sess-1")
    mock_redis.delete.assert_called_once()

import pytest
from unittest.mock import AsyncMock
from src.models.pending_action import PendingAction
import json


@pytest.mark.asyncio
async def test_fix_approval_saves_pending_action():
    from src.utils.redis_store import RedisSessionStore

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    store = RedisSessionStore(mock_redis)

    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject", "feedback"],
        expires_at=None,
        context={"diff_summary": "2 files changed", "fix_explanation": "Fix null check"},
        version=1,
    )
    await store.save_pending_action("sess-1", pa)

    call_args = mock_redis.set.call_args
    stored = json.loads(call_args[0][1])
    assert stored["type"] == "fix_approval"
    assert "approve" in stored["actions"]


@pytest.mark.asyncio
async def test_fix_approval_clears_pending_action():
    from src.utils.redis_store import RedisSessionStore

    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock()
    store = RedisSessionStore(mock_redis)

    await store.clear_pending_action("sess-1")

    mock_redis.delete.assert_called_once_with("pending_action:sess-1")


@pytest.mark.asyncio
async def test_pending_action_to_dict():
    from datetime import datetime, timezone

    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject", "feedback"],
        expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        context={"diff_summary": "3 files changed"},
        version=1,
    )
    d = pa.to_dict()
    assert d["type"] == "fix_approval"
    assert d["blocking"] is True
    assert d["actions"] == ["approve", "reject", "feedback"]
    assert d["expires_at"] == "2026-01-01T00:00:00+00:00"
    assert d["version"] == 1


@pytest.mark.asyncio
async def test_pending_action_roundtrip():
    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=None,
        context={"key": "val"},
        version=1,
    )
    d = pa.to_dict()
    pa2 = PendingAction.from_dict(d)
    assert pa2.type == pa.type
    assert pa2.actions == pa.actions
    assert pa2.context == pa.context

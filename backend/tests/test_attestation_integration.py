import json
import pytest
from unittest.mock import AsyncMock
from src.models.pending_action import PendingAction
from src.agents.intent_parser import IntentParser, UserIntent
from src.utils.redis_store import RedisSessionStore


@pytest.mark.asyncio
async def test_full_attestation_flow():
    """End-to-end: save pending -> parse intent -> clear pending."""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock()
    mock_redis.delete = AsyncMock()
    store = RedisSessionStore(mock_redis)

    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=None,
        context={"confidence": 0.87},
        version=1,
    )
    await store.save_pending_action("sess-1", pa)
    assert mock_redis.set.called

    parser = IntentParser()
    intent = parser.parse("looks good", pa)
    assert intent.type == "approve_attestation"

    await store.clear_pending_action("sess-1")
    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_fix_approval_flow():
    """End-to-end: fix pending -> approve intent -> clear."""
    parser = IntentParser()
    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject", "feedback"],
        expires_at=None,
        context={},
        version=1,
    )
    intent = parser.parse("create pr", pa)
    assert intent.type == "approve_fix"


@pytest.mark.asyncio
async def test_ambiguous_input_low_confidence():
    """Ambiguous input should return low confidence for re-prompting."""
    parser = IntentParser()
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=None,
        context={},
        version=1,
    )
    intent = parser.parse("hmm maybe", pa)
    assert intent.confidence < 0.7


def test_pending_action_roundtrip():
    pa = PendingAction(
        type="campaign_execute_confirm",
        blocking=True,
        actions=["confirm", "cancel"],
        expires_at=None,
        context={"repo_count": 5},
        version=2,
    )
    restored = PendingAction.from_dict(pa.to_dict())
    assert restored.type == pa.type
    assert restored.version == 2
    assert restored.context["repo_count"] == 5

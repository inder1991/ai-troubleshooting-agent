"""Tests for fix-approval race condition guard (P0-1) and Redis decision persistence (P0-2)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_supervisor():
    """Create a minimal SupervisorAgent with mocked dependencies."""
    from src.agents.supervisor import SupervisorAgent

    with patch("src.agents.supervisor.AnthropicClient"):
        sup = SupervisorAgent(connection_config=None)
    sup._session_id = "test-session-123"
    sup._pending_fix_approval = True
    sup._fix_human_decision = None
    sup._seen_feedback_ids = set()
    sup._attestation_logger = None
    return sup


def _make_mock_store(lock_result: bool = True, decision: str | None = None):
    """Create a mock RedisSessionStore."""
    store = AsyncMock()
    store.try_acquire_fix_lock = AsyncMock(return_value=lock_result)
    store.release_fix_lock = AsyncMock()
    store.save_fix_decision = AsyncMock()
    store.load_fix_decision = AsyncMock(return_value=decision)
    store.clear_fix_decision = AsyncMock()
    store.clear_pending_action = AsyncMock()
    return store


@pytest.mark.asyncio
async def test_concurrent_fix_decisions_blocked():
    """Second concurrent call should be rejected by Redis lock."""
    sup = _make_supervisor()
    store = _make_mock_store(lock_result=True)
    sup._session_store = store

    # First call acquires the lock and succeeds
    result1 = await sup._process_fix_decision("approve")
    assert "Approved" in result1
    store.try_acquire_fix_lock.assert_called_with("test-session-123")
    store.release_fix_lock.assert_called_with("test-session-123")

    # Simulate second concurrent call where lock is already held
    store.try_acquire_fix_lock.return_value = False
    sup._pending_fix_approval = True  # reset for second attempt
    sup._fix_human_decision = None

    result2 = await sup._process_fix_decision("approve")
    assert result2 == "Decision already being processed."


@pytest.mark.asyncio
async def test_fix_decision_persisted_to_redis():
    """Decision should be saved to Redis after processing."""
    sup = _make_supervisor()
    store = _make_mock_store(lock_result=True)
    sup._session_store = store

    await sup._process_fix_decision("approve")

    store.save_fix_decision.assert_called_once_with("test-session-123", "approve")


@pytest.mark.asyncio
async def test_resume_loads_from_redis_when_instance_state_lost():
    """If _fix_human_decision is None, should load from Redis."""
    sup = _make_supervisor()
    sup._fix_human_decision = None  # simulates server restart
    store = _make_mock_store(decision="approve")
    sup._session_store = store

    # Mock the fix_result on state so the approve branch works
    mock_state = MagicMock()
    mock_state.fix_result.pr_data = None  # skip PR creation
    mock_state.fix_result.fix_status = None
    mock_emitter = AsyncMock()
    mock_emitter.emit = AsyncMock()

    await sup.resume_fix_pipeline("test-session-123", mock_state, mock_emitter)

    store.load_fix_decision.assert_called_once_with("test-session-123")
    # Verify it proceeded with the approve flow (status set to PR_CREATING)
    from src.models.schemas import FixStatus
    assert mock_state.fix_result.fix_status == FixStatus.PR_CREATING


@pytest.mark.asyncio
async def test_resume_noop_when_no_decision_anywhere():
    """If no decision in memory or Redis, resume should be a no-op."""
    sup = _make_supervisor()
    sup._fix_human_decision = None
    store = _make_mock_store(decision=None)
    sup._session_store = store

    mock_state = MagicMock()
    mock_emitter = AsyncMock()

    await sup.resume_fix_pipeline("test-session-123", mock_state, mock_emitter)

    store.load_fix_decision.assert_called_once_with("test-session-123")
    # No status change should have happened
    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_fix_lock_released_on_exception():
    """Lock must be released even if processing raises."""
    sup = _make_supervisor()
    store = _make_mock_store(lock_result=True)
    sup._session_store = store

    # Force an exception inside the try block by making _pending_fix_approval
    # a property that raises when checked
    sup._pending_fix_approval = True

    # Patch clear_pending_action to raise, simulating an internal error
    store.clear_pending_action.side_effect = RuntimeError("Redis timeout")

    with pytest.raises(RuntimeError, match="Redis timeout"):
        await sup._process_fix_decision("approve")

    # Lock must still be released in the finally block
    store.release_fix_lock.assert_called_once_with("test-session-123")


@pytest.mark.asyncio
async def test_reject_decision_persisted():
    """Reject decision should also be persisted to Redis."""
    sup = _make_supervisor()
    store = _make_mock_store(lock_result=True)
    sup._session_store = store

    result = await sup._process_fix_decision("reject")
    assert "rejected" in result.lower()
    store.save_fix_decision.assert_called_once_with("test-session-123", "reject")


@pytest.mark.asyncio
async def test_feedback_decision_persisted():
    """Feedback text should be persisted to Redis as the decision."""
    sup = _make_supervisor()
    store = _make_mock_store(lock_result=True)
    sup._session_store = store

    result = await sup._process_fix_decision("Please also fix the null check")
    assert "regenerating" in result.lower()
    store.save_fix_decision.assert_called_once_with(
        "test-session-123", "Please also fix the null check"
    )


@pytest.mark.asyncio
async def test_audit_log_confidence_nonzero():
    """P0-5 partial: audit log should use 1.0 confidence for human decisions."""
    sup = _make_supervisor()
    store = _make_mock_store(lock_result=True)
    sup._session_store = store

    mock_logger = AsyncMock()
    sup._attestation_logger = mock_logger

    await sup._process_fix_decision("approve")

    mock_logger.log_decision.assert_called_once()
    call_kwargs = mock_logger.log_decision.call_args
    # Check confidence is 1.0, not 0.0
    assert call_kwargs.kwargs.get("confidence") == 1.0 or call_kwargs[1].get("confidence") == 1.0

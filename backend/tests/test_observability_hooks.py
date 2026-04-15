import pytest
from unittest.mock import AsyncMock
from src.utils.attestation_log import AttestationLogger


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.xadd = AsyncMock(return_value=b"1234567890-0")
    r.xrange = AsyncMock(return_value=[])
    return r


@pytest.fixture
def logger(mock_redis):
    return AttestationLogger(mock_redis)


@pytest.mark.asyncio
async def test_log_lifecycle_pending_created(logger, mock_redis):
    await logger.log_lifecycle("sess-1", "pending_action_created", {
        "type": "attestation_required", "version": 1,
    })
    mock_redis.xadd.assert_called_once()
    call_args = mock_redis.xadd.call_args
    assert call_args[0][0] == "audit:attestation_lifecycle"
    entry = call_args[0][1]
    assert entry["event"] == "pending_action_created"
    assert entry["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_log_lifecycle_resolved(logger, mock_redis):
    await logger.log_lifecycle("sess-1", "pending_action_resolved", {
        "type": "attestation_required", "decision": "approve", "response_time_ms": "4500",
    })
    mock_redis.xadd.assert_called_once()
    entry = mock_redis.xadd.call_args[0][1]
    assert entry["event"] == "pending_action_resolved"
    assert entry["response_time_ms"] == "4500"


@pytest.mark.asyncio
async def test_log_lifecycle_timed_out(logger, mock_redis):
    await logger.log_lifecycle("sess-1", "pending_action_timed_out", {
        "type": "fix_approval", "elapsed_s": "600",
    })
    entry = mock_redis.xadd.call_args[0][1]
    assert entry["event"] == "pending_action_timed_out"

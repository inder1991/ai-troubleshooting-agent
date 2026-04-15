import pytest
from unittest.mock import AsyncMock
from src.utils.attestation_log import AttestationLogger


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.xadd = AsyncMock(return_value=b"1234567890-0")
    return r


@pytest.fixture
def logger(mock_redis):
    return AttestationLogger(mock_redis)


@pytest.mark.asyncio
async def test_log_decision_calls_xadd(logger, mock_redis):
    entry_id = await logger.log_decision(
        session_id="sess-1",
        finding_id="all",
        decision="approved",
        decided_by="user",
        confidence=0.87,
        finding_summary="4 findings approved",
    )
    assert entry_id == b"1234567890-0"
    mock_redis.xadd.assert_called_once()
    call_args = mock_redis.xadd.call_args
    assert call_args[0][0] == "audit:attestations"
    entry = call_args[0][1]
    assert entry["session_id"] == "sess-1"
    assert entry["decision"] == "approved"


@pytest.mark.asyncio
async def test_log_fix_decision(logger, mock_redis):
    await logger.log_decision(
        session_id="sess-1",
        finding_id="fix_attempt_1",
        decision="approve",
        decided_by="user",
        confidence=0.0,
        finding_summary="Fix approved — creating PR",
    )
    mock_redis.xadd.assert_called_once()

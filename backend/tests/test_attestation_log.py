import pytest
import json
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
    return AttestationLogger(redis_client=mock_redis)


@pytest.mark.asyncio
async def test_log_decision(logger, mock_redis):
    await logger.log_decision(
        session_id="sess-1", finding_id="f1", decision="approved",
        decided_by="user", confidence=0.92, finding_summary="OOM in pod-xyz",
    )
    mock_redis.xadd.assert_called_once()
    call_args = mock_redis.xadd.call_args
    assert call_args[0][0] == "audit:attestations"
    fields = call_args[0][1]
    assert fields["session_id"] == "sess-1"
    assert fields["decision"] == "approved"


@pytest.mark.asyncio
async def test_query_by_session(logger, mock_redis):
    mock_redis.xrange.return_value = [
        (b"1234-0", {b"session_id": b"sess-1", b"finding_id": b"f1",
                     b"decision": b"approved", b"decided_by": b"user",
                     b"confidence": b"0.92", b"finding_summary": b"OOM in pod-xyz"}),
    ]
    results = await logger.query(session_id="sess-1")
    assert len(results) == 1
    assert results[0]["decision"] == "approved"


@pytest.mark.asyncio
async def test_query_filters_by_decided_by(logger, mock_redis):
    mock_redis.xrange.return_value = [
        (b"1-0", {b"session_id": b"s1", b"finding_id": b"f1",
                  b"decision": b"approved", b"decided_by": b"user",
                  b"confidence": b"0.9", b"finding_summary": b"finding 1"}),
        (b"2-0", {b"session_id": b"s2", b"finding_id": b"f2",
                  b"decision": b"auto_approved", b"decided_by": b"system",
                  b"confidence": b"0.95", b"finding_summary": b"finding 2"}),
    ]
    results = await logger.query(decided_by="user")
    assert len(results) == 1
    assert results[0]["decided_by"] == "user"


@pytest.mark.asyncio
async def test_query_all(logger, mock_redis):
    mock_redis.xrange.return_value = [
        (b"1-0", {b"session_id": b"s1", b"finding_id": b"f1",
                  b"decision": b"approved", b"decided_by": b"user",
                  b"confidence": b"0.9", b"finding_summary": b"f1"}),
    ]
    results = await logger.query()
    assert len(results) == 1

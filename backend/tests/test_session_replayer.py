import pytest
from unittest.mock import AsyncMock
from src.utils.session_replayer import SessionReplayer
from src.utils.attestation_log import AttestationLogger


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.xrange = AsyncMock(return_value=[
        (b"1-0", {b"session_id": b"sess-1", b"event": b"pending_action_created",
                  b"timestamp": b"2026-04-12T10:00:00", b"type": b"attestation_required"}),
        (b"2-0", {b"session_id": b"sess-1", b"event": b"pending_action_resolved",
                  b"timestamp": b"2026-04-12T10:01:30", b"decision": b"approve"}),
    ])
    return r


@pytest.mark.asyncio
async def test_replay_returns_chronological_timeline(mock_redis):
    logger = AttestationLogger(mock_redis)
    replayer = SessionReplayer(logger)
    timeline = await replayer.replay("sess-1")
    assert len(timeline) >= 1
    timestamps = [e["timestamp"] for e in timeline]
    assert timestamps == sorted(timestamps)

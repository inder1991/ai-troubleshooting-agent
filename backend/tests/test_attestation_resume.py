import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_acknowledge_clears_pending_and_sets_flag():
    from src.agents.supervisor import SupervisorAgent

    supervisor = SupervisorAgent.__new__(SupervisorAgent)
    supervisor._attestation_acknowledged = False
    supervisor._attestation_logger = None
    supervisor._session_store = AsyncMock()
    supervisor._session_id = "sess-1"

    result = await supervisor.acknowledge_attestation("approve", session_id="sess-1")
    assert supervisor._attestation_acknowledged is True
    assert "approved" in result.lower() or "available" in result.lower()
    supervisor._session_store.clear_pending_action.assert_called_once_with("sess-1")


@pytest.mark.asyncio
async def test_acknowledge_reject_keeps_flag_false():
    from src.agents.supervisor import SupervisorAgent

    supervisor = SupervisorAgent.__new__(SupervisorAgent)
    supervisor._attestation_acknowledged = False
    supervisor._attestation_logger = None
    supervisor._session_store = AsyncMock()
    supervisor._session_id = "sess-1"

    result = await supervisor.acknowledge_attestation("reject", session_id="sess-1")
    assert supervisor._attestation_acknowledged is False
    assert "rejected" in result.lower() or "revision" in result.lower()
    supervisor._session_store.clear_pending_action.assert_called_once_with("sess-1")

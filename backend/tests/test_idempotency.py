import pytest


@pytest.mark.asyncio
async def test_idempotent_attestation_approve():
    """Second attestation approval should return existing result, not error."""
    from src.agents.supervisor import SupervisorAgent

    supervisor = SupervisorAgent.__new__(SupervisorAgent)
    supervisor._attestation_acknowledged = True  # Already approved
    supervisor._attestation_logger = None
    supervisor._session_store = None
    supervisor._session_id = "sess-1"

    result = await supervisor.acknowledge_attestation("approve", "sess-1")
    assert "already" in result.lower()


@pytest.mark.asyncio
async def test_fix_decide_already_decided():
    """If fix was already decided, return existing result."""
    from src.agents.supervisor import SupervisorAgent

    supervisor = SupervisorAgent.__new__(SupervisorAgent)
    supervisor._pending_fix_approval = False  # Not pending
    supervisor._fix_human_decision = "approve"  # Already decided
    supervisor._attestation_logger = None
    supervisor._session_store = None
    supervisor._session_id = "sess-1"

    result = await supervisor._process_fix_decision("approve")
    assert "no fix awaiting" in result.lower() or "already" in result.lower()

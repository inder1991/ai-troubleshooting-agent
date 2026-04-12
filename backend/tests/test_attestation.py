import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_auto_approval_above_threshold():
    from src.agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent.__new__(SupervisorAgent)
    supervisor._event_emitter = AsyncMock()

    with patch.dict(os.environ, {"ATTESTATION_AUTO_APPROVE_THRESHOLD": "0.85"}):
        result = supervisor._should_auto_approve(confidence=0.92, critic_has_challenges=False)
    assert result is True


@pytest.mark.asyncio
async def test_no_auto_approval_below_threshold():
    from src.agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent.__new__(SupervisorAgent)

    with patch.dict(os.environ, {"ATTESTATION_AUTO_APPROVE_THRESHOLD": "0.85"}):
        result = supervisor._should_auto_approve(confidence=0.70, critic_has_challenges=False)
    assert result is False


@pytest.mark.asyncio
async def test_no_auto_approval_with_challenges():
    from src.agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent.__new__(SupervisorAgent)

    with patch.dict(os.environ, {"ATTESTATION_AUTO_APPROVE_THRESHOLD": "0.85"}):
        result = supervisor._should_auto_approve(confidence=0.95, critic_has_challenges=True)
    assert result is False

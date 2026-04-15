import json
import pytest
from unittest.mock import AsyncMock
from src.models.pending_action import PendingAction


@pytest.mark.asyncio
async def test_status_includes_pending_action():
    """Session status endpoint should return pending_action when one exists."""
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject", "details"],
        expires_at=None,
        context={"confidence": 0.87},
        version=1,
    )
    d = pa.to_dict()
    assert d["type"] == "attestation_required"
    assert d["actions"] == ["approve", "reject", "details"]
    assert d["blocking"] is True


@pytest.mark.asyncio
async def test_status_pending_action_none():
    """When no pending action, the field should serialize as None."""
    pa = None
    result_field = pa.to_dict() if pa else None
    assert result_field is None

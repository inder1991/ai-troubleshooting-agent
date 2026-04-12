from datetime import datetime, timezone, timedelta
from src.models.pending_action import PendingAction


def test_pending_action_to_dict_roundtrip():
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject", "details"],
        expires_at=datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc),
        context={"findings_count": 4, "confidence": 0.87},
        version=1,
    )
    d = pa.to_dict()
    restored = PendingAction.from_dict(d)
    assert restored.type == "attestation_required"
    assert restored.blocking is True
    assert restored.actions == ["approve", "reject", "details"]
    assert restored.expires_at == pa.expires_at
    assert restored.context["confidence"] == 0.87
    assert restored.version == 1


def test_pending_action_is_expired():
    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        context={},
        version=1,
    )
    assert pa.is_expired() is True


def test_pending_action_no_expiry_never_expired():
    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=None,
        context={},
        version=1,
    )
    assert pa.is_expired() is False

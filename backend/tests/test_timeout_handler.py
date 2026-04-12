import pytest
from datetime import datetime, timezone, timedelta
from src.models.pending_action import PendingAction


def test_expired_action_detected():
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        context={},
        version=1,
    )
    assert pa.is_expired() is True


def test_non_expired_action_not_detected():
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=600),
        context={},
        version=1,
    )
    assert pa.is_expired() is False


def test_no_expiry_never_expires():
    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=None,
        context={},
        version=1,
    )
    assert pa.is_expired() is False

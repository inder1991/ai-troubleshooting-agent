from datetime import datetime, timezone, timedelta
from src.models.pending_action import (
    PendingAction, AttestationContext, FixApprovalContext, CampaignExecuteContext,
)


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


def test_attestation_context_roundtrip():
    ctx = AttestationContext(findings_count=4, confidence=0.87, proposed_action="Fix auth")
    pa = PendingAction(
        type="attestation_required", blocking=True,
        actions=["approve", "reject"], expires_at=None,
        context=ctx, version=1,
    )
    d = pa.to_dict()
    restored = PendingAction.from_dict(d)
    assert isinstance(restored.context, AttestationContext)
    assert restored.context.findings_count == 4
    assert restored.context.confidence == 0.87


def test_fix_approval_context_roundtrip():
    ctx = FixApprovalContext(
        diff_summary="2 files changed", fix_explanation="Add null check",
        fixed_files=["auth.py", "handler.py"], attempt_number=1,
    )
    pa = PendingAction(
        type="fix_approval", blocking=True,
        actions=["approve", "reject", "feedback"], expires_at=None,
        context=ctx, version=1,
    )
    d = pa.to_dict()
    restored = PendingAction.from_dict(d)
    assert isinstance(restored.context, FixApprovalContext)
    assert restored.context.fixed_files == ["auth.py", "handler.py"]


def test_campaign_context_roundtrip():
    ctx = CampaignExecuteContext(repo_count=5, repos=["r1", "r2"], approved_count=5)
    pa = PendingAction(
        type="campaign_execute_confirm", blocking=True,
        actions=["confirm", "cancel"], expires_at=None,
        context=ctx, version=1,
    )
    d = pa.to_dict()
    restored = PendingAction.from_dict(d)
    assert isinstance(restored.context, CampaignExecuteContext)
    assert restored.context.repo_count == 5

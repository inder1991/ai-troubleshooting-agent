import pytest
from datetime import datetime
from src.models.attestation import AttestationGate, AttestationDecision


def test_gate_pending_by_default():
    gate = AttestationGate(findings=[{"finding_id": "f1"}, {"finding_id": "f2"}])
    assert gate.status == "pending"
    assert gate.is_complete() is False


def test_gate_complete_when_all_decided():
    gate = AttestationGate(findings=[{"finding_id": "f1"}])
    gate.decisions["f1"] = AttestationDecision(
        finding_id="f1", decision="approved", decided_by="user",
        decided_at=datetime.utcnow(), confidence_at_decision=0.9,
    )
    assert gate.is_complete() is True


def test_approved_finding_ids():
    gate = AttestationGate(findings=[{"finding_id": "f1"}, {"finding_id": "f2"}])
    gate.decisions["f1"] = AttestationDecision(
        finding_id="f1", decision="approved", decided_by="user",
        decided_at=datetime.utcnow(), confidence_at_decision=0.9,
    )
    gate.decisions["f2"] = AttestationDecision(
        finding_id="f2", decision="rejected", decided_by="user",
        decided_at=datetime.utcnow(), confidence_at_decision=0.5,
    )
    assert gate.approved_finding_ids() == ["f1"]

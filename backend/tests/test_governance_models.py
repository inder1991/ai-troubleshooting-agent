"""Tests for v5 governance data models (Phase 1, Task 1)."""

import pytest
from datetime import datetime
from pydantic import ValidationError
from src.models.schemas import (
    EvidencePin,
    ConfidenceLedger,
    AttestationGate,
    ReasoningStep,
    ReasoningManifest,
    DiagnosticStateV5,
    DiagnosticState,
    DiagnosticPhase,
    TimeWindow,
)


# ---------------------------------------------------------------------------
# TestEvidencePin
# ---------------------------------------------------------------------------


class TestEvidencePin:
    def test_create_valid_pin(self):
        pin = EvidencePin(
            claim="Database connection pool exhausted",
            supporting_evidence=["log line 42", "metric spike at 14:00"],
            source_agent="log_agent",
            source_tool="elasticsearch",
            confidence=0.85,
            timestamp=datetime(2025, 12, 26, 14, 0, 0),
            evidence_type="log",
        )
        assert pin.claim == "Database connection pool exhausted"
        assert pin.confidence == 0.85
        assert pin.evidence_type == "log"
        assert len(pin.supporting_evidence) == 2

    def test_reject_confidence_above_one(self):
        with pytest.raises(ValidationError):
            EvidencePin(
                claim="Something",
                source_agent="agent",
                source_tool="tool",
                confidence=1.5,
                timestamp=datetime.now(),
                evidence_type="log",
            )

    def test_reject_confidence_below_zero(self):
        with pytest.raises(ValidationError):
            EvidencePin(
                claim="Something",
                source_agent="agent",
                source_tool="tool",
                confidence=-0.1,
                timestamp=datetime.now(),
                evidence_type="log",
            )

    def test_reject_empty_claim(self):
        with pytest.raises(ValidationError):
            EvidencePin(
                claim="",
                source_agent="agent",
                source_tool="tool",
                confidence=0.5,
                timestamp=datetime.now(),
                evidence_type="log",
            )

    def test_default_supporting_evidence_is_empty(self):
        pin = EvidencePin(
            claim="A claim",
            source_agent="agent",
            source_tool="tool",
            confidence=0.5,
            timestamp=datetime.now(),
            evidence_type="metric",
        )
        assert pin.supporting_evidence == []

    def test_all_evidence_types(self):
        for etype in ("log", "metric", "trace", "k8s_event", "code", "change"):
            pin = EvidencePin(
                claim="Test",
                source_agent="a",
                source_tool="t",
                confidence=0.5,
                timestamp=datetime.now(),
                evidence_type=etype,
            )
            assert pin.evidence_type == etype

    def test_reject_invalid_evidence_type(self):
        with pytest.raises(ValidationError):
            EvidencePin(
                claim="Test",
                source_agent="a",
                source_tool="t",
                confidence=0.5,
                timestamp=datetime.now(),
                evidence_type="invalid",
            )


# ---------------------------------------------------------------------------
# TestConfidenceLedger
# ---------------------------------------------------------------------------


class TestConfidenceLedger:
    def test_create_default(self):
        ledger = ConfidenceLedger()
        assert ledger.log_confidence == 0.0
        assert ledger.metrics_confidence == 0.0
        assert ledger.weighted_final == 0.0
        assert ledger.critic_adjustment == 0.0
        assert "log" in ledger.weights
        assert abs(sum(ledger.weights.values()) - 1.0) < 1e-9

    def test_compute_weighted_final(self):
        ledger = ConfidenceLedger(
            log_confidence=0.8,
            metrics_confidence=0.9,
            tracing_confidence=0.7,
            k8s_confidence=0.6,
            code_confidence=0.5,
            change_confidence=0.4,
        )
        ledger.compute_weighted_final()
        # Expected: 0.8*0.25 + 0.9*0.30 + 0.7*0.20 + 0.6*0.15 + 0.5*0.05 + 0.4*0.05
        # = 0.20 + 0.27 + 0.14 + 0.09 + 0.025 + 0.02 = 0.745
        assert abs(ledger.weighted_final - 0.745) < 1e-9

    def test_compute_weighted_final_with_critic_adjustment(self):
        ledger = ConfidenceLedger(
            log_confidence=0.8,
            metrics_confidence=0.9,
            tracing_confidence=0.7,
            k8s_confidence=0.6,
            code_confidence=0.5,
            change_confidence=0.4,
            critic_adjustment=-0.1,
        )
        ledger.compute_weighted_final()
        # 0.745 + (-0.1) = 0.645
        assert abs(ledger.weighted_final - 0.645) < 1e-9

    def test_weighted_final_clamped_to_zero(self):
        ledger = ConfidenceLedger(
            log_confidence=0.0,
            metrics_confidence=0.0,
            tracing_confidence=0.0,
            k8s_confidence=0.0,
            code_confidence=0.0,
            change_confidence=0.0,
            critic_adjustment=-0.3,
        )
        ledger.compute_weighted_final()
        assert ledger.weighted_final == 0.0

    def test_weighted_final_clamped_to_one(self):
        ledger = ConfidenceLedger(
            log_confidence=1.0,
            metrics_confidence=1.0,
            tracing_confidence=1.0,
            k8s_confidence=1.0,
            code_confidence=1.0,
            change_confidence=1.0,
            critic_adjustment=0.1,
        )
        ledger.compute_weighted_final()
        assert ledger.weighted_final == 1.0

    def test_critic_adjustment_reject_too_low(self):
        with pytest.raises(ValidationError):
            ConfidenceLedger(critic_adjustment=-0.5)

    def test_critic_adjustment_reject_too_high(self):
        with pytest.raises(ValidationError):
            ConfidenceLedger(critic_adjustment=0.2)


# ---------------------------------------------------------------------------
# TestAttestationGate
# ---------------------------------------------------------------------------


class TestAttestationGate:
    def test_create_gate(self):
        gate = AttestationGate(gate_type="discovery_complete")
        assert gate.gate_type == "discovery_complete"
        assert gate.requires_human is True
        assert gate.evidence_summary == []
        assert gate.proposed_action is None
        assert gate.human_decision is None

    def test_approve_gate(self):
        gate = AttestationGate(
            gate_type="pre_remediation",
            proposed_action="Restart pod payment-service-abc",
            human_decision="approve",
            human_notes="Looks good, proceed.",
            decided_at=datetime(2025, 12, 26, 15, 0, 0),
            decided_by="oncall-eng",
        )
        assert gate.human_decision == "approve"
        assert gate.decided_by == "oncall-eng"

    def test_gate_with_evidence_pins(self):
        pin = EvidencePin(
            claim="Pod crash loop detected",
            source_agent="k8s_agent",
            source_tool="kubectl",
            confidence=0.95,
            timestamp=datetime.now(),
            evidence_type="k8s_event",
        )
        gate = AttestationGate(
            gate_type="pre_remediation",
            evidence_summary=[pin],
        )
        assert len(gate.evidence_summary) == 1
        assert gate.evidence_summary[0].claim == "Pod crash loop detected"

    def test_reject_invalid_gate_type(self):
        with pytest.raises(ValidationError):
            AttestationGate(gate_type="invalid_type")

    def test_reject_invalid_human_decision(self):
        with pytest.raises(ValidationError):
            AttestationGate(
                gate_type="discovery_complete",
                human_decision="maybe",
            )


# ---------------------------------------------------------------------------
# TestReasoningManifest
# ---------------------------------------------------------------------------


class TestReasoningManifest:
    def test_create_manifest(self):
        manifest = ReasoningManifest(session_id="sess-001")
        assert manifest.session_id == "sess-001"
        assert manifest.steps == []

    def test_add_steps(self):
        step1 = ReasoningStep(
            step_number=1,
            timestamp=datetime(2025, 12, 26, 14, 0, 0),
            decision="Analyze logs first",
            reasoning="Logs are the most common source of error evidence",
            evidence_considered=["error rate spike"],
            confidence_at_step=0.3,
        )
        step2 = ReasoningStep(
            step_number=2,
            timestamp=datetime(2025, 12, 26, 14, 5, 0),
            decision="Check metrics correlation",
            reasoning="Logs showed timeout errors; metrics may confirm",
            evidence_considered=["timeout logs", "latency metric"],
            confidence_at_step=0.6,
            alternatives_rejected=["Skip metrics, go to tracing"],
        )
        manifest = ReasoningManifest(
            session_id="sess-001",
            steps=[step1, step2],
        )
        assert len(manifest.steps) == 2
        assert manifest.steps[0].step_number == 1
        assert manifest.steps[1].confidence_at_step == 0.6
        assert "Skip metrics" in manifest.steps[1].alternatives_rejected[0]


# ---------------------------------------------------------------------------
# TestDiagnosticStateV5
# ---------------------------------------------------------------------------


class TestDiagnosticStateV5:
    def _make_base_kwargs(self):
        return dict(
            session_id="sess-v5-001",
            phase=DiagnosticPhase.INITIAL,
            service_name="payment-service",
            time_window=TimeWindow(start="2025-12-26T14:00:00", end="2025-12-26T15:00:00"),
        )

    def test_extends_diagnostic_state(self):
        assert issubclass(DiagnosticStateV5, DiagnosticState)

    def test_create_with_defaults(self):
        state = DiagnosticStateV5(**self._make_base_kwargs())
        assert state.evidence_pins == []
        assert isinstance(state.confidence_ledger, ConfidenceLedger)
        assert state.attestation_gates == []
        assert state.reasoning_manifest is not None
        assert state.reasoning_manifest.session_id == "sess-v5-001"
        assert state.integration_id is None

    def test_v5_fields_alongside_base_fields(self):
        state = DiagnosticStateV5(**self._make_base_kwargs())
        # Base fields still work
        assert state.service_name == "payment-service"
        assert state.phase == DiagnosticPhase.INITIAL
        assert state.all_findings == []

    def test_with_evidence_and_gates(self):
        pin = EvidencePin(
            claim="OOM kill detected",
            source_agent="k8s_agent",
            source_tool="kubectl",
            confidence=0.9,
            timestamp=datetime.now(),
            evidence_type="k8s_event",
        )
        gate = AttestationGate(gate_type="discovery_complete")
        state = DiagnosticStateV5(
            **self._make_base_kwargs(),
            evidence_pins=[pin],
            attestation_gates=[gate],
        )
        assert len(state.evidence_pins) == 1
        assert len(state.attestation_gates) == 1

    def test_reasoning_manifest_auto_initialized(self):
        """When reasoning_manifest is None, it should be auto-set from session_id."""
        state = DiagnosticStateV5(**self._make_base_kwargs())
        assert state.reasoning_manifest is not None
        assert state.reasoning_manifest.session_id == state.session_id

    def test_reasoning_manifest_explicit(self):
        """When reasoning_manifest is explicitly provided, use it as-is."""
        manifest = ReasoningManifest(session_id="custom-session")
        state = DiagnosticStateV5(
            **self._make_base_kwargs(),
            reasoning_manifest=manifest,
        )
        assert state.reasoning_manifest.session_id == "custom-session"

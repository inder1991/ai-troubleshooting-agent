"""Tests for hypothesis models — EvidenceSignal, CausalLink, Hypothesis, HypothesisResult."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.models.hypothesis import EvidenceSignal, CausalLink, Hypothesis, HypothesisResult


# ── EvidenceSignal ──────────────────────────────────────────────────────────

class TestEvidenceSignal:
    def test_basic_creation_with_defaults(self):
        sig = EvidenceSignal(
            signal_id="sig-1",
            signal_type="log",
            signal_name="oom_kill",
            source_agent="log_agent",
        )
        assert sig.signal_id == "sig-1"
        assert sig.signal_type == "log"
        assert sig.signal_name == "oom_kill"
        assert sig.raw_data == {}
        assert sig.source_agent == "log_agent"
        assert sig.timestamp is None
        assert sig.strength == 1.0
        assert sig.freshness == 1.0

    def test_strength_clamped_above_one(self):
        sig = EvidenceSignal(
            signal_id="s1", signal_type="metric", signal_name="high_cpu",
            source_agent="metrics_agent", strength=5.0,
        )
        assert sig.strength == 1.0

    def test_strength_clamped_below_zero(self):
        sig = EvidenceSignal(
            signal_id="s1", signal_type="metric", signal_name="high_cpu",
            source_agent="metrics_agent", strength=-2.0,
        )
        assert sig.strength == 0.0

    def test_freshness_clamped_above_one(self):
        sig = EvidenceSignal(
            signal_id="s1", signal_type="log", signal_name="err",
            source_agent="a", freshness=1.5,
        )
        assert sig.freshness == 1.0

    def test_freshness_clamped_below_zero(self):
        sig = EvidenceSignal(
            signal_id="s1", signal_type="log", signal_name="err",
            source_agent="a", freshness=-0.3,
        )
        assert sig.freshness == 0.0

    def test_invalid_signal_type_raises(self):
        with pytest.raises(ValidationError):
            EvidenceSignal(
                signal_id="s1", signal_type="invalid_type",
                signal_name="x", source_agent="a",
            )

    def test_all_valid_signal_types(self):
        for st in ("log", "metric", "k8s", "trace", "code", "change"):
            sig = EvidenceSignal(
                signal_id="s1", signal_type=st,
                signal_name="x", source_agent="a",
            )
            assert sig.signal_type == st

    def test_timestamp_accepted(self):
        now = datetime.utcnow()
        sig = EvidenceSignal(
            signal_id="s1", signal_type="log", signal_name="x",
            source_agent="a", timestamp=now,
        )
        assert sig.timestamp == now


# ── CausalLink ──────────────────────────────────────────────────────────────

class TestCausalLink:
    def test_basic_creation(self):
        link = CausalLink(
            cause_signal="sig-1",
            effect_signal="sig-2",
            confidence=0.85,
            time_delta_seconds=12.5,
        )
        assert link.cause_signal == "sig-1"
        assert link.effect_signal == "sig-2"
        assert link.confidence == 0.85
        assert link.time_delta_seconds == 12.5
        assert link.same_entity is False
        assert link.validation == ""

    def test_invalid_confidence_raises(self):
        with pytest.raises(ValidationError):
            CausalLink(
                cause_signal="a", effect_signal="b",
                confidence=1.5, time_delta_seconds=0,
            )


# ── Hypothesis ──────────────────────────────────────────────────────────────

class TestHypothesis:
    def test_basic_creation_with_defaults(self):
        h = Hypothesis(hypothesis_id="h-1", category="memory")
        assert h.hypothesis_id == "h-1"
        assert h.category == "memory"
        assert h.source_patterns == []
        assert h.status == "active"
        assert h.confidence == 0.0
        assert h.evidence_for == []
        assert h.evidence_against == []
        assert h.downstream_effects == []
        assert h.root_cause_of is None
        assert h.elimination_reason is None
        assert h.elimination_phase is None

    def test_status_change_to_eliminated(self):
        h = Hypothesis(hypothesis_id="h-1", category="memory", status="eliminated",
                       elimination_reason="no supporting evidence",
                       elimination_phase="metric_validation")
        assert h.status == "eliminated"
        assert h.elimination_reason == "no supporting evidence"

    def test_status_change_to_winner(self):
        h = Hypothesis(hypothesis_id="h-1", category="connection", status="winner",
                       confidence=92.5)
        assert h.status == "winner"
        assert h.confidence == 92.5

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            Hypothesis(hypothesis_id="h-1", category="memory", status="unknown")

    def test_confidence_range(self):
        with pytest.raises(ValidationError):
            Hypothesis(hypothesis_id="h-1", category="memory", confidence=101.0)

    def test_evidence_lists(self):
        sig = EvidenceSignal(
            signal_id="s1", signal_type="log", signal_name="oom_kill",
            source_agent="log_agent",
        )
        h = Hypothesis(
            hypothesis_id="h-1", category="memory",
            evidence_for=[sig], evidence_against=[],
        )
        assert len(h.evidence_for) == 1
        assert h.evidence_for[0].signal_name == "oom_kill"


# ── HypothesisResult ───────────────────────────────────────────────────────

class TestHypothesisResult:
    def test_basic_creation_with_defaults(self):
        result = HypothesisResult()
        assert result.hypotheses == []
        assert result.winner is None
        assert result.status == "resolved"
        assert result.elimination_log == []
        assert result.evidence_timeline == []
        assert result.recommendations == []

    def test_resolved_with_winner(self):
        winner = Hypothesis(hypothesis_id="h-1", category="memory",
                            status="winner", confidence=95.0)
        result = HypothesisResult(
            hypotheses=[winner],
            winner=winner,
            status="resolved",
            recommendations=["Increase memory limit to 2Gi"],
        )
        assert result.status == "resolved"
        assert result.winner.hypothesis_id == "h-1"
        assert len(result.recommendations) == 1

    def test_inconclusive(self):
        h1 = Hypothesis(hypothesis_id="h-1", category="memory",
                        status="eliminated", elimination_reason="no evidence")
        h2 = Hypothesis(hypothesis_id="h-2", category="network",
                        status="eliminated", elimination_reason="no evidence")
        result = HypothesisResult(
            hypotheses=[h1, h2],
            status="inconclusive",
            elimination_log=[
                {"hypothesis_id": "h-1", "reason": "no evidence"},
                {"hypothesis_id": "h-2", "reason": "no evidence"},
            ],
        )
        assert result.status == "inconclusive"
        assert result.winner is None
        assert len(result.elimination_log) == 2

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            HypothesisResult(status="invalid")

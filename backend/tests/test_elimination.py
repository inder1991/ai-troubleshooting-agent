"""Tests for hypothesis elimination engine."""

import uuid

import pytest

from src.models.hypothesis import EvidenceSignal, Hypothesis, HypothesisResult
from src.hypothesis.elimination import (
    COMPETING_MARGIN,
    CONFIDENCE_GAP_THRESHOLD,
    MIN_WINNER_CONFIDENCE,
    evaluate_hypotheses,
    pick_winner_or_inconclusive,
)


def _signal(agent: str = "log_agent") -> EvidenceSignal:
    return EvidenceSignal(
        signal_id=f"s_{uuid.uuid4().hex[:12]}",
        signal_type="log",
        signal_name="test",
        raw_data={},
        source_agent=agent,
    )


# ---------------------------------------------------------------------------
# evaluate_hypotheses
# ---------------------------------------------------------------------------

class TestEvaluation:
    def test_no_evidence_after_2_agents_eliminated(self):
        h1 = Hypothesis(
            hypothesis_id="h1", category="error",
            confidence=60, evidence_for=[_signal()],
        )
        h2 = Hypothesis(
            hypothesis_id="h2", category="timeout",
            confidence=50,
        )
        log = evaluate_hypotheses([h1, h2], agents_completed=2, phase="log")
        assert len(log) == 1
        assert log[0]["hypothesis_id"] == "h2"
        assert "No supporting evidence" in log[0]["reason"]
        assert h2.status == "eliminated"

    def test_confidence_gap_eliminated(self):
        h1 = Hypothesis(hypothesis_id="h1", category="error", confidence=75)
        h2 = Hypothesis(
            hypothesis_id="h2", category="timeout", confidence=30,
            evidence_for=[_signal()],
        )
        log = evaluate_hypotheses([h1, h2], agents_completed=1, phase="metrics")
        assert len(log) == 1
        assert log[0]["hypothesis_id"] == "h2"
        assert "Confidence gap" in log[0]["reason"]
        assert h2.status == "eliminated"

    def test_contradicted_eliminated(self):
        h1 = Hypothesis(
            hypothesis_id="h1", category="error",
            confidence=60, evidence_for=[_signal()],
        )
        h2 = Hypothesis(
            hypothesis_id="h2", category="timeout",
            confidence=55,
            evidence_for=[_signal()],
            evidence_against=[_signal(), _signal(), _signal()],
        )
        log = evaluate_hypotheses([h1, h2], agents_completed=1, phase="log")
        assert len(log) == 1
        assert log[0]["hypothesis_id"] == "h2"
        assert "contradicting" in log[0]["reason"]

    def test_never_kill_all(self):
        h1 = Hypothesis(hypothesis_id="h1", category="error", confidence=10)
        h2 = Hypothesis(hypothesis_id="h2", category="timeout", confidence=5)
        log = evaluate_hypotheses([h1, h2], agents_completed=3, phase="log")
        active = [h for h in [h1, h2] if h.status == "active"]
        assert len(active) >= 1

    def test_single_hypothesis_never_eliminated(self):
        h1 = Hypothesis(hypothesis_id="h1", category="error", confidence=10)
        log = evaluate_hypotheses([h1], agents_completed=5, phase="log")
        assert log == []
        assert h1.status == "active"

    def test_downstream_effect_eliminated(self):
        h1 = Hypothesis(hypothesis_id="h1", category="error", confidence=80)
        h2 = Hypothesis(
            hypothesis_id="h2", category="cascade", confidence=40,
            root_cause_of="h1", evidence_for=[_signal()],
        )
        log = evaluate_hypotheses([h1, h2], agents_completed=1, phase="k8s")
        assert len(log) == 1
        assert log[0]["hypothesis_id"] == "h2"
        assert "Downstream effect" in log[0]["reason"]

    def test_returns_elimination_log(self):
        h1 = Hypothesis(hypothesis_id="h1", category="error", confidence=75)
        h2 = Hypothesis(
            hypothesis_id="h2", category="timeout", confidence=30,
            evidence_for=[_signal()],
        )
        log = evaluate_hypotheses([h1, h2], agents_completed=2, phase="metrics")
        assert len(log) >= 1
        entry = log[0]
        assert "hypothesis_id" in entry
        assert "reason" in entry
        assert "phase" in entry
        assert "confidence" in entry


# ---------------------------------------------------------------------------
# pick_winner_or_inconclusive
# ---------------------------------------------------------------------------

class TestPickWinner:
    def test_resolved_with_clear_winner(self):
        h1 = Hypothesis(hypothesis_id="h1", category="error", confidence=75)
        h2 = Hypothesis(
            hypothesis_id="h2", category="timeout", confidence=20,
            status="eliminated", elimination_reason="gap",
        )
        result = pick_winner_or_inconclusive([h1, h2])
        assert result.status == "resolved"
        assert result.winner is not None
        assert result.winner.hypothesis_id == "h1"

    def test_inconclusive_low_confidence(self):
        h1 = Hypothesis(hypothesis_id="h1", category="error", confidence=30)
        result = pick_winner_or_inconclusive([h1])
        assert result.status == "inconclusive"
        assert result.winner is None
        assert len(result.recommendations) > 0

    def test_inconclusive_competing(self):
        h1 = Hypothesis(hypothesis_id="h1", category="error", confidence=55)
        h2 = Hypothesis(hypothesis_id="h2", category="timeout", confidence=50)
        result = pick_winner_or_inconclusive([h1, h2])
        assert result.status == "inconclusive"
        assert result.winner is None

    def test_empty_hypotheses_inconclusive(self):
        result = pick_winner_or_inconclusive([])
        assert result.status == "inconclusive"
        assert result.winner is None

    def test_winner_gets_winner_status(self):
        h1 = Hypothesis(hypothesis_id="h1", category="error", confidence=75)
        h2 = Hypothesis(
            hypothesis_id="h2", category="timeout", confidence=20,
            status="eliminated",
        )
        result = pick_winner_or_inconclusive([h1, h2])
        assert result.winner.status == "winner"

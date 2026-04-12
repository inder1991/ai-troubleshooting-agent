"""Tests for the deterministic confidence scoring engine."""

import pytest

from src.models.hypothesis import EvidenceSignal, Hypothesis
from src.hypothesis.confidence_engine import compute_confidence


def _signal(signal_type: str, agent: str, strength: float = 1.0) -> EvidenceSignal:
    return EvidenceSignal(
        signal_id="s",
        signal_type=signal_type,
        signal_name="test",
        raw_data={},
        source_agent=agent,
        strength=strength,
    )


class TestNonLinearScoring:
    def test_zero_evidence_zero_confidence(self):
        h = Hypothesis(hypothesis_id="h1", category="test")
        assert compute_confidence(h, total_agents_completed=3) == 0.0

    def test_single_strong_signal(self):
        h = Hypothesis(
            hypothesis_id="h1",
            category="test",
            evidence_for=[_signal("log", "log_agent", 1.0)],
        )
        score = compute_confidence(h, total_agents_completed=3)
        assert 30.0 <= score <= 70.0, f"Single strong signal should be moderate, got {score}"

    def test_diminishing_returns(self):
        h1 = Hypothesis(
            hypothesis_id="h1",
            category="test",
            evidence_for=[_signal("log", "log_agent", 1.0)],
        )
        h5 = Hypothesis(
            hypothesis_id="h5",
            category="test",
            evidence_for=[_signal("log", "log_agent", 1.0)] * 5,
        )
        score_1 = compute_confidence(h1, total_agents_completed=1)
        score_5 = compute_confidence(h5, total_agents_completed=1)
        assert score_5 < score_1 * 3, (
            f"5 signals ({score_5}) should be less than 3x 1 signal ({score_1 * 3})"
        )

    def test_one_strong_beats_five_weak(self):
        h_strong = Hypothesis(
            hypothesis_id="h1",
            category="test",
            evidence_for=[_signal("log", "log_agent", 1.0)],
        )
        h_weak = Hypothesis(
            hypothesis_id="h2",
            category="test",
            evidence_for=[_signal("log", "log_agent", 0.1)] * 5,
        )
        score_strong = compute_confidence(h_strong, total_agents_completed=1)
        score_weak = compute_confidence(h_weak, total_agents_completed=1)
        assert score_strong > score_weak, (
            f"1 strong ({score_strong}) should beat 5 weak ({score_weak})"
        )


class TestAgentAgreement:
    def test_multi_agent_corroboration_boosts(self):
        h_single = Hypothesis(
            hypothesis_id="h1",
            category="test",
            evidence_for=[
                _signal("log", "log_agent", 1.0),
                _signal("log", "log_agent", 1.0),
                _signal("log", "log_agent", 1.0),
            ],
        )
        h_multi = Hypothesis(
            hypothesis_id="h2",
            category="test",
            evidence_for=[
                _signal("log", "log_agent", 1.0),
                _signal("k8s", "k8s_agent", 1.0),
                _signal("metric", "metrics_agent", 1.0),
            ],
        )
        score_single = compute_confidence(h_single, total_agents_completed=3)
        score_multi = compute_confidence(h_multi, total_agents_completed=3)
        assert score_multi > score_single, (
            f"Multi-agent ({score_multi}) should beat single-agent ({score_single})"
        )


class TestContradictions:
    def test_contradiction_reduces(self):
        h_clean = Hypothesis(
            hypothesis_id="h1",
            category="test",
            evidence_for=[_signal("log", "log_agent", 1.0)],
        )
        h_contradicted = Hypothesis(
            hypothesis_id="h2",
            category="test",
            evidence_for=[_signal("log", "log_agent", 1.0)],
            evidence_against=[_signal("k8s", "k8s_agent", 1.0)],
        )
        score_clean = compute_confidence(h_clean, total_agents_completed=2)
        score_contradicted = compute_confidence(h_contradicted, total_agents_completed=2)
        assert score_contradicted < score_clean, (
            f"Contradicted ({score_contradicted}) should be less than clean ({score_clean})"
        )


class TestAgentReliability:
    def test_log_weighted_higher_than_tracing(self):
        h_log = Hypothesis(
            hypothesis_id="h1",
            category="test",
            evidence_for=[_signal("log", "log_agent", 1.0)],
        )
        h_trace = Hypothesis(
            hypothesis_id="h2",
            category="test",
            evidence_for=[_signal("trace", "tracing_agent", 1.0)],
        )
        score_log = compute_confidence(h_log, total_agents_completed=1)
        score_trace = compute_confidence(h_trace, total_agents_completed=1)
        assert score_log > score_trace, (
            f"log_agent ({score_log}) should score higher than tracing_agent ({score_trace})"
        )


class TestBounds:
    def test_never_exceeds_100(self):
        h = Hypothesis(
            hypothesis_id="h1",
            category="test",
            evidence_for=[
                _signal("log", "log_agent", 1.0),
                _signal("k8s", "k8s_agent", 1.0),
                _signal("metric", "metrics_agent", 1.0),
                _signal("trace", "tracing_agent", 1.0),
                _signal("code", "code_agent", 1.0),
                _signal("change", "change_agent", 1.0),
            ],
        )
        score = compute_confidence(h, total_agents_completed=6)
        assert score <= 100.0, f"Score should never exceed 100, got {score}"

    def test_never_below_zero(self):
        h = Hypothesis(
            hypothesis_id="h1",
            category="test",
            evidence_against=[
                _signal("log", "log_agent", 1.0),
                _signal("k8s", "k8s_agent", 1.0),
                _signal("metric", "metrics_agent", 1.0),
            ],
        )
        score = compute_confidence(h, total_agents_completed=3)
        assert score >= 0.0, f"Score should never be below 0, got {score}"

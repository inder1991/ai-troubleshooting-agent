"""Tests for hypothesis data in the V4 findings response."""

import pytest
from unittest.mock import MagicMock, patch
from src.models.hypothesis import Hypothesis, EvidenceSignal, HypothesisResult


def _make_signal(name: str, stype: str = "log", agent: str = "log_agent", strength: float = 0.8):
    return EvidenceSignal(
        signal_id=f"sig-{name}",
        signal_type=stype,
        signal_name=name,
        source_agent=agent,
        strength=strength,
    )


def _make_hypothesis(hid: str, category: str, status: str = "active", confidence: float = 50.0):
    return Hypothesis(
        hypothesis_id=hid,
        category=category,
        status=status,
        confidence=confidence,
    )


def test_hypothesis_evidence_summaries_serialized():
    """evidence_for and evidence_against should include signal summaries."""
    h = _make_hypothesis("h1", "memory", confidence=72.0)
    h.evidence_for = [
        _make_signal("oom_killed", "k8s", "k8s_agent", 0.9),
        _make_signal("high_memory_usage", "metric", "metrics_agent", 0.7),
    ]
    h.evidence_against = [
        _make_signal("low_memory_usage", "metric", "metrics_agent", 0.3),
    ]

    serialized = {
        "hypothesis_id": h.hypothesis_id,
        "category": h.category,
        "status": h.status,
        "confidence": h.confidence,
        "evidence_for_count": len(h.evidence_for),
        "evidence_against_count": len(h.evidence_against),
        "evidence_for": [
            {
                "signal_name": s.signal_name,
                "signal_type": s.signal_type,
                "source_agent": s.source_agent,
                "strength": s.strength,
            }
            for s in h.evidence_for
        ],
        "evidence_against": [
            {
                "signal_name": s.signal_name,
                "signal_type": s.signal_type,
                "source_agent": s.source_agent,
                "strength": s.strength,
            }
            for s in h.evidence_against
        ],
        "downstream_effects": h.downstream_effects,
        "elimination_reason": h.elimination_reason,
        "elimination_phase": h.elimination_phase,
    }

    assert serialized["evidence_for_count"] == 2
    assert serialized["evidence_against_count"] == 1
    assert len(serialized["evidence_for"]) == 2
    assert serialized["evidence_for"][0]["signal_name"] == "oom_killed"
    assert serialized["evidence_for"][0]["source_agent"] == "k8s_agent"
    assert serialized["evidence_against"][0]["signal_name"] == "low_memory_usage"


def test_hypothesis_result_serialization():
    """hypothesis_result should include elimination_log entries with all fields."""
    h_winner = _make_hypothesis("h1", "memory", status="winner", confidence=72.0)
    h_elim = _make_hypothesis("h2", "connection", status="eliminated", confidence=35.0)

    result = HypothesisResult(
        hypotheses=[h_winner, h_elim],
        winner=h_winner,
        status="resolved",
        elimination_log=[
            {
                "hypothesis_id": "h2",
                "reason": "Confidence gap: 35 vs leader 72",
                "phase": "metrics_analyzed",
                "confidence": 35.0,
            }
        ],
        recommendations=[],
    )

    serialized = {
        "status": result.status,
        "winner_id": result.winner.hypothesis_id if result.winner else None,
        "elimination_log": result.elimination_log,
        "recommendations": result.recommendations,
    }

    assert serialized["status"] == "resolved"
    assert serialized["winner_id"] == "h1"
    assert len(serialized["elimination_log"]) == 1
    assert serialized["elimination_log"][0]["hypothesis_id"] == "h2"
    assert serialized["elimination_log"][0]["phase"] == "metrics_analyzed"

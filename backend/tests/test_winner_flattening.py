"""Tests for winner hypothesis flattening into V4Findings error_patterns."""

import pytest
from src.models.hypothesis import Hypothesis, HypothesisResult


def _make_hypothesis(hid, category, status="active", confidence=50.0, patterns=None):
    return Hypothesis(
        hypothesis_id=hid,
        category=category,
        status=status,
        confidence=confidence,
        source_patterns=patterns or [],
    )


def _flatten_winner_patterns(hypotheses, hypothesis_result):
    """Reproduce the flattening logic to test it independently."""
    extra_patterns = []
    if hypothesis_result and hypothesis_result.status == "resolved" and hypothesis_result.winner:
        winner = hypothesis_result.winner
        for p in winner.source_patterns:
            if isinstance(p, dict) and "pattern_id" in p:
                flat = dict(p)
                flat["causal_role"] = "root_cause"
                extra_patterns.append(flat)

        for h in hypotheses:
            if h.status == "eliminated":
                for p in h.source_patterns:
                    if isinstance(p, dict) and "pattern_id" in p:
                        flat = dict(p)
                        flat["causal_role"] = "correlated_anomaly"
                        extra_patterns.append(flat)

    return extra_patterns


def test_winner_patterns_get_root_cause_role():
    winner = _make_hypothesis("h1", "memory", "winner", 72.0, patterns=[
        {"pattern_id": "p1", "exception_type": "OOMKilled", "severity": "critical", "count": 5},
    ])
    elim = _make_hypothesis("h2", "connection", "eliminated", 35.0, patterns=[
        {"pattern_id": "p2", "exception_type": "ConnectionTimeout", "severity": "medium", "count": 3},
    ])
    result = HypothesisResult(
        hypotheses=[winner, elim],
        winner=winner,
        status="resolved",
    )

    extra = _flatten_winner_patterns([winner, elim], result)
    assert len(extra) == 2
    assert extra[0]["causal_role"] == "root_cause"
    assert extra[0]["exception_type"] == "OOMKilled"
    assert extra[1]["causal_role"] == "correlated_anomaly"
    assert extra[1]["exception_type"] == "ConnectionTimeout"


def test_no_flattening_when_inconclusive():
    h1 = _make_hypothesis("h1", "memory", "active", 45.0, patterns=[
        {"pattern_id": "p1", "exception_type": "OOMKilled", "severity": "critical", "count": 5},
    ])
    result = HypothesisResult(
        hypotheses=[h1],
        status="inconclusive",
    )
    extra = _flatten_winner_patterns([h1], result)
    assert len(extra) == 0


def test_no_flattening_when_no_result():
    extra = _flatten_winner_patterns([], None)
    assert len(extra) == 0


def test_skips_non_dict_patterns():
    winner = _make_hypothesis("h1", "memory", "winner", 72.0, patterns=["raw string pattern"])
    result = HypothesisResult(hypotheses=[winner], winner=winner, status="resolved")
    extra = _flatten_winner_patterns([winner], result)
    assert len(extra) == 0

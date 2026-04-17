"""Task 4.3 — signature matcher fast-path."""
from __future__ import annotations

from src.agents.orchestration.signature_matcher import (
    SignatureHypothesis,
    try_signature_match,
)
from src.patterns import OOM_CASCADE, Signal


def sig(kind: str, t: float, service: str = "payment") -> Signal:
    return Signal(kind=kind, t=t, service=service)


def _oom_signals(service: str = "payment") -> list[Signal]:
    return [
        sig("memory_pressure", t=0, service=service),
        sig("oom_killed", t=60, service=service),
        sig("pod_restart", t=70, service=service),
        sig("error_rate_spike", t=90, service=service),
    ]


class TestFastPath:
    def test_high_confidence_match_returns_hypothesis(self):
        hyp = try_signature_match(_oom_signals())
        assert hyp is not None
        assert hyp.pattern_name == "oom_cascade"
        assert hyp.confidence >= 0.70

    def test_no_signals_returns_none(self):
        assert try_signature_match([]) is None

    def test_no_match_returns_none(self):
        signals = [sig("error_rate_spike", t=0)]
        assert try_signature_match(signals) is None

    def test_summary_interpolates_service_name(self):
        hyp = try_signature_match(_oom_signals(service="checkout"))
        assert hyp is not None
        assert "checkout" in hyp.summary

    def test_suggested_remediation_propagates(self):
        hyp = try_signature_match(_oom_signals())
        assert hyp is not None
        assert hyp.suggested_remediation is not None
        assert "memory" in hyp.suggested_remediation.lower()

    def test_only_matches_above_floor(self):
        # Match floor 0.99 means nothing qualifies even for high-confidence patterns.
        assert try_signature_match(_oom_signals(), match_floor=0.99) is None


class TestDeterminism:
    def test_same_signals_same_pattern(self):
        signals = _oom_signals()
        h1 = try_signature_match(signals)
        h2 = try_signature_match(signals)
        assert h1 == h2

    def test_multiple_matches_picks_highest_confidence_then_name(self):
        # Use a minimal library with two patterns both tied at the floor;
        # tiebreak on name, alphabetical.
        from src.patterns.schema import SignaturePattern, TemporalRule

        A = SignaturePattern(
            name="a_pattern",
            required_signals=("error_rate_spike",),
            confidence_floor=0.70,
            summary_template="a on {service}",
        )
        Z = SignaturePattern(
            name="z_pattern",
            required_signals=("error_rate_spike",),
            confidence_floor=0.70,
            summary_template="z on {service}",
        )
        hyp = try_signature_match(
            [sig("error_rate_spike", t=0)],
            library=(A, Z),
        )
        assert hyp is not None
        assert hyp.pattern_name == "a_pattern"

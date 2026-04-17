"""Task 4.6 — pure eval metrics."""
from __future__ import annotations

import pytest

from eval.metrics import (
    Case,
    EvalReport,
    build_report,
    ece,
    high_confidence_wrong_count,
    top1_accuracy,
)


class TestTop1:
    def test_empty_corpus_returns_zero(self):
        assert top1_accuracy([]) == 0.0

    def test_all_correct_is_100pct(self):
        cases = [Case(predicted="x", labelled="x"), Case(predicted="y", labelled="y")]
        assert top1_accuracy(cases) == 1.0

    def test_all_wrong_is_zero(self):
        cases = [Case(predicted="a", labelled="x"), Case(predicted="b", labelled="y")]
        assert top1_accuracy(cases) == 0.0

    def test_counts_match_against_acceptable_alternates(self):
        cases = [
            Case(predicted="x", labelled="x"),
            Case(predicted="z", labelled="y", alternates=("z",)),
        ]
        assert top1_accuracy(cases) == 1.0

    def test_rounding_to_4dp(self):
        cases = [Case(predicted="x", labelled="x")] * 1 + [Case(predicted="a", labelled="b")] * 2
        # 1/3 = 0.3333...
        assert top1_accuracy(cases) == 0.3333


class TestECE:
    def test_empty_returns_zero(self):
        assert ece([]) == 0.0

    def test_perfect_calibration_near_zero(self):
        # 9 correct + 1 wrong, all predicted at 0.9 -> acc=0.9, conf=0.9 -> ECE=0
        cases = [Case(predicted="x", labelled="x", predicted_confidence=0.9)] * 9
        cases += [Case(predicted="x", labelled="y", predicted_confidence=0.9)]
        assert ece(cases, bins=10) == pytest.approx(0.0, abs=0.05)

    def test_overconfident_high_ece(self):
        # Model says 0.9 confident but is wrong every time -> ECE ~ 0.9
        cases = [Case(predicted="x", labelled="y", predicted_confidence=0.9)] * 10
        assert ece(cases, bins=10) > 0.7

    def test_confidence_clamped_to_0_1_range(self):
        # Even with out-of-range confidences, the function shouldn't crash.
        cases = [
            Case(predicted="x", labelled="x", predicted_confidence=1.5),
            Case(predicted="x", labelled="y", predicted_confidence=-0.3),
        ]
        assert 0.0 <= ece(cases) <= 1.0


class TestHighConfWrong:
    def test_zero_when_all_right(self):
        cases = [Case(predicted="x", labelled="x", predicted_confidence=0.95)] * 5
        assert high_confidence_wrong_count(cases) == 0

    def test_counts_only_above_threshold(self):
        cases = [
            Case(predicted="a", labelled="b", predicted_confidence=0.95),   # 1
            Case(predicted="a", labelled="b", predicted_confidence=0.50),   # not above threshold
            Case(predicted="a", labelled="b", predicted_confidence=0.72),   # 1
        ]
        assert high_confidence_wrong_count(cases, threshold=0.70) == 2

    def test_configurable_threshold(self):
        cases = [
            Case(predicted="a", labelled="b", predicted_confidence=0.50),
            Case(predicted="a", labelled="b", predicted_confidence=0.90),
        ]
        assert high_confidence_wrong_count(cases, threshold=0.40) == 2


class TestReport:
    def test_build_report_has_every_field(self):
        cases = [Case(predicted="x", labelled="x", predicted_confidence=0.8)]
        r = build_report(cases)
        assert isinstance(r, EvalReport)
        assert r.total_cases == 1
        assert r.top1_accuracy == 1.0
        assert r.high_confidence_wrong_count == 0

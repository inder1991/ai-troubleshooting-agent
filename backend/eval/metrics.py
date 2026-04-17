"""Eval metrics — pure scoring functions.

Corpus-independent. Given a list of graded cases (predicted vs labelled
answer + model confidence + correctness), produce top-1 accuracy and
expected calibration error (ECE). These functions power the replay harness
in ``runner.py`` and the regression gate in ``.github/workflows/nightly-eval.yml``.

Kept pure so tests don't need a labelled corpus and the runner can use
them against synthetic cases during CI bring-up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Case:
    """One graded eval case.

    ``predicted`` and ``labelled`` are the canonical strings (typically
    pattern names or short root-cause categories). ``alternates`` lets a
    case accept multiple valid answers — useful when the incident has
    two equally-defensible root-cause framings.
    """

    predicted: str = ""
    labelled: str = ""
    alternates: tuple[str, ...] = ()
    predicted_confidence: float = 0.0
    correct: bool | None = None  # derived if None


def _is_correct(c: Case) -> bool:
    if c.correct is not None:
        return c.correct
    if c.predicted == c.labelled:
        return True
    return c.predicted in c.alternates


def top1_accuracy(cases: Sequence[Case]) -> float:
    """Fraction of cases where predicted matches labelled (or an alternate)."""
    if not cases:
        return 0.0
    correct = sum(1 for c in cases if _is_correct(c))
    return round(correct / len(cases), 4)


def ece(cases: Sequence[Case], *, bins: int = 10) -> float:
    """Expected calibration error over equal-width bins of confidence.

    For each bin, ``|acc(bin) - mean_conf(bin)|`` weighted by bin fraction;
    summed. Returns 0 when all confidences fall in bins where accuracy
    matches mean confidence.
    """
    if not cases or bins < 1:
        return 0.0
    total = len(cases)
    bin_sums_conf: list[float] = [0.0] * bins
    bin_sums_correct: list[int] = [0] * bins
    bin_counts: list[int] = [0] * bins
    for c in cases:
        conf = min(max(c.predicted_confidence, 0.0), 1.0)
        idx = min(int(conf * bins), bins - 1)
        bin_counts[idx] += 1
        bin_sums_conf[idx] += conf
        bin_sums_correct[idx] += 1 if _is_correct(c) else 0
    e = 0.0
    for i in range(bins):
        n = bin_counts[i]
        if n == 0:
            continue
        mean_conf = bin_sums_conf[i] / n
        acc = bin_sums_correct[i] / n
        e += (n / total) * abs(mean_conf - acc)
    return round(e, 4)


def high_confidence_wrong_count(cases: Sequence[Case], *, threshold: float = 0.70) -> int:
    """How many cases claim confidence >= threshold but were wrong.

    This is the single most actionable miscalibration signal — the system
    should never be confidently wrong. Any non-zero value is a regression.
    """
    return sum(
        1
        for c in cases
        if c.predicted_confidence >= threshold and not _is_correct(c)
    )


@dataclass(frozen=True)
class EvalReport:
    top1_accuracy: float
    ece: float
    high_confidence_wrong_count: int
    total_cases: int


def build_report(cases: Sequence[Case]) -> EvalReport:
    return EvalReport(
        top1_accuracy=top1_accuracy(cases),
        ece=ece(cases, bins=10),
        high_confidence_wrong_count=high_confidence_wrong_count(cases),
        total_cases=len(cases),
    )

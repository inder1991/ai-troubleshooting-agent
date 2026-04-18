"""Candidate-trace ranking for trace mining.

When the user doesn't have a specific ``trace_id``, we ask the backend for
candidate traces matching the incident shape (service + time window ± filters)
and pick the most diagnostically valuable ones to analyze.

Scoring is deterministic: error presence > latency outlier > causal depth.
The top-N (typically 3) survive to full ``get_trace()`` + analysis.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Literal

from src.models.schemas import TraceSummary


@dataclass
class RankedTrace:
    summary: TraceSummary
    score: float
    reasons: list[str]


@dataclass
class RankerConfig:
    """Weights — operator-tunable per integration if needed."""

    error_weight: float = 10.0
    latency_z_weight: float = 2.0
    depth_weight: float = 1.0
    # How many to return after ranking.
    top_n: int = 3
    # Require at least 1 error-carrying trace in the top-N when symptom is
    # error-shaped, padding with latency outliers otherwise.
    prefer_error_traces_when_available: bool = True


@dataclass
class SymptomHints:
    """What the user is actually investigating — drives ranking."""

    expecting_errors: bool = False  # 500s, timeouts, exceptions
    expecting_slowness: bool = False  # latency regression
    known_error_keywords: list[str] = None  # type: ignore[assignment]


class TraceRanker:
    def __init__(self, config: RankerConfig | None = None) -> None:
        self._cfg = config or RankerConfig()

    def rank(
        self,
        candidates: list[TraceSummary],
        hints: SymptomHints | None = None,
    ) -> list[RankedTrace]:
        if not candidates:
            return []

        hints = hints or SymptomHints(expecting_errors=True)

        # Pre-compute latency stats so z-scoring is meaningful.
        durations = [c.duration_ms for c in candidates]
        mean_dur = statistics.fmean(durations) if durations else 0.0
        stdev_dur = statistics.pstdev(durations) if len(durations) > 1 else 0.0

        max_span_count = max((c.span_count for c in candidates), default=1) or 1

        ranked = [
            self._score_one(c, mean_dur, stdev_dur, max_span_count, hints)
            for c in candidates
        ]

        ranked.sort(key=lambda r: r.score, reverse=True)
        return self._apply_top_n_policy(ranked, hints)

    # ── Internals ────────────────────────────────────────────────────────

    def _score_one(
        self,
        c: TraceSummary,
        mean_dur: float,
        stdev_dur: float,
        max_span_count: int,
        hints: SymptomHints,
    ) -> RankedTrace:
        reasons: list[str] = []
        score = 0.0

        if c.has_error:
            score += self._cfg.error_weight * c.error_count
            reasons.append(f"has {c.error_count} error-carrying spans")

        if stdev_dur > 0:
            z = (c.duration_ms - mean_dur) / stdev_dur
            if z > 0:
                score += self._cfg.latency_z_weight * z
                reasons.append(f"latency z-score +{z:.2f} vs peers")

        depth_ratio = c.span_count / max_span_count
        score += self._cfg.depth_weight * depth_ratio
        if depth_ratio > 0.7:
            reasons.append(f"high causal depth ({c.span_count} spans)")

        if hints.expecting_errors and not c.has_error:
            # Demote error-free traces when the symptom is error-shaped.
            score *= 0.5
            reasons.append("demoted: no errors (symptom is error-shaped)")

        return RankedTrace(summary=c, score=score, reasons=reasons)

    def _apply_top_n_policy(
        self, ranked: list[RankedTrace], hints: SymptomHints
    ) -> list[RankedTrace]:
        n = self._cfg.top_n
        if len(ranked) <= n:
            return ranked

        if not self._cfg.prefer_error_traces_when_available:
            return ranked[:n]

        # Ensure error-carrying traces are represented when any exist.
        error_carrying = [r for r in ranked if r.summary.has_error]
        if not error_carrying:
            return ranked[:n]

        # Take the top (n-1) overall + at least 1 error-carrying if missing from that set.
        picks = list(ranked[:n])
        if not any(r.summary.has_error for r in picks):
            picks[-1] = error_carrying[0]
        return picks

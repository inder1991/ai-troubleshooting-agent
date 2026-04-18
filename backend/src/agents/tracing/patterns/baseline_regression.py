"""Baseline-aware latency regression detector.

Shape:
  span's observed duration exceeds the service+operation's historical P99.
  Moves diagnostic weight from "this span is 4s" → "this span is 4s but
  it's NORMALLY 200ms" — a 20× anomaly.

The baseline lookup hits a ``TraceLatencyBaseline`` table:

  service_name : str
  operation_name : str
  p99_ms_7d : float
  sample_count : int
  updated_at : datetime

When no baseline row exists for a given (service, op) we degrade gracefully
— the detector returns no findings for that span. A follow-up PR
(TA-PR2b) will ship the populator that writes this table from the outbox
on a 5-min cadence.

Rule:
  - z-score ≥ 3.0 (observed >> baseline P99)
  - OR duration > 2.5 × baseline P99

Severity:
  z 3-5 or 2.5-4× baseline    medium
  z 5-10 or 4-8×              high
  z > 10 or >8×               critical
"""
from __future__ import annotations

from typing import Callable, Optional

from src.models.schemas import LatencyRegressionHint, PatternFinding, SpanInfo


# Injectable baseline-fetcher function. Signature:
#   (service_name, operation_name) -> (p99_ms, sample_count) or None
BaselineFetcher = Callable[[str, str], Optional[tuple[float, int]]]


_Z_THRESHOLD = 3.0
_RATIO_THRESHOLD = 2.5


class BaselineRegressionDetector:
    kind = "baseline_latency_regression"

    def __init__(self, fetcher: Optional[BaselineFetcher] = None) -> None:
        """``fetcher`` is injectable so tests bypass the DB. When None, the
        detector returns no findings (gracefully degrades)."""
        self._fetcher = fetcher

    def detect(self, spans: list[SpanInfo]) -> list[PatternFinding]:
        if not spans or self._fetcher is None:
            return []

        findings: list[PatternFinding] = []
        for span in spans:
            baseline = self._fetcher(span.service_name, span.operation_name)
            if baseline is None:
                continue
            p99_ms, sample_count = baseline
            if p99_ms <= 0 or sample_count < 10:
                # Baseline is unreliable — skip.
                continue

            ratio = span.duration_ms / p99_ms
            # Z-score is approximate — assume stdev ~= p99_ms/3 (log-normal thumb rule).
            approx_stdev = p99_ms / 3.0
            z = (span.duration_ms - p99_ms) / approx_stdev if approx_stdev else 0.0

            if ratio < _RATIO_THRESHOLD and z < _Z_THRESHOLD:
                continue

            severity = _severity(ratio, z)
            findings.append(
                PatternFinding(
                    kind="baseline_latency_regression",
                    confidence=_confidence(ratio, z, sample_count),
                    severity=severity,
                    human_summary=(
                        f"Latency regression: {span.service_name}/"
                        f"{span.operation_name} observed {span.duration_ms:.0f}ms "
                        f"vs historical P99 of {p99_ms:.0f}ms ({ratio:.1f}× slower, "
                        f"z-score ≈ {z:.1f}). Based on {sample_count} recent samples."
                    ),
                    span_ids_involved=[span.span_id],
                    service_name=span.service_name,
                    metadata={
                        "operation": span.operation_name,
                        "observed_duration_ms": round(span.duration_ms, 2),
                        "baseline_p99_ms": round(p99_ms, 2),
                        "ratio": round(ratio, 2),
                        "z_score": round(z, 2),
                        "baseline_sample_count": sample_count,
                    },
                )
            )
        return findings

    def as_hints(self, findings: list[PatternFinding]) -> list[LatencyRegressionHint]:
        """Convert findings → handoff hints consumed by metrics_agent."""
        out: list[LatencyRegressionHint] = []
        for f in findings:
            if f.kind != "baseline_latency_regression":
                continue
            meta = f.metadata
            out.append(
                LatencyRegressionHint(
                    service_name=f.service_name,
                    operation_name=meta.get("operation", ""),
                    observed_duration_ms=float(meta.get("observed_duration_ms", 0.0)),
                    baseline_p99_ms=float(meta.get("baseline_p99_ms", 0.0)),
                    z_score=float(meta.get("z_score", 0.0)),
                    baseline_source="trace_history",
                )
            )
        return out


# ── helpers ──────────────────────────────────────────────────────────────


def _severity(ratio: float, z: float) -> str:
    if ratio >= 8.0 or z >= 10.0:
        return "critical"
    if ratio >= 4.0 or z >= 5.0:
        return "high"
    return "medium"


def _confidence(ratio: float, z: float, sample_count: int) -> int:
    # More samples → more confidence in baseline; bigger anomaly → more
    # confidence in the regression call.
    base = 60 + min(int((ratio - 2.5) * 4), 25)
    sample_bonus = min((sample_count - 10) // 50, 10)
    return min(base + sample_bonus, 95)

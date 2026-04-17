"""24h baseline filter for metric anomalies (Task 1.13).

Before a metric spike is reported as an anomaly, it must be compared
to its own 24h-earlier baseline. A peak within ``threshold_pct`` of
baseline is signal-indistinguishable from normal load and must be
suppressed — reporting every within-noise deviation floods downstream
causal analysis with false positives.

The plan's ``fetch_baseline(query, offset_hours)`` helper that issues
``<query> offset <H>h`` is deferred to when we wire the live
Prometheus client; ``apply_baseline_filter`` here operates on the
MetricAnomaly records that already carry ``baseline_value`` /
``peak_value``.
"""
from __future__ import annotations

from src.models.schemas import MetricAnomaly


DEFAULT_BASELINE_THRESHOLD_PCT = 15


def _absolute_deviation_percent(peak: float, baseline: float) -> float:
    """Return |peak - baseline| / baseline * 100. Zero-baseline is
    treated as new-signal: any non-zero peak returns 100.0 so the
    anomaly is always kept; zero-over-zero returns 0.0 so it's
    suppressed by any positive threshold."""
    if baseline == 0:
        return 100.0 if peak != 0 else 0.0
    return abs(peak - baseline) / abs(baseline) * 100.0


def apply_baseline_filter(
    findings: list[MetricAnomaly],
    *,
    threshold_pct: float = DEFAULT_BASELINE_THRESHOLD_PCT,
) -> list[MetricAnomaly]:
    """Drop any finding whose peak is within ``threshold_pct`` (absolute
    percentage deviation) of its baseline. Returns a NEW list; input
    is not mutated."""
    if threshold_pct < 0:
        raise ValueError(f"threshold_pct {threshold_pct} must be >= 0")

    kept: list[MetricAnomaly] = []
    for f in findings:
        delta_pct = _absolute_deviation_percent(f.peak_value, f.baseline_value)
        if delta_pct >= threshold_pct:
            kept.append(f)
    return kept


def apply_baseline_filter_dicts(
    findings: list[dict],
    *,
    threshold_pct: float = DEFAULT_BASELINE_THRESHOLD_PCT,
) -> list[dict]:
    """Dict-keyed variant of ``apply_baseline_filter``. Used where the
    anomalies stream exists as LLM-output dicts (metrics_agent) rather
    than fully-typed MetricAnomaly instances. Each dict must have
    ``peak_value`` and ``baseline_value``; annotates survivors with
    ``baseline_delta_pct``. Findings missing either field are kept
    (can't assess — deferred to downstream validation)."""
    if threshold_pct < 0:
        raise ValueError(f"threshold_pct {threshold_pct} must be >= 0")

    kept: list[dict] = []
    for f in findings:
        peak = f.get("peak_value")
        baseline = f.get("baseline_value")
        if peak is None or baseline is None:
            kept.append(f)
            continue
        try:
            delta_pct = _absolute_deviation_percent(float(peak), float(baseline))
        except (TypeError, ValueError):
            kept.append(f)
            continue
        if delta_pct >= threshold_pct:
            annotated = dict(f)
            annotated["baseline_delta_pct"] = round(delta_pct, 1)
            kept.append(annotated)
    return kept

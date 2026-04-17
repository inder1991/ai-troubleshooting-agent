"""Task 1.13 — Mandatory 24h baseline compare for metric anomalies.

Agents were reporting "CPU at 82%" as critical without checking
whether 82% was actually anomalous for this service. For many
services, 82% CPU is their baseline load. Suppressing within-noise
anomalies (absolute deviation < ``threshold_pct``) cuts false-positive
findings that pollute downstream causal analysis.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.models.schemas import MetricAnomaly


def _anomaly(value: float, baseline: float, *, metric: str = "cpu_utilisation_percent") -> MetricAnomaly:
    now = datetime(2026, 4, 17, tzinfo=timezone.utc)
    return MetricAnomaly(
        metric_name=metric,
        promql_query=f'avg({metric}{{namespace="x"}})',
        baseline_value=baseline,
        peak_value=value,
        spike_start=now,
        spike_end=now,
        severity="high",
        correlation_to_incident="n/a",
        confidence_score=70,
    )


def test_anomaly_suppressed_when_within_threshold():
    """82 vs 78 baseline is +5.1%; threshold=15% → suppressed."""
    from src.agents.baseline import apply_baseline_filter

    out = apply_baseline_filter([_anomaly(82, 78)], threshold_pct=15)
    assert out == []


def test_anomaly_kept_when_above_threshold():
    """180 vs 80 baseline is +125%; well above 15% threshold."""
    from src.agents.baseline import apply_baseline_filter

    out = apply_baseline_filter([_anomaly(180, 80)], threshold_pct=15)
    assert len(out) == 1
    # Deviation rounding may give us 124.9 or 125.0 depending on float
    # representation — assert within a tolerance.
    assert 124 <= out[0].deviation_percent <= 126


def test_decrease_below_threshold_suppressed():
    """Value dropping 10% is below the 15% threshold — suppress."""
    from src.agents.baseline import apply_baseline_filter

    out = apply_baseline_filter([_anomaly(90, 100)], threshold_pct=15)
    assert out == []


def test_large_decrease_kept():
    """50 vs 100 baseline = -50%; absolute deviation > threshold."""
    from src.agents.baseline import apply_baseline_filter

    out = apply_baseline_filter([_anomaly(50, 100)], threshold_pct=15)
    assert len(out) == 1


def test_zero_baseline_keeps_nonzero_peak():
    """0 baseline with non-zero peak is a brand-new signal — keep it."""
    from src.agents.baseline import apply_baseline_filter

    out = apply_baseline_filter([_anomaly(15, 0)], threshold_pct=15)
    assert len(out) == 1


def test_zero_baseline_zero_peak_suppressed():
    from src.agents.baseline import apply_baseline_filter

    out = apply_baseline_filter([_anomaly(0, 0)], threshold_pct=15)
    assert out == []


def test_mixed_list_partial_suppress():
    from src.agents.baseline import apply_baseline_filter

    findings = [
        _anomaly(82, 78, metric="cpu_a"),          # noise, suppress
        _anomaly(500, 100, metric="cpu_b"),        # keep
        _anomaly(101, 100, metric="cpu_c"),        # noise, suppress
    ]
    out = apply_baseline_filter(findings, threshold_pct=15)
    assert len(out) == 1
    assert out[0].metric_name == "cpu_b"


def test_threshold_zero_keeps_everything():
    from src.agents.baseline import apply_baseline_filter

    out = apply_baseline_filter([_anomaly(82, 78)], threshold_pct=0)
    assert len(out) == 1


def test_threshold_negative_rejected():
    from src.agents.baseline import apply_baseline_filter

    with pytest.raises(ValueError):
        apply_baseline_filter([_anomaly(82, 78)], threshold_pct=-1)

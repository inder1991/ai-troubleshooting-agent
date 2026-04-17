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


# ── Dual-baseline (24h + 7d) ────────────────────────────────────────────


def test_dual_baseline_catches_slow_drift_incident():
    """Slow memory-leak case: current=92, 24h baseline=90 (already
    degraded), 7d baseline=50 (healthy). The 24h delta alone is 2%
    which looks like noise, but the 7d delta is 84% — the anomaly
    MUST be kept. Take max(delta_24h, delta_7d)."""
    from src.agents.baseline import apply_baseline_filter_dicts

    findings = [{
        "metric_name": "memory_percent",
        "peak_value": 92.0,
        "baseline_value": 90.0,      # 24h baseline — also degraded
        "baseline_value_7d": 50.0,   # 7d baseline — healthy reference
    }]
    out = apply_baseline_filter_dicts(findings, threshold_pct=15)
    assert len(out) == 1
    # The annotated delta reflects the larger (7d) deviation.
    assert out[0]["baseline_delta_pct"] >= 80


def test_dual_baseline_recent_spike_uses_24h():
    """Fresh spike: current=180, 24h baseline=80 (+125%), 7d baseline
    ~80 too. Either baseline catches it; the max is still > threshold."""
    from src.agents.baseline import apply_baseline_filter_dicts

    findings = [{
        "metric_name": "error_rate",
        "peak_value": 180.0,
        "baseline_value": 80.0,
        "baseline_value_7d": 82.0,
    }]
    out = apply_baseline_filter_dicts(findings, threshold_pct=15)
    assert len(out) == 1
    assert out[0]["baseline_delta_pct"] >= 100


def test_dual_baseline_both_near_current_suppressed():
    """True non-event: current matches both 24h and 7d baselines."""
    from src.agents.baseline import apply_baseline_filter_dicts

    findings = [{
        "metric_name": "cpu_percent",
        "peak_value": 82.0,
        "baseline_value": 80.0,
        "baseline_value_7d": 78.0,
    }]
    out = apply_baseline_filter_dicts(findings, threshold_pct=15)
    assert out == []


def test_dual_baseline_missing_7d_falls_back_to_24h():
    """Back-compat: findings without baseline_value_7d still work."""
    from src.agents.baseline import apply_baseline_filter_dicts

    findings = [{
        "metric_name": "cpu_percent",
        "peak_value": 180.0,
        "baseline_value": 80.0,
        # no baseline_value_7d
    }]
    out = apply_baseline_filter_dicts(findings, threshold_pct=15)
    assert len(out) == 1

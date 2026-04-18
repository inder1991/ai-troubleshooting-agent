"""trace_baseline_populator unit tests.

The DB-facing ``populate_once`` is covered via _harvest_spans + _p99 pure
helpers; the full DB round-trip is covered by the integration test suite
that spins up a real Postgres.
"""
from __future__ import annotations

from src.workers.trace_baseline_populator import (
    MIN_SAMPLE_COUNT,
    _harvest_spans,
    _p99,
)


# ── _harvest_spans ────────────────────────────────────────────────────


def test_harvest_empty_payload():
    buckets: dict = {}
    _harvest_spans({}, buckets)
    assert buckets == {}


def test_harvest_none_payload():
    buckets: dict = {}
    _harvest_spans(None, buckets)
    assert buckets == {}


def test_harvest_missing_trace_analysis():
    buckets: dict = {}
    _harvest_spans({"some_other_field": "x"}, buckets)
    assert buckets == {}


def test_harvest_extracts_per_service_operation():
    buckets: dict = {}
    payload = {
        "trace_analysis": {
            "call_chain": [
                {"service_name": "api", "operation_name": "GET /x", "duration_ms": 10.0},
                {"service_name": "api", "operation_name": "GET /x", "duration_ms": 12.0},
                {"service_name": "db", "operation_name": "SELECT", "duration_ms": 50.0},
            ],
        },
    }
    _harvest_spans(payload, buckets)
    assert buckets[("api", "GET /x")] == [10.0, 12.0]
    assert buckets[("db", "SELECT")] == [50.0]


def test_harvest_accepts_legacy_service_field():
    """Some older payloads use ``service`` / ``operation`` instead of
    ``service_name`` / ``operation_name`` — should still harvest."""
    buckets: dict = {}
    payload = {
        "trace_analysis": {
            "call_chain": [
                {"service": "legacy", "operation": "do", "duration_ms": 5.0},
            ],
        },
    }
    _harvest_spans(payload, buckets)
    assert buckets[("legacy", "do")] == [5.0]


def test_harvest_skips_invalid_spans():
    buckets: dict = {}
    payload = {
        "trace_analysis": {
            "call_chain": [
                {"service_name": "ok", "operation_name": "op", "duration_ms": 1.0},
                {"service_name": "", "operation_name": "op", "duration_ms": 1.0},  # empty svc
                {"service_name": "s", "operation_name": None, "duration_ms": 1.0},  # no op
                {"service_name": "s", "operation_name": "op", "duration_ms": -1.0},  # bad dur
                {"service_name": "s", "operation_name": "op", "duration_ms": "bad"},  # wrong type
            ],
        },
    }
    _harvest_spans(payload, buckets)
    assert buckets == {("ok", "op"): [1.0]}


def test_harvest_accumulates_across_calls():
    """Calling _harvest_spans repeatedly should extend the same buckets."""
    buckets: dict = {}
    p1 = {"trace_analysis": {"call_chain": [{"service_name": "x", "operation_name": "y", "duration_ms": 1.0}]}}
    p2 = {"trace_analysis": {"call_chain": [{"service_name": "x", "operation_name": "y", "duration_ms": 2.0}]}}
    _harvest_spans(p1, buckets)
    _harvest_spans(p2, buckets)
    assert buckets[("x", "y")] == [1.0, 2.0]


# ── _p99 ─────────────────────────────────────────────────────────────


def test_p99_tiny_samples_falls_back_to_max():
    assert _p99([10.0]) == 10.0
    assert _p99([10.0, 20.0]) == 20.0


def test_p99_larger_sample_picks_99th_percentile():
    # 100 durations 1..100 → P99 should be 99 (inclusive).
    durations = [float(i) for i in range(1, 101)]
    p = _p99(durations)
    assert 98.0 <= p <= 100.0


def test_p99_robust_to_outliers():
    # 50 values at 10ms + 1 outlier at 9999ms — P99 should be dominated
    # by the population, not the outlier (outlier IS the P99 row, but only
    # because there's so few samples — semantics match documented behavior).
    durations = [10.0] * 50 + [9999.0]
    p = _p99(durations)
    # With 51 samples, P99 index = floor(0.99 * 51) - 1 = 49 → durations[49] = 10.
    # The outlier is at index 50 (100%ile), not 99%ile.
    assert p == 10.0


# ── Threshold semantics ──────────────────────────────────────────────


def test_min_sample_count_exposed_constant():
    """The detector's gate + the populator's floor must agree. Lock it."""
    assert MIN_SAMPLE_COUNT == 10

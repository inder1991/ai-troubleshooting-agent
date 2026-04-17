"""Task 1.11 — PromQL safety middleware.

A planner hallucinating ``count_over_time(my_metric[1y])`` will return
hundreds of thousands of points, stall Prometheus, and DOS the
investigation. The validator rejects unsafe queries before dispatch:

- Namespace label required — prevents cluster-wide scans.
- Range × step-derived cardinality capped at 100k points.
- Range capped at 7 days.
- Step minimum 60s — one-second step over a day is 86k points per
  series and blows up cardinality.
- Query length capped so attacker-controlled PromQL from logs can't
  exfiltrate.
"""
from __future__ import annotations

import pytest


def test_reject_query_without_namespace_label():
    from src.tools.promql_safety import validate_promql, UnsafeQuery

    with pytest.raises(UnsafeQuery, match="namespace"):
        validate_promql('rate(http_requests_total[5m])')


def test_reject_range_too_long_for_step():
    """7d range with 1s step = 604800 points per series → well over cap."""
    from src.tools.promql_safety import validate_promql, UnsafeQuery

    with pytest.raises(UnsafeQuery, match="cardinality"):
        validate_promql('rate(http_requests_total{namespace="payments"}[7d])', step_s=1)


def test_reject_count_over_time_year_range():
    from src.tools.promql_safety import validate_promql, UnsafeQuery

    with pytest.raises(UnsafeQuery, match="range"):
        validate_promql('count_over_time(my_metric{namespace="x"}[1y])')


def test_accept_well_bounded_query():
    from src.tools.promql_safety import validate_promql

    # Should not raise.
    validate_promql(
        'rate(http_requests_total{namespace="payments",service="api"}[5m])',
        step_s=60,
        range_h=1,
    )


def test_reject_step_below_minimum():
    from src.tools.promql_safety import validate_promql, UnsafeQuery

    with pytest.raises(UnsafeQuery, match="step"):
        validate_promql(
            'rate(http_requests_total{namespace="payments"}[1h])',
            step_s=1,
        )


def test_reject_excessively_long_query_string():
    """Attacker-controlled PromQL (via a log line or a tool call arg)
    could embed a megabyte of regex; cap the string length."""
    from src.tools.promql_safety import validate_promql, UnsafeQuery

    giant = 'rate(http_requests_total{namespace="a",service="' + "x" * 20000 + '"}[5m])'
    with pytest.raises(UnsafeQuery, match="length"):
        validate_promql(giant)


def test_reject_empty_query():
    from src.tools.promql_safety import validate_promql, UnsafeQuery

    with pytest.raises(UnsafeQuery):
        validate_promql("")


def test_accept_namespace_with_regex_operator():
    """Regex-equality on namespace (`namespace=~"foo.*"`) still counts
    as a namespace filter."""
    from src.tools.promql_safety import validate_promql

    validate_promql(
        'rate(http_requests_total{namespace=~"payments-.*",service="api"}[5m])',
        step_s=60,
        range_h=1,
    )


def test_range_exactly_seven_days_accepted():
    from src.tools.promql_safety import validate_promql

    # 7d with step=60s → 10080 points, well under cap.
    validate_promql(
        'rate(http_requests_total{namespace="x"}[7d])',
        step_s=60,
        range_h=168,
    )


def test_range_over_seven_days_rejected():
    from src.tools.promql_safety import validate_promql, UnsafeQuery

    with pytest.raises(UnsafeQuery, match="range"):
        validate_promql(
            'rate(http_requests_total{namespace="x"}[8d])',
            step_s=60,
            range_h=192,
        )


def test_seconds_and_minutes_units_supported():
    from src.tools.promql_safety import validate_promql

    validate_promql(
        'sum(rate(http_requests_total{namespace="x"}[300s]))',
        step_s=60,
    )
    validate_promql(
        'sum(rate(http_requests_total{namespace="x"}[10m]))',
        step_s=60,
    )

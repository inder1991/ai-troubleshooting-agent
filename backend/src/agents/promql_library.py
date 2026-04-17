"""PromQL library — golden signals, alerts, scrape health, baseline offset.

Every function returns a ready-to-dispatch PromQL string that passes
``validate_promql``. Agents don't build PromQL from scratch — they compose
library calls. Benefits: (a) every query is safety-validated before it's
ever serialised; (b) the LLM's PromQL is confined to choosing *which*
function to call, not *what* string to emit.

All functions require a namespace so queries are always scoped — cluster-
wide scans are banned by the safety middleware anyway, but enforcing the
constraint at the library surface keeps the error messages actionable.
"""
from __future__ import annotations

from src.tools.promql_safety import validate_promql


def _require_label(name: str, value: str) -> None:
    if not value or not isinstance(value, str):
        raise ValueError(f"{name} is required")
    if '"' in value or "\n" in value or "\\" in value:
        raise ValueError(
            f"{name}={value!r} contains unsafe characters (quote/newline/backslash)"
        )


def build_golden_signals(
    *,
    namespace: str,
    service: str,
    window: str = "5m",
    step_s: int = 60,
) -> dict[str, str]:
    """The four RED/USE queries for one service in one namespace.

    Returns: latency_p50/p95/p99, traffic_rps, error_rate, saturation_cpu,
    saturation_mem. All validated against promql_safety before return so a
    caller that gets a string can dispatch it unconditionally.
    """
    _require_label("namespace", namespace)
    _require_label("service", service)

    selector = f'namespace="{namespace}",service="{service}"'
    range_selector = f'namespace="{namespace}",service="{service}"'

    queries = {
        "latency_p50": (
            f"histogram_quantile(0.50, sum by (le) ("
            f"rate(http_request_duration_seconds_bucket{{{selector}}}[{window}])"
            f"))"
        ),
        "latency_p95": (
            f"histogram_quantile(0.95, sum by (le) ("
            f"rate(http_request_duration_seconds_bucket{{{selector}}}[{window}])"
            f"))"
        ),
        "latency_p99": (
            f"histogram_quantile(0.99, sum by (le) ("
            f"rate(http_request_duration_seconds_bucket{{{selector}}}[{window}])"
            f"))"
        ),
        "traffic_rps": (
            f"sum(rate(http_requests_total{{{selector}}}[{window}]))"
        ),
        "error_rate": (
            f'sum(rate(http_requests_total{{{selector},status=~"5.."}}[{window}])) '
            f"/ clamp_min(sum(rate(http_requests_total{{{range_selector}}}[{window}])), 1)"
        ),
        "saturation_cpu": (
            f"sum(rate(container_cpu_usage_seconds_total{{{selector}}}[{window}])) "
            f"/ sum(kube_pod_container_resource_limits{{{selector},resource=\"cpu\"}})"
        ),
        "saturation_mem": (
            f"sum(container_memory_working_set_bytes{{{selector}}}) "
            f"/ sum(kube_pod_container_resource_limits{{{selector},resource=\"memory\"}})"
        ),
    }

    for q in queries.values():
        validate_promql(q, step_s=step_s, range_h=1)
    return queries


def query_alerts_firing(*, namespace: str) -> str:
    """All firing alerts scoped to a namespace."""
    _require_label("namespace", namespace)
    q = f'ALERTS{{namespace="{namespace}",alertstate="firing"}}'
    validate_promql(q, step_s=60, range_h=1)
    return q


def query_scrape_health(*, namespace: str, job: str = ".+") -> str:
    """up{} for the given namespace + job selector.

    ``job`` is a regex fragment; the default matches any job so callers
    can drop it when they don't know the job name. Scanning across all
    namespaces is blocked by the safety middleware.
    """
    _require_label("namespace", namespace)
    _require_label("job", job)
    q = f'up{{namespace="{namespace}",job=~"{job}"}}'
    validate_promql(q, step_s=60, range_h=1)
    return q


def query_recording_rule_lag(*, namespace: str) -> str:
    """Rule-evaluation latency — a symptom of Prometheus overload."""
    _require_label("namespace", namespace)
    q = (
        f"max_over_time("
        f'prometheus_rule_evaluation_duration_seconds{{namespace="{namespace}"}}'
        f"[5m])"
    )
    validate_promql(q, step_s=60, range_h=1)
    return q


def query_offset_baseline(
    query: str,
    *,
    hours: int,
    step_s: int = 60,
) -> str:
    """Wrap ``query`` with a PromQL ``offset <hours>h`` for baseline compare."""
    if hours <= 0 or hours > 168:
        raise ValueError(f"hours {hours} must be in (0, 168] for offset baseline")
    wrapped = f"({query}) offset {hours}h"
    validate_promql(wrapped, step_s=step_s, range_h=max(1, hours))
    return wrapped

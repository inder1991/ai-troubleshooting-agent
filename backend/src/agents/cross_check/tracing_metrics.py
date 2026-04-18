"""Tracing ↔ Metrics divergence detector.

When tracing and metrics disagree about which service is suffering, that
disagreement is itself a diagnostic signal — usually one of:

  1. **Sampling artifact** — tracing picked an outlier trace; metrics show
     the broader population is fine.
  2. **Metric-pipeline lag** — the metric aggregation window hasn't caught
     up with the tracing sample (tracing reflects events newer than the
     metrics roll-up).
  3. **Aggregation bug** — metric labels drop the affected service, so the
     metric exists but isn't segmented by service.
  4. **Genuine coverage gap** — one of the two is missing the real signal.

All four are worth surfacing to the user. Checker runs after both
``metrics_analysis`` and ``trace_analysis`` land on state — typically at
EvalGate time in the Phase-4 orchestration loop.

Pure function; zero LLM; unit-testable.
"""
from __future__ import annotations

import re
from typing import Optional

from src.models.schemas import (
    DivergenceFinding,
    MetricAnomaly,
    MetricsAnalysisResult,
    TraceAnalysisResult,
)


# PromQL label-extraction regex — pulls common service-identifier labels.
_LABEL_PATTERNS = [
    re.compile(r'service(?:_name)?="([^"]+)"'),
    re.compile(r'app="([^"]+)"'),
    re.compile(r'container(?:_name)?="([^"]+)"'),
    re.compile(r'deployment(?:_name)?="([^"]+)"'),
    re.compile(r'destination_service_name="([^"]+)"'),  # Istio/OSM conventions
    re.compile(r'destination_workload="([^"]+)"'),
    re.compile(r'job="([^"]+)"'),
]


def check_tracing_metrics_divergence(
    metrics: Optional[MetricsAnalysisResult],
    trace: Optional[TraceAnalysisResult],
) -> list[DivergenceFinding]:
    """Return divergence findings comparing metrics-agent + tracing-agent output.

    Returns an empty list when either input is None, or when both agents
    agree on the relevant services.
    """
    if metrics is None or trace is None:
        return []
    if not metrics.anomalies and not trace.baseline_regressions and trace.failure_point is None:
        return []

    findings: list[DivergenceFinding] = []

    metric_services = _services_from_metrics(metrics.anomalies)
    trace_services_in_chain = set(trace.services_in_chain or [])
    failure_svc = (
        trace.failure_point.service_name
        if trace.failure_point is not None
        else None
    )

    # Divergence 1 — tracing names a failure service; metrics doesn't flag it.
    if failure_svc and failure_svc not in metric_services:
        findings.append(
            DivergenceFinding(
                kind="trace_failure_service_no_metric_anomaly",
                severity="high",
                service_name=failure_svc,
                human_summary=(
                    f"Tracing identified '{failure_svc}' as the failure point, "
                    f"but metrics_agent surfaced no anomaly referencing this service. "
                    f"Likely causes: sampling outlier, metric-pipeline lag, or missing "
                    f"service label in the aggregation."
                ),
                metadata={
                    "failure_service": failure_svc,
                    "metric_services": sorted(metric_services),
                    "trace_overall_confidence": trace.overall_confidence,
                    "metrics_overall_confidence": metrics.overall_confidence,
                },
            )
        )

    # Divergence 2 — baseline-regression hints from tracing with no matching
    # metric anomaly. Each trace-side regression carries a service_name and
    # a ratio/z-score; if metrics didn't flag the same service, something's
    # out of sync.
    for hint in trace.baseline_regressions or []:
        if hint.service_name not in metric_services:
            findings.append(
                DivergenceFinding(
                    kind="trace_baseline_regression_no_metric_anomaly",
                    severity=_severity_from_ratio(
                        hint.observed_duration_ms / max(hint.baseline_p99_ms, 1.0)
                    ),
                    service_name=hint.service_name,
                    human_summary=(
                        f"Tracing saw '{hint.service_name}' at "
                        f"{hint.observed_duration_ms:.0f}ms vs baseline P99 "
                        f"{hint.baseline_p99_ms:.0f}ms (z={hint.z_score:.1f}); "
                        f"metrics_agent's anomaly set has nothing on this service. "
                        f"Cross-check sampling window + metric label coverage."
                    ),
                    metadata={
                        "operation": hint.operation_name,
                        "observed_duration_ms": hint.observed_duration_ms,
                        "baseline_p99_ms": hint.baseline_p99_ms,
                        "z_score": hint.z_score,
                        "metric_services": sorted(metric_services),
                    },
                )
            )

    # Divergence 3 — metrics flagged a service that tracing never saw.
    # Only emit when we have positive evidence tracing should have covered it
    # (i.e. tracing ran and has a services_in_chain list). An empty list
    # could mean no-trace-data, not divergence.
    if trace_services_in_chain:
        for svc in metric_services:
            if svc and svc not in trace_services_in_chain:
                findings.append(
                    DivergenceFinding(
                        kind="metric_anomaly_service_absent_from_trace",
                        severity="medium",
                        service_name=svc,
                        human_summary=(
                            f"metrics_agent flagged an anomaly on '{svc}', but this "
                            f"service does not appear in tracing's services_in_chain. "
                            f"Either the anomaly is in an upstream/sibling service "
                            f"outside the sampled request path, or tracing missed this "
                            f"hop due to sampling."
                        ),
                        metadata={
                            "service_in_chain": sorted(trace_services_in_chain),
                            "metric_service": svc,
                        },
                    )
                )

    return findings


# ── Helpers ──────────────────────────────────────────────────────────────


def _services_from_metrics(anomalies: list[MetricAnomaly]) -> set[str]:
    """Extract service identifiers from the PromQL queries on each anomaly.

    MetricAnomaly has no explicit service field (metric-keyed model), so
    we parse label selectors. Robust to common conventions (Istio, OSM,
    plain Prometheus, k8s kube-state-metrics).
    """
    services: set[str] = set()
    for anomaly in anomalies:
        q = anomaly.promql_query or ""
        for pat in _LABEL_PATTERNS:
            for m in pat.findall(q):
                if m and m != "*":
                    services.add(m)
    return services


def _severity_from_ratio(ratio: float) -> str:
    if ratio >= 8.0:
        return "critical"
    if ratio >= 4.0:
        return "high"
    if ratio >= 2.0:
        return "medium"
    return "low"

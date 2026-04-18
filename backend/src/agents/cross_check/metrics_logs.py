"""Metrics ↔ Logs divergence detector.

Runs after both ``metrics_analysis`` and ``log_analysis`` land on state.
Compares the services each agent is talking about and surfaces the three
kinds of disagreement that matter to oncall:

  1. **Metric anomaly, silent logs** — metrics flag service X, but no log
     pattern mentions X. Usually: noisy metric, upstream 4xx counted as
     "errors", or log shipper dropping the service's volume.
  2. **Log error cluster, no metric anomaly** — logs show a repeating
     exception on service X, but metrics look flat for X. Usually: that
     service is missing error-rate instrumentation.
  3. **Log errors on a service metrics has never heard of** — logs name
     service X, but metrics have no anomaly *or baseline* referencing X.
     Service is a full metric blind spot (scrape config missing, etc.).

All three are surfaced as ``DivergenceFinding`` records. Pure function,
zero LLM, unit-testable.

Note on (3): the signal is weaker than (2) because metrics_analysis only
lists *anomalous* services, not the full metric-covered universe. We
suppress (3) when metrics produced no anomalies at all — that's a
different kind of silence (metrics ran fine, nothing was anomalous)
rather than a coverage gap.
"""
from __future__ import annotations

import re
from typing import Optional

from src.models.schemas import (
    DivergenceFinding,
    ErrorPattern,
    LogAnalysisResult,
    MetricAnomaly,
    MetricsAnalysisResult,
)


# Reuse the same PromQL label extractor as tracing↔metrics — same conventions.
_LABEL_PATTERNS = [
    re.compile(r'service(?:_name)?="([^"]+)"'),
    re.compile(r'app="([^"]+)"'),
    re.compile(r'container(?:_name)?="([^"]+)"'),
    re.compile(r'deployment(?:_name)?="([^"]+)"'),
    re.compile(r'destination_service_name="([^"]+)"'),
    re.compile(r'destination_workload="([^"]+)"'),
    re.compile(r'job="([^"]+)"'),
]

# Minimum log-pattern frequency before we treat it as a "cluster" worth
# cross-checking against metrics. Single-shot errors are too noisy.
_MIN_LOG_CLUSTER_FREQUENCY = 3


def check_metrics_logs_divergence(
    metrics: Optional[MetricsAnalysisResult],
    logs: Optional[LogAnalysisResult],
) -> list[DivergenceFinding]:
    """Return divergence findings comparing metrics-agent + log-agent output.

    Returns an empty list when either input is None, or when both agents
    agree on the services involved.
    """
    if metrics is None or logs is None:
        return []

    metric_services = _services_from_metrics(metrics.anomalies)
    log_clusters = _clusters_from_logs(logs)
    log_services = {svc for svc, _pattern in log_clusters}

    # Short-circuit: nothing meaningful to compare.
    if not metric_services and not log_services:
        return []

    findings: list[DivergenceFinding] = []

    # Divergence 1 — metrics flagged a service; logs are silent on it.
    # Emit only when logs produced ≥1 cluster elsewhere (i.e. log_agent
    # did see errors somewhere; the silence on this service is informative).
    if log_services:
        for svc in sorted(metric_services):
            if svc not in log_services:
                findings.append(
                    DivergenceFinding(
                        kind="metric_anomaly_no_error_logs",
                        severity="medium",
                        service_name=svc,
                        human_summary=(
                            f"metrics_agent flagged an anomaly on '{svc}', but "
                            f"log_agent found no repeating error pattern on this "
                            f"service. Likely causes: noisy metric (e.g. upstream "
                            f"4xx counted as errors), log shipper lag, or the app "
                            f"isn't logging at error level."
                        ),
                        metadata={
                            "metric_service": svc,
                            "log_services_with_errors": sorted(log_services),
                            "metrics_overall_confidence": metrics.overall_confidence,
                            "logs_overall_confidence": logs.overall_confidence,
                        },
                    )
                )

    # Divergence 2 — logs show an error cluster; metrics flat for that service.
    # Gated by _MIN_LOG_CLUSTER_FREQUENCY so a single stray exception doesn't
    # fire. Only emit when metrics produced at least one anomaly — otherwise
    # "metrics found nothing anywhere" is a different problem (collection
    # outage) that shouldn't be per-service.
    if metric_services:
        for svc, pattern in log_clusters:
            if svc in metric_services:
                continue
            if pattern.frequency < _MIN_LOG_CLUSTER_FREQUENCY:
                continue
            findings.append(
                DivergenceFinding(
                    kind="log_error_cluster_no_metric_anomaly",
                    severity=_severity_from_log(pattern),
                    service_name=svc,
                    human_summary=(
                        f"log_agent found '{pattern.exception_type}' repeating "
                        f"{pattern.frequency}× on '{svc}', but metrics_agent "
                        f"reports no anomaly for this service. Likely a metric "
                        f"coverage gap — error-rate counter missing or "
                        f"unlabelled for this service."
                    ),
                    metadata={
                        "log_service": svc,
                        "pattern_exception_type": pattern.exception_type,
                        "pattern_frequency": pattern.frequency,
                        "pattern_confidence": pattern.confidence_score,
                        "metric_services_flagged": sorted(metric_services),
                    },
                )
            )

    # Divergence 3 — logs name services metrics has never heard of (no
    # anomaly, not even a "healthy" data point). Only meaningful when
    # metrics did produce anomalies elsewhere — if metrics found nothing
    # anywhere, we can't distinguish "blind spot" from "quiet system".
    if metric_services:
        # A service can't be a "blind spot" and also be "flagged" — so we
        # only need to look at services in logs that are NOT in metric_services
        # AND whose cluster already matched D2's gate. To avoid double-firing,
        # D3 fires only when metrics cover DIFFERENT services (strong signal
        # that the log-service is architecturally invisible to metrics).
        for svc, pattern in log_clusters:
            if svc in metric_services:
                continue
            if pattern.frequency < _MIN_LOG_CLUSTER_FREQUENCY:
                continue
            # D2 and D3 share the same trigger condition — we keep them
            # separate when the service identifier looks like it would
            # NEVER show up in metric labels (e.g. contains a path or is
            # freeform text rather than a k8s-style service name).
            if _looks_like_nonmetric_service(svc):
                findings.append(
                    DivergenceFinding(
                        kind="log_error_service_not_in_metrics",
                        severity="medium",
                        service_name=svc,
                        human_summary=(
                            f"log_agent found errors on '{svc}', which does not "
                            f"match any service label in the metrics the "
                            f"metrics_agent saw. Likely a scrape-config blind "
                            f"spot — this service isn't being collected."
                        ),
                        metadata={
                            "log_service": svc,
                            "metric_services_flagged": sorted(metric_services),
                            "pattern_exception_type": pattern.exception_type,
                        },
                    )
                )

    return findings


# ── Helpers ──────────────────────────────────────────────────────────────


def _services_from_metrics(anomalies: list[MetricAnomaly]) -> set[str]:
    """Extract service identifiers from each anomaly's PromQL query."""
    services: set[str] = set()
    for anomaly in anomalies:
        q = anomaly.promql_query or ""
        for pat in _LABEL_PATTERNS:
            for m in pat.findall(q):
                if m and m != "*":
                    services.add(m)
    return services


def _clusters_from_logs(
    logs: LogAnalysisResult,
) -> list[tuple[str, ErrorPattern]]:
    """Flatten primary + secondary patterns into (service, pattern) pairs.

    Each pattern's ``affected_components`` can name multiple services; we
    fan out so each service-pattern pair is checked independently.
    """
    pairs: list[tuple[str, ErrorPattern]] = []
    all_patterns: list[ErrorPattern] = []
    if logs.primary_pattern is not None:
        all_patterns.append(logs.primary_pattern)
    all_patterns.extend(logs.secondary_patterns or [])

    for pattern in all_patterns:
        for svc in pattern.affected_components or []:
            if svc:
                pairs.append((svc.strip(), pattern))
    return pairs


def _severity_from_log(pattern: ErrorPattern) -> str:
    """Map log-pattern severity to divergence severity, capped at high —
    meta-findings shouldn't out-rank their source findings."""
    if pattern.severity in ("critical", "high"):
        return "high"
    return "medium"


# Service names that couldn't possibly match a Prometheus label — these are
# almost certainly log-level identifiers (URL paths, human-readable names)
# rather than k8s service names. Used to decide D2 vs D3.
_NON_METRIC_HEURISTICS = (
    "/",       # URL path
    " ",       # human name with spaces
    "\t",
)


def _looks_like_nonmetric_service(svc: str) -> bool:
    """Return True when the service identifier is unlikely to ever appear
    in a metric label (thus "blind spot" rather than "uninstrumented")."""
    return any(marker in svc for marker in _NON_METRIC_HEURISTICS)

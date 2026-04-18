"""Deterministic Envoy/Istio ``response.flags`` matcher — zero LLM.

When a span carries a ``response.flags`` tag set by Envoy (the sidecar in
Istio, or a front-proxy), the tag value names the failure mode in a
2-3-letter code. This matcher translates those codes into structured
findings without asking the LLM — same philosophy as the Phase 4 signature
library for logs.

Why this is a big deal: roughly 40% of Istio-mesh production failures have
a crisp ``response.flags`` match, which means 40% of trace analyses can
be answered by pattern matching alone, saving both the LLM cost and the
latency + giving users a deterministic, explainable answer.

Reference: https://www.envoyproxy.io/docs/envoy/latest/configuration/observability/access_log/usage#config-access-log-format-response-flags
"""
from __future__ import annotations

from typing import Optional

from src.models.schemas import EnvoyFlagFinding, SpanInfo


# Canonical mapping — lifted from Envoy access-log spec, pruned to the flags
# that actually appear in trace tags (some are access-log-only).
_FLAG_TABLE: dict[str, dict[str, str]] = {
    "UH": {
        "summary": "No healthy upstream endpoints",
        "cause": (
            "The destination service had zero healthy endpoints when this "
            "request arrived. Common root causes: (a) the target deployment "
            "has no ready pods; (b) readiness probes are failing; (c) Istio "
            "destination rule is filtering out all endpoints."
        ),
    },
    "UO": {
        "summary": "Upstream overflow — circuit breaker open",
        "cause": (
            "Envoy circuit breaker tripped for the upstream cluster. Either "
            "connection pool or request pool saturated. The target service "
            "is overloaded OR the circuit-breaker thresholds are too tight."
        ),
    },
    "UC": {
        "summary": "Upstream connection termination",
        "cause": (
            "The upstream pod dropped the connection mid-flight. Common "
            "causes: pod was killed (OOM, eviction, deploy), keep-alive "
            "timeout mismatch, or a server-side bug closing the socket."
        ),
    },
    "UT": {
        "summary": "Upstream request timeout",
        "cause": (
            "Envoy's per-request timeout fired before the upstream responded. "
            "Either the upstream is slow (investigate its metrics/logs) OR "
            "the caller's timeout is tighter than the callee's P99 latency."
        ),
    },
    "URX": {
        "summary": "Upstream retry limit exceeded",
        "cause": (
            "All configured retries to the upstream failed. Strong signal "
            "that the upstream is hard-down rather than transiently slow. "
            "Look at the first retry attempt's span for the original cause."
        ),
    },
    "DC": {
        "summary": "Downstream connection termination",
        "cause": (
            "The client disconnected before Envoy finished sending the "
            "response. Often benign (client timeout, user navigated away) "
            "but can indicate the client's own timeout is tighter than "
            "this service's P99."
        ),
    },
    "NR": {
        "summary": "No route configured",
        "cause": (
            "No Istio VirtualService / RouteConfiguration rule matched this "
            "request's destination. Usually a misconfigured Gateway or a "
            "missing DestinationRule — a config bug, not a runtime fault."
        ),
    },
    "LR": {
        "summary": "Connection-local reset",
        "cause": (
            "Envoy reset the connection locally. Typically means Envoy itself "
            "ran out of resources (file descriptors, memory) — check the "
            "Istio proxy's own container health."
        ),
    },
    "RL": {
        "summary": "Rate-limit service denied request",
        "cause": (
            "The Envoy rate-limit filter rejected this request. Either the "
            "limit is tuned too low for legitimate traffic or a client is "
            "misbehaving. Check the rate-limit rule for this route."
        ),
    },
}


class EnvoyResponseFlagsMatcher:
    """Scans spans for ``response.flags`` and emits deterministic findings."""

    @staticmethod
    def match_span(span: SpanInfo) -> Optional[EnvoyFlagFinding]:
        """Return a finding if this span carries a recognized Envoy flag, else None.

        Envoy can emit MULTIPLE flags separated by ``,`` on a single
        request (e.g. ``UH,URX`` when all retries failed because there
        was never a healthy upstream). We honor the most-primary one per
        the _FLAG_PRIORITY list below — URX dominates UH because the
        retry exhaustion is the enclosing event.
        """
        raw = span.tags.get("response.flags") or span.tags.get("response_flags")
        if not raw:
            return None

        flags = [f.strip() for f in raw.split(",") if f.strip()]
        flag = _pick_primary_flag(flags)
        if flag is None or flag not in _FLAG_TABLE:
            return None

        entry = _FLAG_TABLE[flag]
        return EnvoyFlagFinding(
            flag=flag,  # type: ignore[arg-type]
            span_id=span.span_id,
            service_name=span.service_name,
            upstream_cluster=span.tags.get("upstream.cluster") or span.tags.get("upstream_cluster"),
            human_summary=entry["summary"],
            likely_cause=entry["cause"],
        )

    @staticmethod
    def scan_trace(spans: list[SpanInfo]) -> list[EnvoyFlagFinding]:
        """Scan every span; return every recognized Envoy-flag finding."""
        findings: list[EnvoyFlagFinding] = []
        for span in spans:
            f = EnvoyResponseFlagsMatcher.match_span(span)
            if f is not None:
                findings.append(f)
        return findings

    @staticmethod
    def is_self_explanatory(findings: list[EnvoyFlagFinding]) -> bool:
        """True when the flag findings tell the whole story cleanly enough to
        skip the LLM call.

        Criteria: exactly one flag, and it's not an ambiguous one. We
        deliberately require uniqueness — multiple flags across a trace
        usually indicate cascading failures that benefit from LLM narrative.
        """
        if len(findings) != 1:
            return False
        return findings[0].flag in {"UH", "UO", "URX", "NR", "RL"}


# Priority when multiple flags appear on one span. Earlier wins.
_FLAG_PRIORITY = ["URX", "UO", "UH", "UT", "UC", "NR", "RL", "LR", "DC"]


def _pick_primary_flag(flags: list[str]) -> Optional[str]:
    for candidate in _FLAG_PRIORITY:
        if candidate in flags:
            return candidate
    # None of the recognized ones; return the first raw flag so the caller
    # at least knows SOMETHING was flagged (even if we don't have a canned
    # interpretation).
    return flags[0] if flags else None

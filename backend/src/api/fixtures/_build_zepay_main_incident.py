"""Build the Zepay scenario timeline JSON.

Running this script regenerates zepay-main-incident.json. Keep the
timeline authoritative HERE — editing the JSON directly is fine for
small tweaks, but anything structural (adding a new agent, changing
the critic sequence, etc.) lives in this builder.

Design contract:
  · Events ONLY use the event_types the UI renders: started, progress,
    tool_call, finding, summary, success, error, warning, phase_change,
    attestation_required, reasoning. Anything else silently drops.
  · State mutations write to either `session.*` (top-level fields
    /status reads) or `state.*` (the DiagnosticState-shaped blob
    /findings projects from).
  · Per-agent token_usage grows over time via list-append patches
    using the convention `"token_usage[+]": {...}`.

Pacing philosophy:
  · 0-3s:     dispatch + initial log_agent scan
  · 3-15s:    log_agent clusters, metric_agent starts, tracing starts
  · 15-40s:   parallel agent work, tool-calls + thoughts
  · 40-65s:   cross-checks, hypothesis elimination (ReAct + critic rounds)
  · 65-88s:   code_agent, verdict synthesis, critic challenge + rebound
  · 88-90s:   signature match, blast radius, fix-ready
  · 90s:      attestation gate (waits for operator)
  · +0-10s after approval: 3 PRs opened sequentially, phase=complete
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "zepay-main-incident.json"
TIMELINE: list[dict] = []


# ── Helpers ───────────────────────────────────────────────────────────


def evt(t: float, agent: str, event_type: str, message: str, details: dict | None = None) -> None:
    TIMELINE.append({
        "t": round(t, 2),
        "kind": "event",
        "event": {
            "agent_name": agent,
            "event_type": event_type,
            "message": message,
            "details": details or {},
        },
    })


def patch(t: float, patch_body: dict) -> None:
    TIMELINE.append({"t": round(t, 2), "kind": "state_patch", "patch": patch_body})


def phase(t: float, p: str) -> None:
    TIMELINE.append({"t": round(t, 2), "kind": "phase_change", "phase": p})


def token_patch(t: float, agent: str, input_tokens: int, output_tokens: int) -> None:
    patch(t, {"state": {"token_usage[+]": {
        "agent_name": agent,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }}})


def budget_patch(t: float, tool_calls_used: int, usd_used: float) -> None:
    patch(t, {"session": {"budget": {
        "tool_calls_used": tool_calls_used,
        "tool_calls_max":  40,
        "llm_usd_used":    round(usd_used, 4),
        "llm_usd_max":     1.00,
    }}})


# ── Phase 1 — dispatch + log_agent ────────────────────────────────────


phase(0.0, "collecting_context")
evt(0.1, "supervisor", "summary",
    "Session started — operator flagged checkout-service as patient zero.",
    {"service_name": "checkout-service"})

evt(0.5, "supervisor", "started",
    "Dispatching log_agent first — cheapest signal, widest coverage.",
    {"plan": ["log_agent", "metric_agent", "tracing_agent", "k8s_agent"]})

evt(1.0, "log_agent", "started",
    "Scanning 4-hour window across payments-prod Elasticsearch indices.")
evt(1.5, "log_agent", "tool_call",
    "elasticsearch.search(index='payments-prod-*', size=5000, "
    "query={exception_type OR level:ERROR OR level:WARN}, window=4h)",
    {"tool": "elasticsearch.search", "params": {"size": 5000, "window_hours": 4}})
evt(2.1, "log_agent", "reasoning",
    "2.1M log lines in window. Filtering to error/warn bands before clustering.")
evt(2.7, "log_agent", "progress",
    "Batch 1/8: 264K lines processed, 31 exception types surfaced.",
    {"batch": "1/8", "lines": 264000})
token_patch(3.0, "log_agent", 2100, 40)

evt(3.4, "log_agent", "progress",
    "Batch 3/8: clustering by exception_type. Top: UpstreamTimeoutException (47), "
    "NullPointerException (14), FraudScoreProviderSlowdown (206).",
    {"batch": "3/8"})
evt(4.0, "log_agent", "tool_call",
    "elasticsearch.search(exception_type:UpstreamTimeoutException, correlation_ids:*)")
evt(4.4, "log_agent", "reasoning",
    "UpstreamTimeoutException: 47 occurrences, all from payment-service. "
    "Each followed within 3ms by INFO 'RetryAttempt=2 for inventory-reserve'.")
evt(5.0, "log_agent", "progress",
    "Batch 6/8: correlating log timestamps against customer-complaint window.")
token_patch(5.2, "log_agent", 4100, 180)

evt(5.8, "log_agent", "finding",
    "UpstreamTimeoutException cluster — 47 occurrences, payment-service primary. "
    "RetryAttempt=2 pattern precedes each.",
    {
        "pattern_id": "p-upstream-timeout",
        "exception_type": "UpstreamTimeoutException",
        "frequency": 47,
        "affected_components": ["payment-service", "istio-proxy", "inventory-service"],
        "priority_rank": 1,
        "confidence_score": 89,
        "causal_role": "root_cause_tentative",
    })

# Populate log_analysis state so Evidence column's AgentFindingCard renders.
patch(6.0, {"state": {
    "log_analysis": {
        "primary_pattern": {
            "pattern_id": "p-upstream-timeout",
            "exception_type": "UpstreamTimeoutException",
            "error_message": "Read timeout after 15000ms calling inventory-service.reserve",
            "frequency": 47,
            "severity": "high",
            "affected_components": ["payment-service", "istio-proxy", "inventory-service"],
            "sample_logs": [
                {"timestamp": "2026-04-21T14:47:18.023Z",
                 "level": "WARN",
                 "msg": "upstream connect error 504 inventory-service",
                 "trace_id": "T-sarah-1234-001"},
                {"timestamp": "2026-04-21T14:47:18.024Z",
                 "level": "INFO",
                 "msg": "RetryAttempt=2 for inventory-reserve",
                 "trace_id": "T-sarah-1234-001"},
            ],
            "confidence_score": 89,
            "priority_rank": 1,
            "priority_reasoning": "15× baseline for retry-flagged pattern; 47/47 correlate to customer complaints",
            "causal_role": "root_cause",
            "correlation_ids": [f"T-demo-{i:04d}" for i in range(47)],
        },
        "secondary_patterns": [
            {
                "pattern_id": "p-fraud-slow",
                "exception_type": "FraudScoreProviderSlowdown",
                "frequency": 206,
                "severity": "medium",
                "affected_components": ["fraud-adapter"],
                "confidence_score": 71,
                "priority_rank": 2,
                "priority_reasoning": "Latency 2.7× baseline but uncorrelated to complaints",
                "causal_role": "correlated_anomaly",
            }
        ],
        "negative_findings": [
            "No WARN/ERROR cluster on wallet-service: replication lag < 50ms throughout.",
            "checkout-service error-rate 0.04% — within 7d baseline.",
        ],
        "overall_confidence": 84,
    }
}})

evt(6.3, "log_agent", "finding",
    "Patient Zero reframe: operator flagged checkout-service, evidence points to payment-service.",
    {"old_patient_zero": "checkout-service", "new_patient_zero": "payment-service"})

# patient_zero + namespace + inferred dependencies
patch(6.5, {"state": {
    "patient_zero": {
        "service": "payment-service",
        "first_error_time": "2026-04-21T14:47:03.012Z",
        "reasoning": "47/47 UpstreamTimeoutException clusters originate at payment-service.execute",
    },
    "detected_namespace": "payments-prod",
    "target_service": "payment-service",
    "inferred_dependencies": [
        {"source": "api-gateway", "target": "checkout-service", "kind": "http"},
        {"source": "checkout-service", "target": "payment-service", "kind": "http"},
        {"source": "payment-service", "target": "wallet-service", "kind": "http"},
        {"source": "payment-service", "target": "inventory-service", "kind": "http"},
        {"source": "payment-service", "target": "fraud-adapter", "kind": "http"},
        {"source": "payment-service", "target": "notification-service", "kind": "http"},
        {"source": "checkout-service", "target": "cart-service", "kind": "http"},
        {"source": "api-gateway", "target": "auth-service", "kind": "http"},
    ],
    "service_flow": [
        {"service": "api-gateway", "order": 1},
        {"service": "checkout-service", "order": 2},
        {"service": "payment-service", "order": 3},
        {"service": "wallet-service", "order": 4},
        {"service": "inventory-service", "order": 5},
    ],
    "suggested_promql_queries": [
        {"metric": "payment_ledger_write_total",
         "query": "sum by (retry) (rate(payment_ledger_write_total{namespace=\"payments-prod\"}[5m]))",
         "rationale": "Break out retry=true — the path hiding the duplicate-debit signal."},
        {"metric": "istio_request_duration_seconds",
         "query": "histogram_quantile(0.99, sum by (le,destination_service) (rate(istio_request_duration_seconds_bucket{source_service=\"payment-service\",namespace=\"payments-prod\"}[5m])))",
         "rationale": "p99 from payment-service's perspective — reveals the 15s sidecar wall."},
        {"metric": "wallet_balance_changes_total",
         "query": "sum by (customer_id) (increase(wallet_balance_changes_total{namespace=\"payments-prod\"}[1h]))",
         "rationale": ">1 change per txn_id is the smoking gun."},
        {"metric": "checkout_payment_latency_seconds",
         "query": "histogram_quantile(0.95, sum by (le) (rate(checkout_payment_latency_seconds_bucket{namespace=\"payments-prod\"}[5m])))",
         "rationale": "Proves checkout's latency spiked to 15s — matching the user spinner."},
        {"metric": "reconciliation_drift_dollars",
         "query": "sum(reconciliation_drift_dollars{namespace=\"payments-prod\"})",
         "rationale": "Pre-auto-round drift; would have surfaced duplicates if threshold tighter."},
        {"metric": "kafka_consumer_lag",
         "query": "sum by (consumer_group) (kafka_consumergroup_lag{topic=\"wallet-events\",namespace=\"payments-prod\"})",
         "rationale": "Rules out event-sourced projector as contributing cause."},
    ],
}})

evt(7.0, "log_agent", "summary",
    "Log clusters complete. 1 primary (UpstreamTimeoutException, r=0.89), "
    "1 secondary (FraudScoreProviderSlowdown, r=0.71). Patient Zero: payment-service.",
    {"duration_s": 6.0, "clusters": 2, "confidence": 84})
token_patch(7.0, "log_agent", 300, 120)
patch(7.1, {"state": {"agents_completed[+]": "log_agent"}})


# ── Phase 1 continued — metric_agent in parallel ──────────────────────


evt(4.2, "supervisor", "summary",
    "log_agent progressing; dispatching metric_agent + tracing_agent in parallel.")

evt(4.8, "metric_agent", "started",
    "Opening Prometheus range-query session; 6 suggested queries from log_agent.")
evt(5.5, "metric_agent", "tool_call",
    "prometheus.query_range(payment_ledger_write_total{retry=true}, window=4h, step=60s)",
    {"tool": "prometheus.query_range"})
evt(6.0, "metric_agent", "reasoning",
    "Baselining retry-counter against 6-week history. Target: signal > 3× baseline.")
token_patch(6.2, "metric_agent", 1800, 50)

evt(7.5, "metric_agent", "tool_call",
    "prometheus.query_range(istio_request_duration_p99{destination=inventory-service}, window=4h)")
evt(8.1, "metric_agent", "finding",
    "Anomaly: payment_ledger_write_total{retry=true} 15× over 6-week baseline.",
    {"metric": "payment_ledger_write_total",
     "baseline": 0.02, "peak": 0.31, "severity": "medium", "confidence": 88})

patch(8.3, {"state": {"metric_anomalies[+]": {
    "metric_name": "payment_ledger_write_total",
    "promql_query": "sum by (retry) (rate(payment_ledger_write_total{retry=\"true\",namespace=\"payments-prod\"}[5m]))",
    "baseline_value": 0.02,
    "current_value": 0.31,
    "peak_value": 0.31,
    "spike_start": "2026-04-21T14:00:00Z",
    "spike_end": "2026-04-21T18:47:00Z",
    "severity": "medium",
    "correlation_to_incident": "Retry-flagged ledger writes elevated 15× over 6-week baseline; aligns 1:1 with customer complaint window.",
    "confidence_score": 88,
}}})

evt(8.6, "metric_agent", "tool_call",
    "prometheus.query_range(checkout_payment_latency_seconds_p95, window=4h)")
evt(9.2, "metric_agent", "finding",
    "Anomaly: istio_request_duration_p99{destination=inventory-service} — 140ms → 15.003s.",
    {"metric": "istio_request_duration_seconds", "peak": 15.003, "severity": "high", "confidence": 95})

patch(9.4, {"state": {"metric_anomalies[+]": {
    "metric_name": "istio_request_duration_seconds",
    "promql_query": "histogram_quantile(0.99, sum by (le) (rate(istio_request_duration_seconds_bucket{destination_service=\"inventory-service\",namespace=\"payments-prod\"}[5m])))",
    "baseline_value": 0.140,
    "current_value": 15.003,
    "peak_value": 15.003,
    "spike_start": "2026-04-21T14:00:00Z",
    "spike_end": "2026-04-21T18:47:00Z",
    "severity": "high",
    "correlation_to_incident": "Istio sidecar timeouts on inventory-reserve at the 15s boundary; drives retry behavior upstream.",
    "confidence_score": 95,
}}})

evt(10.0, "metric_agent", "reasoning",
    "checkout_payment_latency p95: 1.8s → 15.2s. Checkout sits behind payment during the retry.")
evt(10.6, "metric_agent", "finding",
    "Anomaly: checkout_payment_latency p95 — 1.8s baseline → 15.2s.",
    {"metric": "checkout_payment_latency", "peak": 15.2, "severity": "high", "confidence": 92})

patch(10.8, {"state": {"metric_anomalies[+]": {
    "metric_name": "checkout_payment_latency_seconds",
    "promql_query": "histogram_quantile(0.95, sum by (le) (rate(checkout_payment_latency_seconds_bucket{namespace=\"payments-prod\"}[5m])))",
    "baseline_value": 1.8,
    "current_value": 15.2,
    "peak_value": 15.2,
    "spike_start": "2026-04-21T14:00:00Z",
    "spike_end": "2026-04-21T18:47:00Z",
    "severity": "high",
    "correlation_to_incident": "Checkout waits 15s behind payment retry — explains user-visible spinner.",
    "confidence_score": 92,
}}})

evt(11.2, "metric_agent", "reasoning",
    "Negative control: payment_txn_success_ratio = 99.97% (unchanged). "
    "Duplicates count as successes — surface metric dashboards would not alarm.")

evt(11.8, "metric_agent", "summary",
    "3 anomalies surfaced. Retry-counter is the narrowest signal; "
    "Istio p99 is the timing source; checkout p95 is the user-visible symptom.",
    {"anomalies": 3, "confidence": 91})
token_patch(12.0, "metric_agent", 2200, 140)


# ── Phase 1 continued — tracing_agent ─────────────────────────────────


evt(5.4, "tracing_agent", "started",
    "Opening Jaeger. Priority trace-IDs seeded from log_agent's complaint correlations.")
evt(6.6, "tracing_agent", "tool_call",
    "jaeger.search(service=payment-service, tags={error:true, http.status:504}, limit=100)")
evt(7.8, "tracing_agent", "reasoning",
    "Sampling 1% gives ~0.01% chance of capturing both debit spans per customer; "
    "targeting trace-IDs from log_agent correlations instead of random sample.")
token_patch(8.0, "tracing_agent", 2400, 60)

evt(9.5, "tracing_agent", "tool_call",
    "jaeger.replay(trace_id=T-sarah-1234-001) — walking span waterfall")
evt(10.3, "tracing_agent", "finding",
    "Trace T-sarah-1234-001: TWO wallets.UPDATE spans for customer C-CHEN-SARAH-8741, "
    "15.203s apart, different span_ids, identical amount.",
    {"trace_id": "T-sarah-1234-001", "duplicate_count": 2, "gap_seconds": 15.203})
evt(12.5, "tracing_agent", "tool_call",
    "jaeger.replay(trace_id=T-acme-corp-0042) — validating pattern")
evt(13.7, "tracing_agent", "reasoning",
    "Identical pattern on Acme Logistics trace: two wallet-update spans, 15.2s apart.")
evt(15.2, "tracing_agent", "tool_call",
    "jaeger.batch_replay(complaint_trace_ids=[47 traces]) — exhaustive confirmation")
evt(17.8, "tracing_agent", "progress",
    "Batch replay: 47 of 47 complaint traces show the double-wallets.UPDATE pattern.")

evt(18.2, "tracing_agent", "finding",
    "Pattern confirmed 47/47 complaint traces. "
    "Bottleneck: istio-proxy.CONNECT inventory-service (15.003s p99).",
    {"pattern": "double_wallets_update_same_customer_different_txn_id",
     "count": 47, "confidence": 0.97})

patch(18.5, {"state": {
    "trace_analysis": {
        "failure_service_from_trace": "payment-service",
        "critical_path_services": ["api-gateway", "checkout-service", "payment-service", "inventory-service"],
        "services_from_traces": ["api-gateway", "auth-service", "cart-service",
                                  "checkout-service", "payment-service", "inventory-service",
                                  "wallet-service", "fraud-adapter", "notification-service"],
        "trace_ids_mined": [f"T-demo-{i:04d}" for i in range(47)],
        "hot_services_from_traces": ["payment-service", "inventory-service"],
        "bottleneck_operations": [
            ["istio-proxy", "CONNECT inventory-service"],
            ["payment-service", "@Retryable execute"],
        ],
        "pattern_findings_from_traces": [{
            "pattern": "double_wallets_update_same_customer_different_txn_id",
            "count": 47, "confidence": 0.97,
        }],
        "negative_findings": [
            "fraud-adapter.score spans complete in 340-420ms — not timeout-related.",
            "auth-service spans <8ms — not on critical path.",
        ],
        "overall_confidence": 94,
    }
}})

evt(18.8, "tracing_agent", "summary",
    "Trace analysis complete. Smoking gun: double wallets.UPDATE spans.",
    {"duration_s": 13.4, "traces_analyzed": 52, "confidence": 94})
token_patch(19.0, "tracing_agent", 900, 200)
patch(19.1, {"state": {"agents_completed[+]": "tracing_agent"}})


# ── Phase 1 continued — k8s_agent ─────────────────────────────────────


evt(8.8, "k8s_agent", "started",
    "Opening Kubernetes API — ruling out infra hypotheses.")
evt(9.4, "k8s_agent", "tool_call",
    "kubectl.get(pods, namespace=payments-prod, labelSelector=app=payment-service)")
evt(10.2, "k8s_agent", "finding",
    "payment-service: 2 replicas, both Running, restart count 0 over 24h, CPU p95 35%, memory p95 52%.",
    {"service": "payment-service", "healthy": True})
evt(11.0, "k8s_agent", "tool_call",
    "kubectl.describe(deploy/payment-service) + get events 4h")
evt(11.8, "k8s_agent", "reasoning",
    "No deploys in 24h. Recent events: 4× BackOff on inventory-service istio-proxy (1 day old).")
token_patch(12.2, "k8s_agent", 1400, 45)

evt(12.4, "k8s_agent", "tool_call",
    "kubectl.get(pods, namespace=payments-prod, all)")
evt(13.0, "k8s_agent", "finding",
    "All 9 services healthy. 18 pods Running, 0 crashlooping, 0 OOMKilled, 0 ImagePullBackOff.",
    {"pods_total": 18, "healthy": 18})
evt(13.6, "k8s_agent", "tool_call",
    "istio.query_sidecar_metrics(inventory-service)")
evt(14.4, "k8s_agent", "finding",
    "Sidecar on inventory-service: upstream_cx_overflow elevated. "
    "Not an outage — a connection-pool-depth event.",
    {"metric": "upstream_cx_overflow", "state": "elevated"})

patch(14.8, {"state": {
    "k8s_analysis": {
        "cluster_name": "zepay-prod-kind",
        "namespace": "payments-prod",
        "service_name": "payment-service",
        "pod_statuses": [
            {"pod_name": f"payment-service-{i}", "namespace": "payments-prod",
             "status": "Running", "restart_count": 0, "container_count": 2, "ready_containers": 2}
            for i in range(2)
        ],
        "events": [],
        "is_crashloop": False,
        "total_restarts_last_hour": 0,
        "resource_mismatch": None,
        "negative_findings": [
            "No crashlooping pods.",
            "No OOMKilled pods.",
            "No recent Deployment rollouts.",
            "All Istio sidecars Ready.",
        ],
        "breadcrumbs": [],
        "overall_confidence": 97,
    }
}})

evt(15.0, "k8s_agent", "summary",
    "Infrastructure ruled out. 4 negative findings. Bug is in code, not pods.",
    {"duration_s": 6.2, "confidence": 97})
token_patch(15.2, "k8s_agent", 600, 90)
patch(15.3, {"state": {"agents_completed[+]": "k8s_agent"}})


# ── Phase 2 — cross-checks + elimination ──────────────────────────────


phase(20.0, "collecting_context")  # Phase name stays; orchestration continues.

evt(20.3, "supervisor", "summary",
    "All 4 context agents complete. Initiating cross-checks.")

# metrics ↔ logs cross-check
evt(20.8, "supervisor", "tool_call",
    "cross_check.metrics_logs(divergence_keys=[service,exception_type])",
    {"check": "metrics_logs"})
evt(21.4, "supervisor", "reasoning",
    "metrics say `payment_txn_retry_total = 0` (no surface retries). "
    "logs show 47× `RetryAttempt=2`. That's a cardinality mismatch.")
evt(22.0, "supervisor", "finding",
    "Divergence: metrics report 0 retries; logs show 47. "
    "Retry-counter wired to wrong span of the code.",
    {"divergence_kind": "metric_log", "severity": "high"})

patch(22.2, {"state": {"divergence_findings[+]": {
    "kind": "metric_log",
    "service_name": "payment-service",
    "severity": "high",
    "human_summary": "metrics ↔ logs — 1 signal disagreement: retry-counter zeroed while log shows 47 retries",
    "metric_value": 0,
    "log_value": 47,
}}})
evt(22.6, "supervisor", "summary",
    "cross-check: metrics ↔ logs — 1 signal disagreement",
    {"action": "cross_check_complete", "cross_check": "metrics_logs", "divergence_count": 1})

# metrics ↔ tracing cross-check
evt(23.2, "supervisor", "tool_call",
    "cross_check.tracing_metrics(divergence_keys=[span_name,txn_id])",
    {"check": "tracing_metrics"})
evt(23.8, "supervisor", "reasoning",
    "metrics count successful txns per txn_id. Tracing shows TWO wallets.UPDATE spans per txn_id. "
    "Our own instrumentation contradicts itself.")
evt(24.5, "supervisor", "finding",
    "Divergence: metrics see 1 successful transaction per txn_id; traces see 2 wallet writes.",
    {"divergence_kind": "metric_trace", "severity": "critical"})

patch(24.7, {"state": {"divergence_findings[+]": {
    "kind": "metric_trace",
    "service_name": "wallet-service",
    "severity": "critical",
    "human_summary": "metrics ↔ tracing — 47 disagreements: same txn_id has 2 wallets.UPDATE spans",
    "metric_cardinality_per_txn": 1,
    "trace_cardinality_per_txn": 2,
}}})
evt(25.1, "supervisor", "summary",
    "cross-check: tracing ↔ metrics — 47 signal disagreements",
    {"action": "cross_check_complete", "cross_check": "tracing_metrics", "divergence_count": 47})


# Hypothesis set — 4 candidates
patch(25.8, {"state": {"hypotheses": [
    {"hypothesis_id": "H1", "category": "fraud_provider_slowdown",
     "status": "testing", "confidence": 71, "evidence_for_count": 2, "evidence_against_count": 0,
     "evidence_for": [{"signal": "fraud-adapter p95 2.7× baseline"},
                      {"signal": "FraudScoreProviderSlowdown WARN × 206"}],
     "evidence_against": []},
    {"hypothesis_id": "H2", "category": "istio_sidecar_outage",
     "status": "testing", "confidence": 58, "evidence_for_count": 1, "evidence_against_count": 0,
     "evidence_for": [{"signal": "47× Istio 504 on inventory-reserve"}],
     "evidence_against": []},
    {"hypothesis_id": "H3", "category": "non_idempotent_retry_with_reconciliation_masking",
     "status": "testing", "confidence": 82, "evidence_for_count": 3, "evidence_against_count": 0,
     "evidence_for": [
        {"signal": "double wallets.UPDATE in 47/47 traces"},
        {"signal": "RetryAttempt=2 log cluster 47×"},
        {"signal": "payment_ledger_write_total{retry=true} 15× baseline"},
     ], "evidence_against": []},
    {"hypothesis_id": "H4", "category": "wallet_replication_lag_stale_read",
     "status": "testing", "confidence": 41, "evidence_for_count": 0, "evidence_against_count": 0,
     "evidence_for": [], "evidence_against": []},
]}})

evt(26.2, "supervisor", "summary",
    "4 hypotheses under evaluation: H1 fraud-slow (71%), H2 istio-outage (58%), "
    "H3 retry-without-idempotency (82%), H4 wallet-replication-lag (41%).",
    {"hypothesis_count": 4})

# Eliminate H1 — the convincing false lead
evt(27.0, "supervisor", "started",
    "Testing H1 (fraud-adapter). If true, latency distribution should be unimodal near 380ms.")
# ReAct loop for H1
evt(27.4, "metric_agent", "reasoning", "REASON: H1 says fraud-adapter slowdown caused the incident.")
evt(27.8, "metric_agent", "tool_call",
    "prometheus.query_range(histogram_quantile(0.99, fraud_score_duration_seconds), window=4h)")
evt(28.5, "metric_agent", "finding",
    "OBSERVE: fraud-adapter distribution is bimodal — two peaks (140ms baseline, 380ms elevated). "
    "A unimodal shift would be consistent with H1; observed shape isn't.",
    {"h": "H1", "observation": "bimodal_distribution"})
evt(29.0, "metric_agent", "reasoning",
    "REFLECT: contribution math: fraud ~240ms (2.7× baseline); istio ~14,863ms. "
    "fraud explains 1.6% of incident latency. H1 ruled out.")
evt(29.4, "supervisor", "finding",
    "H1 eliminated: fraud-adapter accounts for 1.6% of incident latency — not load-bearing.",
    {"h": "H1", "outcome": "eliminated", "confidence": 94})
token_patch(29.6, "metric_agent", 400, 60)

# Eliminate H2
evt(30.2, "supervisor", "started", "Testing H2 (istio outage).")
evt(30.6, "k8s_agent", "reasoning", "REASON: H2 requires istio pods Unready or CrashLoop.")
evt(31.0, "k8s_agent", "tool_call", "kubectl.get(pods, namespace=istio-system)")
evt(31.4, "k8s_agent", "finding",
    "OBSERVE: all istio-system pods Ready; zero restarts. Sidecars healthy.",
    {"h": "H2", "observation": "istio_all_ready"})
evt(31.8, "k8s_agent", "reasoning",
    "REFLECT: upstream_cx_overflow is a connection-pool-depth event, not an outage. H2 fails.")
evt(32.2, "supervisor", "finding",
    "H2 eliminated: istio data plane healthy; the 504 is a configured 15s timeout, not a failure.",
    {"h": "H2", "outcome": "eliminated", "confidence": 91})
token_patch(32.4, "k8s_agent", 200, 50)

# Eliminate H4
evt(33.0, "supervisor", "started", "Testing H4 (wallet replication lag).")
evt(33.4, "metric_agent", "tool_call",
    "prometheus.query_range(wallet_replication_lag_ms, window=4h)")
evt(34.0, "metric_agent", "finding",
    "wallet replication lag <50ms throughout incident. No stale reads possible.",
    {"h": "H4", "observation": "replication_lag_low"})
evt(34.4, "supervisor", "finding",
    "H4 eliminated: replication lag never exceeded 50ms.",
    {"h": "H4", "outcome": "eliminated", "confidence": 97})
token_patch(34.6, "metric_agent", 180, 40)

# Record elimination log in state
patch(35.0, {"state": {
    "hypotheses": [
        {"hypothesis_id": "H1", "category": "fraud_provider_slowdown",
         "status": "eliminated", "confidence": 6, "elimination_reason": "Latency contribution 1.6%; bimodal distribution",
         "elimination_phase": "cross_check"},
        {"hypothesis_id": "H2", "category": "istio_sidecar_outage",
         "status": "eliminated", "confidence": 9, "elimination_reason": "Istio data plane healthy; 504 is a configured timeout",
         "elimination_phase": "cross_check"},
        {"hypothesis_id": "H3", "category": "non_idempotent_retry_with_reconciliation_masking",
         "status": "winner", "confidence": 88,
         "evidence_for_count": 5, "evidence_against_count": 0},
        {"hypothesis_id": "H4", "category": "wallet_replication_lag_stale_read",
         "status": "eliminated", "confidence": 3, "elimination_reason": "Replication lag <50ms throughout",
         "elimination_phase": "cross_check"},
    ],
    "hypothesis_result": {
        "status": "provisional",
        "winner_id": "H3",
        "elimination_log": [
            {"h": "H1", "reason": "Latency contribution 1.6%; bimodal distribution"},
            {"h": "H2", "reason": "Istio data plane healthy; 504 is a configured timeout"},
            {"h": "H4", "reason": "Replication lag <50ms throughout"},
        ],
        "recommendations": [],
    }
}})

evt(35.4, "supervisor", "summary",
    "Elimination round complete: H1, H2, H4 ruled out. H3 is the winner candidate (88% prov.).")
budget_patch(36.0, 11, 0.015)


# ── Phase 3 — code_agent + critic ─────────────────────────────────────


phase(38.0, "diagnosing")

evt(38.2, "code_agent", "started",
    "Opening repos: zepay/payment-service, zepay/shared-finance-models, zepay/reconciliation-job.")
evt(38.8, "code_agent", "tool_call",
    "github.clone(zepay/payment-service, ref=main)")
evt(39.4, "code_agent", "tool_call",
    "ripgrep('@Retryable' in payment-service/src) — locating retry wrappers")
evt(40.0, "code_agent", "finding",
    "Found @Retryable on PaymentExecutor.execute() — wraps BOTH ledger.debit() AND inventoryClient.reserve(). "
    "Retry re-runs the mutation.",
    {"file_path": "payment-service/src/main/java/com/zepay/payment/ledger/PaymentExecutor.java",
     "line": 127})
token_patch(40.2, "code_agent", 3200, 180)

evt(40.8, "code_agent", "reasoning",
    "The mutation (ledger.debit) has no idempotency-key. On retry, fresh txn_id → second row in ledger.txns.")
evt(41.4, "code_agent", "tool_call",
    "github.clone(zepay/shared-finance-models)")
evt(42.0, "code_agent", "tool_call",
    "open(shared-finance-models/Money.java:38)")
evt(42.6, "code_agent", "finding",
    "Money.java stores `amount` as `double`. $87.41 + $87.41 = 174.81999999999999 (IEEE-754 drift).",
    {"file_path": "shared-finance-models/src/main/java/com/zepay/finance/Money.java",
     "line": 38, "defect": "double-based arithmetic"})
evt(43.2, "code_agent", "tool_call",
    "github.clone(zepay/reconciliation-job)")
evt(43.8, "code_agent", "tool_call",
    "open(reconciliation-job/src/reconcile/NightlyReconcile.py:88)")
evt(44.4, "code_agent", "finding",
    "NightlyReconcile auto-rounds any drift < $0.02 — swallows duplicate-charge signals.",
    {"file_path": "reconciliation-job/src/reconcile/NightlyReconcile.py", "line": 88,
     "defect": "threshold absorbs signal"})
evt(45.0, "code_agent", "reasoning",
    "Three-bug stack confirmed. Primary: PaymentExecutor. Amplifier: Money. Suppressor: NightlyReconcile.")

patch(45.3, {"state": {
    "code_analysis": {
        "root_cause_location": {
            "file_path": "payment-service/src/main/java/com/zepay/payment/ledger/PaymentExecutor.java",
            "impact_type": "direct_error",
            "relevant_lines": [{"start": 127, "end": 145}],
            "code_snippet": "@Retryable(retryFor={UpstreamTimeoutException.class}, maxAttempts=2)\npublic PaymentResult execute(PaymentRequest req) {\n    LedgerTxn txn = ledger.debit(req.customer_id(), req.amount_cents(), req.currency());\n    inventoryClient.reserve(req.cart_id(), ...);\n    return PaymentResult.success(txn.id());\n}",
            "relationship": "root",
            "fix_relevance": "must_fix",
        },
        "impacted_files": [
            {"file_path": "shared-finance-models/src/main/java/com/zepay/finance/Money.java",
             "impact_type": "contributing", "relevant_lines": [{"start": 38, "end": 54}],
             "relationship": "amplifier", "fix_relevance": "should_fix"},
            {"file_path": "reconciliation-job/src/reconcile/NightlyReconcile.py",
             "impact_type": "contributing", "relevant_lines": [{"start": 88, "end": 96}],
             "relationship": "signal_masker", "fix_relevance": "should_fix"},
        ],
        "suggested_fix_areas": [
            {"file_path": "payment-service/src/main/java/com/zepay/payment/ledger/PaymentExecutor.java",
             "description": "Add idempotency-key to ledger.debit; move mutation outside @Retryable.",
             "suggested_change": "Thread req.idempotency_key() → ledger.debit(customerId, amount, currency, idempotencyKey); retry only the reserve call."},
            {"file_path": "shared-finance-models/src/main/java/com/zepay/finance/Money.java",
             "description": "Replace double with BigDecimal; enforce currency scale.",
             "suggested_change": "Migrate Money.amount to BigDecimal.setScale(currency.scale(), RoundingMode.UNNECESSARY)."},
            {"file_path": "reconciliation-job/src/reconcile/NightlyReconcile.py",
             "description": "Lower auto-round threshold; escalate sub-cent diffs.",
             "suggested_change": "Drop threshold from $0.02 to $0.001; P3 alert for any drift > $0.001."},
        ],
        "code_call_chain": [
            "api-gateway.POST /api/v1/checkout",
            "checkout-service.POST /pay",
            "payment-service.PaymentExecutor.execute",
            "payment-service.LedgerClient.debit",
            "wallet-service.POST /v1/debit",
            "payment-service.InventoryClient.reserve",
            "istio-proxy → inventory-service (15s timeout)",
            "@Retryable reissue → PaymentExecutor.execute (2nd time)",
            "payment-service.LedgerClient.debit (2nd call, fresh txn_id)",
            "wallet-service.POST /v1/debit (GHOST DEBIT)",
        ],
        "code_cross_repo_findings": [
            {"repo": "zepay/payment-service", "role": "primary_cause",
             "evidence": "Retry wrapper re-runs mutation without idempotency-key."},
            {"repo": "zepay/shared-finance-models", "role": "contributing_library",
             "evidence": "double-based Money arithmetic masks sub-cent duplicate drift."},
            {"repo": "zepay/reconciliation-job", "role": "signal_masker",
             "evidence": "$0.02 auto-round threshold swallows the duplicate-charge signal."},
        ],
        "code_overall_confidence": 94,
    }
}})

evt(45.8, "code_agent", "summary",
    "3 defects across 3 repos. Primary: PaymentExecutor.java:127. "
    "Amplifier: Money.java:38. Suppressor: NightlyReconcile.py:88.",
    {"duration_s": 7.6, "defects": 3, "confidence": 94})
token_patch(46.0, "code_agent", 1200, 480)
patch(46.2, {"state": {"agents_completed[+]": "code_agent"}})


# critic round — advocate / challenger / judge
evt(47.0, "critic", "started",
    "Critic ensemble activating. advocate, challenger, judge.")
evt(47.5, "critic", "reasoning",
    "ADVOCATE: three independent signals — trace double-span, log retry-cluster, "
    "metric retry-counter — all point to the same defect.")
evt(48.0, "critic", "finding",
    "advocate verdict: CONFIRMED (89%)",
    {"role": "advocate", "verdict": "confirmed", "confidence": 89})

evt(48.6, "critic", "reasoning",
    "CHALLENGER: looking for failure modes — is attribution across all 47 complaints sound?")
evt(49.2, "critic", "tool_call",
    "jaeger.replay(trace_ids=[control group, 5 non-complaint traces])")
evt(49.8, "critic", "finding",
    "Some control traces don't have the double-span pattern. "
    "Evidence gap: subset of 47 may include card-network-side dupes.",
    {"role": "challenger", "evidence_gap": "attribution_completeness"})
evt(50.2, "critic", "finding",
    "challenger verdict: CHALLENGED (74%) — attribution uncertain on ~5/47.",
    {"role": "challenger", "verdict": "challenged", "confidence": 74})

evt(50.8, "critic", "reasoning",
    "JUDGE: even if 5/47 are card-network dupes, the code defect is independently proven. "
    "Recommend fix code now; reconcile attribution after.")
evt(51.3, "critic", "finding",
    "judge verdict: CONFIRMED with caveat.",
    {"role": "judge", "verdict": "confirmed_with_caveat", "confidence": 88,
     "caveat": "Per-customer attribution subject to post-fix audit"})

patch(51.5, {"state": {"critic_verdicts": [
    {"finding_index": 0, "verdict": "confirmed", "confidence_in_verdict": 89,
     "reasoning": "Three independent signals converge on H3"},
    {"finding_index": 0, "verdict": "challenged", "confidence_in_verdict": 74,
     "reasoning": "Attribution gap on ~5/47 complaints"},
    {"finding_index": 0, "verdict": "confirmed", "confidence_in_verdict": 88,
     "reasoning": "Code defect independently proven; attribution refinement post-fix"},
]}})

# Re-investigation round
evt(52.0, "supervisor", "started",
    "Challenger dissent exceeds threshold. Triggering one re-investigation round.")
evt(52.5, "metric_agent", "started", "Re-running with narrower window.")
evt(52.9, "metric_agent", "reasoning",
    "REASON: tight window on last 90min should sharpen retry-counter signal.")
evt(53.3, "metric_agent", "tool_call",
    "prometheus.query_range(payment_ledger_write_total{retry=true}, window=90m, step=15s)")
evt(54.0, "metric_agent", "finding",
    "OBSERVE: 15.3× baseline sustained in tight window. Not spurious.",
    {"refined_metric": "payment_ledger_write_total{retry=true}",
     "tight_window_peak": 0.29, "baseline": 0.019})
evt(54.6, "metric_agent", "reasoning",
    "REFLECT: attribution uncertainty doesn't affect the code defect. Confidence rebounds.")

evt(55.0, "supervisor", "finding",
    "Confidence rebounded 74% → 92% after re-investigation.",
    {"before": 74, "after": 92})

patch(55.2, {"state": {
    "hypothesis_result": {
        "status": "resolved",
        "winner_id": "H3",
        "confidence_reasoning": "3 independent signals; critic 2/3 confirmed; re-investigation rebounded",
        "elimination_log": [
            {"h": "H1", "reason": "Latency contribution 1.6%; bimodal distribution"},
            {"h": "H2", "reason": "Istio data plane healthy; 504 is a configured timeout"},
            {"h": "H4", "reason": "Replication lag <50ms throughout"},
        ],
        "recommendations": [
            "Add idempotency-key to ledger.debit (PaymentExecutor.java:127)",
            "Migrate Money to BigDecimal (Money.java:38)",
            "Tighten reconciliation threshold (NightlyReconcile.py:88)",
        ],
    },
    "overall_confidence": 92,
}})

patch(55.4, {"session": {"confidence": 92, "winner_critic_dissent": {
    "advocate_verdict": "confirmed",
    "challenger_verdict": "challenged",
    "judge_verdict": "confirmed",
    "summary": "2/3 critics confirmed after re-investigation; caveat on per-customer attribution",
}}})


# ── Phase 4 — verdict, blast radius, sig match, fix-ready ────────────


evt(56.2, "supervisor", "started",
    "Synthesizing verdict + blast-radius + signature-library lookup.")

# blast radius + notable accounts
evt(57.0, "supervisor", "tool_call",
    "causal_forest.synthesize(winner=H3, affected_services=[payment, checkout, wallet])")
evt(57.8, "supervisor", "finding",
    "Blast radius: 3 services directly affected; 47 customers double-charged; $4,089 refund exposure.")

patch(58.0, {"state": {
    "blast_radius_result": {
        "primary_service": "payment-service",
        "upstream_affected": ["checkout-service", "api-gateway"],
        "downstream_affected": ["wallet-service"],
        "shared_resources": ["reconciliation-job", "shared-finance-models"],
        "estimated_user_impact":
            "47 confirmed duplicate charges totaling $4,089 in refund exposure + "
            "~$880 in Stripe dispute fees. Three VIP escalations: Acme Logistics "
            "($2.1M monthly, SLA clause triggered — $50K + $840K peer-ARR risk); "
            "Sarah Chen (184K-follower food blogger, 2.3M impressions); "
            "@sarah_trades_btc (340K crypto followers, quote-tweeted by @patio11).",
        "scope": "service_group",
        "notable_affected_accounts": [
            {"customer_id": "C-CORP-ACME-LOG-0042",
             "tier": "business_enterprise",
             "stakes_summary": "Acme Logistics — $2.1M/mo volume, SLA tier-1 contract. $50K penalty clause triggered. 3 peer accounts at ARR risk ($840K/yr).",
             "escalation_channel": "relationship_manager + legal",
             "business_severity": "critical"},
            {"customer_id": "C-CHEN-SARAH-8741",
             "tier": "consumer_premium",
             "stakes_summary": "Sarah Chen — food blogger, 184K followers. Pinned tweet on r/personalfinance, 2.3M impressions.",
             "escalation_channel": "pr_team",
             "business_severity": "high"},
            {"customer_id": "C-INFLUENCER-BTC-2291",
             "tier": "consumer_premium",
             "stakes_summary": "@sarah_trades_btc — fintech-Twitter influencer, 340K followers, quote-tweeted by @patio11. Trending #6.",
             "escalation_channel": "pr_team + brand_risk",
             "business_severity": "high"},
        ],
        "business_impact": [
            {"capability": "checkout", "severity": "critical", "affected_services": ["checkout-service"]},
            {"capability": "billing_integrity", "severity": "critical",
             "affected_services": ["payment-service", "reconciliation-job"]},
            {"capability": "customer_trust", "severity": "high",
             "affected_services": ["notification-service"]},
        ],
    }
}})

# Signature library match
evt(58.8, "supervisor", "tool_call",
    "signature_library.match(winner=H3, evidence=[retry,mutation,no_idempotency])")
evt(59.5, "supervisor", "finding",
    "Signature match: retry_without_idempotency_key (89%). Seen in Stripe Q3-2024, Square Q1-2025.",
    {"pattern_name": "retry_without_idempotency_key", "confidence": 0.89})

patch(59.7, {"session": {
    "signature_match": {
        "pattern_name": "retry_without_idempotency_key",
        "confidence": 0.89,
        "matched_at_ms": 0,
        "summary": "Retry wrapper re-executes a mutating operation without an idempotency key.",
        "remediation": "Add idempotency-key header to mutation endpoints; move the mutation outside the retry boundary; or introduce a transactional idempotency table keyed on (client_id, request_id).",
    },
    "diagnosis_stop_reason": "high_confidence_no_challenges",
}})

# Severity
patch(60.2, {"state": {
    "severity_result": {
        "severity": "P1",
        "reasoning":
            "Financial-integrity violation + active social-media exposure + "
            "regulatory-reporting implications (FDIC dispute-reporting threshold exceeded).",
        "regulatory_flags": ["FDIC", "PCI-DSS 10.8"],
        "recommended_responders": ["payments-oncall", "platform-oncall", "finance-controller", "legal-regulatory"],
    }
}})

# Past incidents
patch(60.5, {"state": {"past_incidents": [
    {"incident_id": "INC-2026-0211-checkout-cart-sync-drift",
     "title": "Cart items out of sync between Redis and Postgres projection",
     "resolved_at": "2026-02-11T18:14:00Z",
     "similarity_score": 0.32,
     "shared_services": ["checkout-service"]},
]}})

# Evidence pins from reasoning_chain
patch(61.0, {"state": {
    "evidence_pins": [
        {"id": "pin-1", "label": "Retry log cluster (47 occurrences)",
         "source": "log_agent", "confidence": 89},
        {"id": "pin-2", "label": "Double wallets.UPDATE spans (47/47 complaint traces)",
         "source": "tracing_agent", "confidence": 97},
        {"id": "pin-3", "label": "payment_ledger_write_total{retry=true} 15× baseline",
         "source": "metric_agent", "confidence": 88},
        {"id": "pin-4", "label": "PaymentExecutor.java:127 @Retryable wrapping mutation",
         "source": "code_agent", "confidence": 94},
        {"id": "pin-5", "label": "Reconciliation $0.02 auto-round silences signal",
         "source": "code_agent", "confidence": 93},
    ],
    "reasoning_chain": [
        {"step": 1, "claim": "User perception: checkout broken",
         "refuted_by": "log_agent cluster points at payment-service"},
        {"step": 2, "claim": "Retry fires 47× on inventory-reserve",
         "evidence": ["log cluster", "metric counter"]},
        {"step": 3, "claim": "Retry re-runs ledger.debit() — mutation",
         "evidence": ["trace waterfall shows 2× wallets.UPDATE"]},
        {"step": 4, "claim": "Reconciliation should have caught; didn't",
         "evidence": ["$0.02 threshold absorbs drift from Money.java float-math"]},
    ],
}})

evt(61.4, "supervisor", "summary",
    "Verdict landed. Non-idempotent retry under Istio sidecar timeout. Confidence 92%. "
    "Severity P1 — financial-integrity + social-media + regulatory.",
    {"confidence": 92, "severity": "P1"})
budget_patch(62.0, 23, 0.028)


# Fix-pipeline enters
phase(62.5, "diagnosis_complete")

evt(63.0, "code_agent", "started",
    "Generating fix diffs across 3 repos.")
evt(63.6, "code_agent", "tool_call",
    "generate_fix(repo=zepay/payment-service, file=PaymentExecutor.java:127)")
evt(64.2, "code_agent", "finding",
    "Fix drafted for payment-service: idempotency-key threading + mutation outside @Retryable.",
    {"repo": "zepay/payment-service", "pr": 8427, "lines_added": 31, "lines_removed": 8})
evt(65.0, "code_agent", "tool_call",
    "generate_fix(repo=zepay/shared-finance-models, file=Money.java:38)")
evt(65.6, "code_agent", "finding",
    "Fix drafted for shared-finance-models: double → BigDecimal; breaking semver.",
    {"repo": "zepay/shared-finance-models", "pr": 1203, "lines_added": 47, "lines_removed": 22})
evt(66.2, "code_agent", "tool_call",
    "generate_fix(repo=zepay/reconciliation-job, file=NightlyReconcile.py:88)")
evt(66.8, "code_agent", "finding",
    "Fix drafted for reconciliation-job: threshold $0.02 → $0.001; P3 escalation for sub-cent.",
    {"repo": "zepay/reconciliation-job", "pr": 294, "lines_added": 19, "lines_removed": 5})

patch(67.2, {"state": {"fix_result": {
    "campaign_id": "campaign-zepay-demo-0001",
    "repos": [
        {"repo_url": "zepay/payment-service",
         "service_name": "payment-service",
         "pr_url": "https://github.com/zepay/payment-service/pull/8427",
         "pr_number": 8427,
         "causal_role": "root_cause",
         "status": "drafted",
         "lines_added": 31, "lines_removed": 8,
         "fix_explanation": "Add idempotency-key to ledger.debit; move mutation outside @Retryable.",
         "diff": "@@ -121,15 +121,24 @@\n-@Retryable(retryFor={UpstreamTimeoutException.class}, maxAttempts=2)\n public PaymentResult execute(PaymentRequest req) {\n-    LedgerTxn txn = ledger.debit(req.customer_id(), req.amount_cents(), req.currency());\n-    inventoryClient.reserve(req.cart_id(), items);\n+    String idemKey = req.idempotency_key() != null ? req.idempotency_key()\n+                         : (req.customer_id() + \":\" + req.cart_id());\n+    LedgerTxn txn = ledger.debit(req.customer_id(), req.amount_cents(), req.currency(), idemKey);\n+    reserveWithRetry(req.cart_id(), idemKey);\n     return PaymentResult.success(txn.id());\n }\n+\n+@Retryable(retryFor={UpstreamTimeoutException.class}, maxAttempts=2)\n+private void reserveWithRetry(String cartId, String idemKey) {\n+    inventoryClient.reserve(cartId, items, idemKey);\n+}",
         },
        {"repo_url": "zepay/shared-finance-models",
         "service_name": "shared-finance-models",
         "pr_url": "https://github.com/zepay/shared-finance-models/pull/1203",
         "pr_number": 1203,
         "causal_role": "contributing",
         "status": "drafted",
         "lines_added": 47, "lines_removed": 22,
         "fix_explanation": "Replace double with BigDecimal; deprecate .plus() without currency scale.",
         "diff": "@@ -1,43 +1,58 @@\n-private final double amount;\n+private final BigDecimal amount;\n ...\n-return new Money(this.amount + other.amount, this.currency);\n+return new Money(this.amount.add(other.amount), this.currency);",
         },
        {"repo_url": "zepay/reconciliation-job",
         "service_name": "reconciliation-job",
         "pr_url": "https://github.com/zepay/reconciliation-job/pull/294",
         "pr_number": 294,
         "causal_role": "signal_masker",
         "status": "drafted",
         "lines_added": 19, "lines_removed": 5,
         "fix_explanation": "Lower drift threshold to $0.001; escalate sub-cent diffs as P3.",
         "diff": "@@ -82,10 +82,15 @@\n-if abs(diff) < 0.02:\n-    log.info(...)\n-    continue\n+if abs(diff) < 0.001:\n+    continue\n+if abs(diff) < 0.02:\n+    log.warning(\"sub-cent drift\"); alert_finance_oncall(P3)\n+    continue",
         },
    ],
    "overall_status": "awaiting_approval",
    "approved_count": 0,
    "total_count": 3,
}}})

evt(67.8, "supervisor", "finding",
    "FixReadyBar activated. 3 PRs drafted. Primary stops-the-bleeding; 2 prevent recurrence.")

# Attestation gate
phase(68.0, "awaiting_approval")

TIMELINE.append({
    "t": 68.2,
    "kind": "await_approval",
    "message": "Three fix PRs drafted — awaiting operator approval to merge sequence.",
    "pending_action": {
        "type": "attestation",
        "title": "Approve 3 PRs to remediate INC-2026-0421-payment-ledger-ghost-debits",
        "description": "Primary: payment-service #8427 (stop the bleeding). "
                       "Secondary: shared-finance-models #1203 + reconciliation-job #294 (close blind spot).",
        "options": [
            {"value": "approved", "label": "Approve & merge (sequential)"},
            {"value": "rejected", "label": "Reject — escalate to payments lead"},
        ],
    },
})


# ── Phase 5 — post-approval: sequential PR merges ─────────────────────


# These t values are MEASURED FROM APPROVAL, because the replayer
# resets t0 when await_approval is released.
phase(68.8, "fix_in_progress")

evt(69.0, "supervisor", "summary",
    "Approval received. Starting sequential rollout. Primary fix first.")

# PR 1: payment-service
evt(70.0, "supervisor", "tool_call",
    "github.open_pr(zepay/payment-service, branch=fix/pr-k4-retry-safety)",
    {"pr": 8427})
evt(70.6, "supervisor", "summary",
    "PR #8427 opened on zepay/payment-service. CI triggering.")
evt(71.2, "supervisor", "progress", "PR #8427 — unit tests running (3/9 passed)")
evt(72.0, "supervisor", "progress", "PR #8427 — unit tests passing (9/9)")
evt(72.6, "supervisor", "progress", "PR #8427 — integration tests running (2/4)")
evt(73.4, "supervisor", "progress", "PR #8427 — integration tests passing (4/4)")
evt(74.0, "supervisor", "success", "PR #8427 merged to main. Rollout canary 25% → 50% → 100%.")

patch(74.2, {"state": {"fix_result": {"repos": [
    {"repo_url": "zepay/payment-service", "pr_number": 8427, "status": "merged",
     "merge_sha": "0a7e4f3b9c1e"},
    {"repo_url": "zepay/shared-finance-models", "pr_number": 1203, "status": "drafted"},
    {"repo_url": "zepay/reconciliation-job", "pr_number": 294, "status": "drafted"},
], "overall_status": "primary_merged", "approved_count": 1, "total_count": 3}}})

# PR 2: shared-finance-models
evt(75.0, "supervisor", "tool_call",
    "github.open_pr(zepay/shared-finance-models, branch=fix/money-bigdecimal)",
    {"pr": 1203})
evt(75.6, "supervisor", "summary",
    "PR #1203 opened on zepay/shared-finance-models. 14 downstream consumers verifying.")
evt(76.4, "supervisor", "progress", "PR #1203 — semver check: BREAKING (expected)")
evt(77.2, "supervisor", "progress", "PR #1203 — downstream consumer tests running")
evt(78.0, "supervisor", "progress", "PR #1203 — 14/14 consumer suites green")
evt(78.6, "supervisor", "success", "PR #1203 merged. shared-finance-models v4.3.0 published.")

patch(78.8, {"state": {"fix_result": {"repos": [
    {"repo_url": "zepay/payment-service", "pr_number": 8427, "status": "merged",
     "merge_sha": "0a7e4f3b9c1e"},
    {"repo_url": "zepay/shared-finance-models", "pr_number": 1203, "status": "merged",
     "merge_sha": "3f2b91c0d8a4"},
    {"repo_url": "zepay/reconciliation-job", "pr_number": 294, "status": "drafted"},
], "overall_status": "amplifier_merged", "approved_count": 2, "total_count": 3}}})

# PR 3: reconciliation-job
evt(79.4, "supervisor", "tool_call",
    "github.open_pr(zepay/reconciliation-job, branch=fix/threshold-tighten)",
    {"pr": 294})
evt(80.0, "supervisor", "summary",
    "PR #294 opened on zepay/reconciliation-job. Config-only change.")
evt(80.6, "supervisor", "progress", "PR #294 — replaying last 90 days of reconciliation at new threshold")
evt(81.4, "supervisor", "progress", "PR #294 — 0 false positives detected at $0.001 threshold")
evt(82.0, "supervisor", "success", "PR #294 merged. Next recon run at 03:00 UTC will use new threshold.")

patch(82.2, {"state": {"fix_result": {"repos": [
    {"repo_url": "zepay/payment-service", "pr_number": 8427, "status": "merged",
     "merge_sha": "0a7e4f3b9c1e"},
    {"repo_url": "zepay/shared-finance-models", "pr_number": 1203, "status": "merged",
     "merge_sha": "3f2b91c0d8a4"},
    {"repo_url": "zepay/reconciliation-job", "pr_number": 294, "status": "merged",
     "merge_sha": "91eac47b6d22"},
], "overall_status": "all_merged", "approved_count": 3, "total_count": 3}}})

# Closure
evt(83.0, "supervisor", "tool_call",
    "verify.deploy_health(payment-service, window=5min)")
evt(83.8, "supervisor", "success",
    "Post-fix verification: retry-counter baseline, duplicate-wallets-span pattern 0/0 in last 5 min.")

patch(84.2, {"state": {
    "closure_state": {
        "status": "resolved",
        "resolution_summary": "3 PRs merged (payment-service #8427, shared-finance-models #1203, reconciliation-job #294). "
                              "Retry-counter baseline restored. No duplicate-debit events in post-fix window.",
        "resolved_at": "2026-04-21T20:00:00Z",
        "time_to_resolution_seconds": 84,
    }
}})

phase(85.0, "complete")

evt(85.2, "supervisor", "summary",
    "Incident resolved. Postmortem dossier available. Total time-to-resolution: ~85 seconds.",
    {"ttr_seconds": 85, "prs_merged": 3})

# Final token burst
token_patch(85.4, "critic", 800, 300)
budget_patch(85.6, 31, 0.041)


# ── Write ─────────────────────────────────────────────────────────────


TIMELINE.sort(key=lambda e: (e["t"], 0 if e["kind"] == "event" else 1))

OUT.write_text(json.dumps(TIMELINE, indent=2))
print(f"wrote {OUT} — {len(TIMELINE)} entries")

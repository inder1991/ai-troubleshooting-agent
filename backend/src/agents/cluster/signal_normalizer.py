"""Signal normalizer: extract canonical signals from domain report data."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.agents.cluster.state import NormalizedSignal
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Signal extraction rules: (field_path, condition, signal_type, reliability)
SIGNAL_RELIABILITY = {
    "node_condition": 1.0,
    "deployment_status": 0.9,
    "pod_phase": 0.8,
    "pvc_status": 0.9,
    "hpa_status": 0.9,
    "daemonset_status": 0.9,
    "service_endpoints": 0.9,
    "k8s_event_warning": 0.6,
    "k8s_event_normal": 0.3,
    "prometheus_metric": 0.5,
    "resource_utilization": 0.6,
    "pod_log": 0.4,
    "coredns_log": 0.4,
    "alert_firing": 0.3,
    "pattern_match": 0.8,
}


def _make_signal(signal_type: str, resource_key: str, domain: str,
                 reliability_key: str, raw_value: Any = None,
                 timestamp: str = "", namespace: str = "") -> NormalizedSignal:
    return NormalizedSignal(
        signal_id=str(uuid.uuid4())[:8],
        signal_type=signal_type,
        resource_key=resource_key,
        source_domain=domain,
        raw_value=raw_value,
        reliability=SIGNAL_RELIABILITY.get(reliability_key, 0.5),
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        namespace=namespace,
    )


def extract_signals(reports: list[dict]) -> list[NormalizedSignal]:
    """Extract canonical signals from all domain reports."""
    signals: list[NormalizedSignal] = []

    for report in reports:
        domain = report.get("domain", "")
        if report.get("status") in ("SKIPPED", "FAILED"):
            continue

        for anomaly in report.get("anomalies", []):
            # Fast path: use explicit signal_type if provided by domain agent
            explicit_type = anomaly.get("signal_type")
            if explicit_type:
                ref = anomaly.get("evidence_ref", "")
                ns = ref.split("/")[0] if "/" in ref else ""
                signals.append(_make_signal(
                    explicit_type, ref, domain,
                    "pod_phase",  # default reliability key
                    namespace=ns
                ))
                continue

            # Slow path: infer from description text
            desc = anomaly.get("description", "").lower()
            ref = anomaly.get("evidence_ref", "")
            severity = anomaly.get("severity", "medium")
            ns = ref.split("/")[0] if "/" in ref else ""

            # Pod status signals
            if "crashloopbackoff" in desc or "crashloop" in desc:
                signals.append(_make_signal("CRASHLOOP", ref, domain, "pod_phase", namespace=ns))
            if "oomkilled" in desc or "oom" in desc:
                signals.append(_make_signal("OOM_KILLED", ref, domain, "pod_phase", namespace=ns))
            if "imagepullbackoff" in desc or "image pull" in desc:
                signals.append(_make_signal("IMAGE_PULL_BACKOFF", ref, domain, "pod_phase", namespace=ns))
            if "pending" in desc and "pod" in desc:
                signals.append(_make_signal("POD_PENDING", ref, domain, "pod_phase", namespace=ns))

            # Node signals
            if "notready" in desc.replace(" ", "").lower() or "not ready" in desc:
                signals.append(_make_signal("NODE_NOT_READY", ref, domain, "node_condition", namespace=ns))
            if "diskpressure" in desc.replace(" ", "").lower() or "disk pressure" in desc:
                signals.append(_make_signal("NODE_DISK_PRESSURE", ref, domain, "node_condition", namespace=ns))
            if "memorypressure" in desc.replace(" ", "").lower() or "memory pressure" in desc:
                signals.append(_make_signal("NODE_MEMORY_PRESSURE", ref, domain, "node_condition", namespace=ns))
            if "pidpressure" in desc.replace(" ", "").lower():
                signals.append(_make_signal("NODE_PID_PRESSURE", ref, domain, "node_condition", namespace=ns))

            # Workload signals
            if "stuck rollout" in desc or "replicas_ready" in desc and "desired" in desc:
                signals.append(_make_signal("DEPLOYMENT_DEGRADED", ref, domain, "deployment_status", namespace=ns))
            if "rollout" in desc and ("stuck" in desc or "progress" in desc.lower()):
                signals.append(_make_signal("ROLLOUT_STUCK", ref, domain, "deployment_status", namespace=ns))
            if "daemonset" in desc and "unavailable" in desc:
                signals.append(_make_signal("DAEMONSET_INCOMPLETE", ref, domain, "daemonset_status", namespace=ns))

            # Service signals
            if "endpoint" in desc and ("0" in desc or "zero" in desc or "no endpoint" in desc):
                signals.append(_make_signal("SERVICE_ZERO_ENDPOINTS", ref, domain, "service_endpoints", namespace=ns))
            if "loadbalancer" in desc and "pending" in desc:
                signals.append(_make_signal("LB_PENDING", ref, domain, "service_endpoints", namespace=ns))

            # Scheduling
            if "failedscheduling" in desc.replace(" ", "").lower() or "failed scheduling" in desc:
                signals.append(_make_signal("FAILED_SCHEDULING", ref, domain, "k8s_event_warning", namespace=ns))

            # HPA
            if "hpa" in desc and ("max" in desc or "scaling" in desc and "limited" in desc):
                signals.append(_make_signal("HPA_AT_MAX", ref, domain, "hpa_status", namespace=ns))

            # Storage
            if "pvc" in desc and "pending" in desc:
                signals.append(_make_signal("PVC_PENDING", ref, domain, "pvc_status", namespace=ns))

            # Evictions
            if "evict" in desc:
                signals.append(_make_signal("POD_EVICTION", ref, domain, "k8s_event_warning", namespace=ns))

            # Jobs
            if "backoff" in desc and "job" in desc:
                signals.append(_make_signal("JOB_BACKOFF_EXCEEDED", ref, domain, "k8s_event_warning", namespace=ns))

            # DNS
            if "dns" in desc and ("fail" in desc or "error" in desc):
                signals.append(_make_signal("DNS_FAILURE", ref, domain, "coredns_log", namespace=ns))

            # Network policy
            if "networkpolicy" in desc.replace(" ", "").lower() and "empty" in desc:
                signals.append(_make_signal("NETPOL_EMPTY_INGRESS", ref, domain, "k8s_event_warning", namespace=ns))

            # Restarts
            if "restart" in desc:
                try:
                    # Try to extract restart count
                    import re
                    nums = re.findall(r'\d+', desc)
                    if nums and int(nums[0]) > 5:
                        signals.append(_make_signal("HIGH_RESTART_COUNT", ref, domain, "pod_phase",
                                                    raw_value=int(nums[0]), namespace=ns))
                except Exception:
                    pass

            # RBAC
            if "rbac" in desc or "permission" in desc or "forbidden" in desc:
                signals.append(_make_signal("RBAC_PERMISSION_DENIED", ref, domain, "k8s_event_warning", namespace=ns))

    # Deduplicate by (signal_type, resource_key)
    seen = set()
    deduped = []
    for s in signals:
        key = (s.signal_type, s.resource_key)
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    logger.info("Extracted %d signals from %d reports", len(deduped), len(reports))
    return deduped


@traced_node(timeout_seconds=3)
async def signal_normalizer(state: dict, config: dict) -> dict:
    """Extract canonical signals from domain reports. Deterministic, zero LLM cost."""
    reports = state.get("domain_reports", [])
    signals = extract_signals(reports)
    return {"normalized_signals": [s.model_dump(mode="json") for s in signals]}

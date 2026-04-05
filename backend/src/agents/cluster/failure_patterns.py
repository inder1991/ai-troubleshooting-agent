"""Known failure pattern library and matcher."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.agents.cluster.state import FailurePattern, PatternMatch, NormalizedSignal
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pattern Library — 15 known K8s failure patterns
# ---------------------------------------------------------------------------

FAILURE_PATTERNS: list[FailurePattern] = [
    FailurePattern(
        pattern_id="CRASHLOOP_OOM",
        name="CrashLoopBackOff due to OOM",
        version="1.0", scope="resource", priority=10,
        conditions=[{"signal": "CRASHLOOP"}, {"signal": "OOM_KILLED"}],
        probable_causes=["Memory limit too low", "Memory leak in application"],
        known_fixes=["Increase memory limits", "Profile application memory usage"],
        severity="high", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="CRASHLOOP_CONFIG",
        name="CrashLoopBackOff due to config error",
        version="1.0", scope="resource", priority=5,
        conditions=[{"signal": "CRASHLOOP"}],
        probable_causes=["Bad env var or secret", "Missing ConfigMap", "Invalid command/args"],
        known_fixes=["Check pod logs", "Verify ConfigMap/Secret mounts", "Check readiness probe"],
        severity="high", confidence_boost=0.15,
    ),
    FailurePattern(
        pattern_id="SERVICE_NO_ENDPOINTS",
        name="Service with zero endpoints",
        version="1.0", scope="namespace", priority=8,
        conditions=[{"signal": "SERVICE_ZERO_ENDPOINTS"}],
        probable_causes=["Selector mismatch", "No ready pods matching selector", "All backend pods crashed"],
        known_fixes=["Compare service selector with pod labels", "Check pod readiness"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="SCHEDULING_FAILURE",
        name="Pod pending due to scheduling failure",
        version="1.0", scope="cluster", priority=7,
        conditions=[{"signal": "FAILED_SCHEDULING"}],
        probable_causes=["Insufficient CPU/memory", "Node affinity mismatch", "Taints blocking scheduling"],
        known_fixes=["Scale cluster nodes", "Adjust resource requests", "Check node taints"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="NODE_DISK_FULL",
        name="Node NotReady due to disk pressure",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "NODE_NOT_READY"}, {"signal": "NODE_DISK_PRESSURE"}],
        probable_causes=["Disk full on node", "Container images filling disk", "Logs not rotated"],
        known_fixes=["Clean /var/lib/containerd", "Increase node disk", "Configure log rotation"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="HPA_CEILING",
        name="HPA at max replicas with unmet target",
        version="1.0", scope="namespace", priority=7,
        conditions=[{"signal": "HPA_AT_MAX"}],
        probable_causes=["Cluster capacity ceiling", "Insufficient node capacity"],
        known_fixes=["Increase HPA maxReplicas", "Add cluster nodes", "Optimize application"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="IMAGE_PULL_FAIL",
        name="ImagePullBackOff",
        version="1.0", scope="resource", priority=6,
        conditions=[{"signal": "IMAGE_PULL_BACKOFF"}],
        probable_causes=["Bad image tag", "Registry authentication failure", "Registry unreachable"],
        known_fixes=["Verify image tag exists", "Check imagePullSecrets", "Test registry connectivity"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="STUCK_ROLLOUT",
        name="Deployment stuck rollout",
        version="1.0", scope="namespace", priority=8,
        conditions=[{"signal": "DEPLOYMENT_DEGRADED"}, {"signal": "ROLLOUT_STUCK"}],
        probable_causes=["Readiness probe failing", "Insufficient resources", "Image issue"],
        known_fixes=["Check pod events", "Rollback deployment", "Fix readiness probe"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="PVC_STUCK",
        name="PVC stuck in Pending",
        version="1.0", scope="namespace", priority=6,
        conditions=[{"signal": "PVC_PENDING"}],
        probable_causes=["No matching StorageClass", "Storage capacity exhausted", "Provisioner failure"],
        known_fixes=["Check StorageClass", "Verify CSI driver health", "Check provisioner logs"],
        severity="medium", confidence_boost=0.15,
    ),
    FailurePattern(
        pattern_id="DNS_FAILURE",
        name="DNS resolution failure",
        version="1.0", scope="cluster", priority=8,
        conditions=[{"signal": "DNS_FAILURE"}],
        probable_causes=["CoreDNS pods crashed", "CoreDNS misconfigured", "Network policy blocking DNS"],
        known_fixes=["Check CoreDNS pods", "Verify CoreDNS ConfigMap", "Check network policies"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="NODE_PRESSURE_EVICTION",
        name="Pod evictions from node pressure",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "POD_EVICTION"}, {"signal": "NODE_DISK_PRESSURE"}],
        probable_causes=["Node undersized", "Noisy neighbor consuming resources"],
        known_fixes=["Increase node resources", "Set resource limits on all pods", "Add node affinity"],
        severity="critical", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="DAEMONSET_GAPS",
        name="DaemonSet not on all nodes",
        version="1.0", scope="cluster", priority=5,
        conditions=[{"signal": "DAEMONSET_INCOMPLETE"}],
        probable_causes=["Node taint blocking", "Resource conflict", "DaemonSet update rolling"],
        known_fixes=["Check node taints and tolerations", "Verify DaemonSet resource requests"],
        severity="medium", confidence_boost=0.1,
    ),
    FailurePattern(
        pattern_id="NETPOL_BLOCKING_CONFIRMED",
        name="NetworkPolicy blocking traffic (confirmed)",
        version="1.0", scope="namespace", priority=8,
        conditions=[{"signal": "NETPOL_EMPTY_INGRESS"}, {"signal": "SERVICE_ZERO_ENDPOINTS"}],
        probable_causes=["Overly restrictive NetworkPolicy", "Default-deny without allow rules"],
        known_fixes=["Review NetworkPolicy ingress rules", "Add allow rules for required traffic"],
        severity="high", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="NETPOL_SUSPICIOUS",
        name="NetworkPolicy with empty ingress (suspicious)",
        version="1.0", scope="namespace", priority=4,
        conditions=[{"signal": "NETPOL_EMPTY_INGRESS"}],
        probable_causes=["Overly restrictive NetworkPolicy", "Default-deny without allow rules"],
        known_fixes=["Review NetworkPolicy ingress rules", "Add allow rules for required traffic"],
        severity="medium", confidence_boost=0.1,
    ),
    FailurePattern(
        pattern_id="JOB_FAILURE",
        name="Job exceeded backoff limit",
        version="1.0", scope="namespace", priority=5,
        conditions=[{"signal": "JOB_BACKOFF_EXCEEDED"}],
        probable_causes=["Application bug", "Dependency failure", "Resource constraints"],
        known_fixes=["Check job pod logs", "Verify job dependencies", "Increase backoffLimit"],
        severity="medium", confidence_boost=0.1,
    ),
    FailurePattern(
        pattern_id="NODE_MEMORY_EVICTION",
        name="Pod evictions from memory pressure",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "POD_EVICTION"}, {"signal": "NODE_MEMORY_PRESSURE"}],
        probable_causes=["Node memory exhausted", "Pod without memory limits consuming too much"],
        known_fixes=["Set memory limits on all pods", "Increase node memory", "Identify memory-heavy pods"],
        severity="critical", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="OPERATOR_SCALED_DOWN",
        name="Operator degraded or scaled down",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "OPERATOR_DEGRADED"}],
        probable_causes=["Operator pods scaled to zero", "Operator uninstalled", "CVO issue"],
        known_fixes=["Check operator pods", "Check ClusterVersion status", "Restart operator pod"],
        severity="critical", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="OPERATOR_UPGRADE_STUCK",
        name="Operator upgrade stuck progressing",
        version="1.0", scope="cluster", priority=7,
        conditions=[{"signal": "OPERATOR_PROGRESSING"}],
        probable_causes=["Cluster version upgrade in progress", "Operator pod OOM during upgrade", "Node drain stuck"],
        known_fixes=["Wait for upgrade to complete", "Check operator logs", "Check node drain status"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="ETCD_QUORUM_LOSS",
        name="Etcd quorum loss (operator degraded + node down)",
        version="1.0", scope="cluster", priority=10,
        conditions=[{"signal": "OPERATOR_DEGRADED"}, {"signal": "NODE_NOT_READY"}],
        probable_causes=["Control plane node failure", "Network partition", "Etcd disk full"],
        known_fixes=["Restore failed node", "Check etcd member health", "Check disk space on control plane nodes"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="WEBHOOK_BLOCKING",
        name="Webhook blocking API operations",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "WEBHOOK_FAILURE"}],
        probable_causes=["Webhook backend down", "External service unreachable", "Certificate expired"],
        known_fixes=["Change failurePolicy to Ignore", "Fix webhook backend", "Delete stale webhook config"],
        severity="critical", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="INIT_CONTAINER_STUCK_PATTERN",
        name="Init container stuck preventing pod start",
        version="1.0", scope="resource", priority=7,
        conditions=[{"signal": "INIT_CONTAINER_STUCK"}],
        probable_causes=["Init container image missing", "Init script failing", "Dependency not available"],
        known_fixes=["Check init container logs", "Verify init container image", "Check dependency availability"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="CONFIG_MOUNT_FAILURE",
        name="ConfigMap/Secret mount failure",
        version="1.0", scope="resource", priority=7,
        conditions=[{"signal": "MOUNT_FAILURE"}],
        probable_causes=["ConfigMap/Secret deleted", "Key not found in ConfigMap", "RBAC blocking secret access"],
        known_fixes=["Verify ConfigMap/Secret exists", "Check key names in mount spec", "Check RBAC permissions"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="NETPOL_BLOCKS_DNS",
        name="NetworkPolicy blocking DNS resolution",
        version="1.0", scope="namespace", priority=9,
        conditions=[{"signal": "NETPOL_EMPTY_INGRESS"}, {"signal": "DNS_FAILURE"}],
        probable_causes=["Default-deny egress blocking DNS port 53", "NetworkPolicy missing DNS allow rule"],
        known_fixes=["Add egress rule allowing UDP/TCP port 53 to kube-dns", "Review NetworkPolicy egress rules"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="QUOTA_SCHEDULING_FAILURE",
        name="Quota exceeded causing scheduling failure",
        version="1.0", scope="namespace", priority=8,
        conditions=[{"signal": "QUOTA_EXCEEDED"}, {"signal": "FAILED_SCHEDULING"}],
        probable_causes=["Resource quota exhausted", "Too many pods", "Over-provisioned resource requests"],
        known_fixes=["Increase quota limits", "Reduce resource requests", "Delete unused pods"],
        severity="high", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="CLUSTER_UPGRADE_FAILURE",
        name="Cluster version upgrade stuck or failing",
        version="1.0", scope="cluster", priority=10,
        conditions=[{"signal": "CLUSTER_UPGRADE_STUCK"}],
        probable_causes=["Degraded operator blocking upgrade", "Insufficient node capacity", "etcd health issue"],
        known_fixes=["Check ClusterVersion conditions", "Check degraded operators", "Check node capacity"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="OLM_OPERATOR_INSTALL_FAILURE",
        name="OLM operator install/upgrade failure",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "OLM_SUBSCRIPTION_FAILURE"}, {"signal": "OLM_CSV_FAILURE"}],
        probable_causes=["Operator dependency missing", "RBAC insufficient for operator", "Operator image pull failure"],
        known_fixes=["Check CSV status and events", "Check operator namespace events", "Verify CatalogSource health"],
        severity="critical", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="OLM_UPGRADE_STUCK",
        name="OLM operator upgrade stuck",
        version="1.0", scope="cluster", priority=8,
        conditions=[{"signal": "OLM_SUBSCRIPTION_FAILURE"}, {"signal": "OLM_INSTALLPLAN_STUCK"}],
        probable_causes=["InstallPlan requires manual approval", "InstallPlan stuck in Installing", "CatalogSource not synced"],
        known_fixes=["Approve InstallPlan", "Delete and recreate Subscription", "Check CatalogSource pod health"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="MACHINE_PROVISIONING_FAILURE",
        name="Machine provisioning failure causing node loss",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "MACHINE_FAILURE"}, {"signal": "NODE_NOT_READY"}],
        probable_causes=["Cloud provider quota exhausted", "Machine spec invalid", "Network/subnet issue"],
        known_fixes=["Check Machine conditions", "Verify cloud provider quota", "Check MachineSet spec"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="PROXY_BLOCKS_IMAGE_PULL",
        name="Proxy misconfiguration blocking image pulls",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "PROXY_MISCONFIGURED"}, {"signal": "IMAGE_PULL_BACKOFF"}],
        probable_causes=["noProxy missing registry CIDR", "trustedCA not configured for HTTPS interception", "Proxy blocking registry traffic"],
        known_fixes=["Add registry to noProxy", "Configure trustedCA bundle", "Test registry connectivity through proxy"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="MACHINE_NODE_MISMATCH",
        name="Machine not in Running phase",
        version="1.0", scope="cluster", priority=7,
        conditions=[{"signal": "MACHINE_FAILURE"}],
        probable_causes=["Machine stuck in provisioning", "Cloud provider API error", "Machine deleted but not replaced"],
        known_fixes=["Check Machine object conditions", "Delete stuck Machine to trigger MachineSet replacement", "Check cloud provider console"],
        severity="high", confidence_boost=0.2,
    ),
]


def match_patterns(
    reports: list[dict],
    signals: list[dict],
    patterns: list[FailurePattern] | None = None,
) -> list[PatternMatch]:
    """Match normalized signals against known failure patterns."""
    if patterns is None:
        patterns = FAILURE_PATTERNS

    # Build signal type index
    signal_objects = [NormalizedSignal(**s) if isinstance(s, dict) else s for s in signals]
    signal_type_set = {s.signal_type for s in signal_objects}
    signal_by_type: dict[str, list[NormalizedSignal]] = {}
    for s in signal_objects:
        signal_by_type.setdefault(s.signal_type, []).append(s)

    matches: list[PatternMatch] = []

    for pattern in patterns:
        # Check if ALL conditions are met
        required_signals = [c.get("signal", "") for c in pattern.conditions]
        if not all(sig_type in signal_type_set for sig_type in required_signals):
            continue

        # Collect affected resources from matching signals
        affected = set()
        matched_conds = []
        for sig_type in required_signals:
            matched_conds.append(sig_type)
            for s in signal_by_type.get(sig_type, []):
                affected.add(s.resource_key)

        matches.append(PatternMatch(
            pattern_id=pattern.pattern_id,
            name=pattern.name,
            matched_conditions=matched_conds,
            affected_resources=sorted(affected),
            confidence_boost=pattern.confidence_boost,
            severity=pattern.severity,
            scope=pattern.scope,
            probable_causes=pattern.probable_causes,
            known_fixes=pattern.known_fixes,
        ))

    logger.info("Matched %d patterns from %d signals", len(matches), len(signals))
    return matches


def resolve_priority_conflicts(matches: list[PatternMatch]) -> list[PatternMatch]:
    """When multiple patterns match the same resource, keep highest priority."""
    if len(matches) <= 1:
        return matches

    priority_map = {p.pattern_id: p.priority for p in FAILURE_PATTERNS}

    resource_best: dict[str, str] = {}
    for m in matches:
        pri = priority_map.get(m.pattern_id, 0)
        for res in m.affected_resources:
            current_best = resource_best.get(res)
            if not current_best or pri > priority_map.get(current_best, 0):
                resource_best[res] = m.pattern_id

    keep_ids = set(resource_best.values())
    return [m for m in matches if m.pattern_id in keep_ids]


@traced_node(timeout_seconds=5)
async def failure_pattern_matcher(state: dict, config: RunnableConfig) -> dict:
    """Match normalized signals against known failure patterns. Zero LLM cost."""
    signals = state.get("normalized_signals", [])
    matches = match_patterns([], signals)
    matches = resolve_priority_conflicts(matches)
    logger.info(
        "Pattern matcher: %d matches from %d signals",
        len(matches), len(signals),
        extra={"action": "patterns_matched"},
    )
    return {"pattern_matches": [m.model_dump(mode="json") for m in matches]}

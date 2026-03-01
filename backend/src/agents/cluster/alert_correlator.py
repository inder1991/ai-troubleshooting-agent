"""Alert Correlator — groups cluster events into IssueCluster with root candidates."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from src.agents.cluster.state import (
    ClusterAlert, IssueCluster, RootCandidate,
)
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Alert types that indicate problems
_PROBLEM_STATUSES = frozenset({
    "NotReady", "CrashLoopBackOff", "Evicted", "OOMKilled", "Pending",
    "Degraded", "Unavailable", "ImagePullBackOff", "Error", "Failed",
    "DiskPressure", "MemoryPressure", "PIDPressure",
})


def _extract_alerts(state: dict) -> list[ClusterAlert]:
    """Extract problem alerts from topology nodes."""
    topo = state.get("scoped_topology_graph") or state.get("topology_graph", {})
    nodes = topo.get("nodes", {})
    alerts: list[ClusterAlert] = []

    for key, node in nodes.items():
        status = node.get("status", "")
        if status in _PROBLEM_STATUSES:
            alerts.append(ClusterAlert(
                resource_key=key,
                alert_type=status,
                severity="critical" if status in ("NotReady", "OOMKilled", "Degraded", "Unavailable") else "warning",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
    return alerts


def _build_adjacency(edges: list[dict]) -> dict[str, set[str]]:
    """Build bidirectional adjacency map from topology edges."""
    adj: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        fk = edge.get("from_key")
        tk = edge.get("to_key")
        if fk and tk:
            adj[fk].add(tk)
            adj[tk].add(fk)
    return adj


def _find_connected_component(start: str, adj: dict[str, set[str]]) -> set[str]:
    """BFS to find all resources connected to start."""
    component: set[str] = set()
    visited: set[str] = set()
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        component.add(current)
        for neighbor in adj.get(current, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return component


def _pick_root_candidate(cluster_alerts: list[ClusterAlert], adj: dict[str, set[str]]) -> list[RootCandidate]:
    """Pick the most likely root cause from a cluster of alerts."""
    candidates: list[RootCandidate] = []

    # Heuristic: resource with most connections to other alerts is likely root
    alert_keys = {a.resource_key for a in cluster_alerts}
    for alert in cluster_alerts:
        connected_alerts = alert_keys & adj.get(alert.resource_key, set())
        # Nodes and operators are more likely roots than pods
        kind = alert.resource_key.split("/")[0]
        kind_weight = {"node": 0.3, "operator": 0.25, "deployment": 0.1, "service": 0.1}.get(kind, 0.0)
        confidence = min(1.0, 0.4 + len(connected_alerts) * 0.15 + kind_weight)

        signals = [a.alert_type for a in cluster_alerts if a.resource_key in connected_alerts or a.resource_key == alert.resource_key]

        candidates.append(RootCandidate(
            resource_key=alert.resource_key,
            hypothesis=f"{alert.alert_type} on {alert.resource_key} cascading to connected resources",
            supporting_signals=signals,
            confidence=round(confidence, 2),
        ))

    # Return top 2 by confidence
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates[:2]


@traced_node(timeout_seconds=15)
async def alert_correlator(state: dict, config: dict) -> dict:
    """LangGraph node: correlate alerts into IssueCluster groups."""
    topo = state.get("scoped_topology_graph") or state.get("topology_graph", {})
    edges = topo.get("edges", [])

    # Extract alerts from topology
    alerts = _extract_alerts(state)

    if not alerts:
        logger.info("No problem alerts found", extra={"action": "no_alerts"})
        return {"issue_clusters": []}

    # Build adjacency map
    adj = _build_adjacency(edges)

    # Group alerts by topology connectivity
    visited: set[str] = set()
    clusters: list[IssueCluster] = []
    cluster_idx = 0

    # Sort alerts for deterministic ordering
    alerts.sort(key=lambda a: a.resource_key)

    for alert in alerts:
        if alert.resource_key in visited:
            continue

        # Find all connected resources
        component = _find_connected_component(alert.resource_key, adj)
        # Filter to only resources that have alerts
        alert_keys_in_component = [a for a in alerts if a.resource_key in component]

        if not alert_keys_in_component:
            alert_keys_in_component = [alert]

        visited.update(a.resource_key for a in alert_keys_in_component)

        # Determine correlation basis
        basis = ["topology"] if len(component) > 1 else []

        # Check namespace affinity
        namespaces = {a.resource_key.split("/")[1] for a in alert_keys_in_component if a.resource_key.count("/") >= 2}
        if len(namespaces) == 1 and len(alert_keys_in_component) > 1:
            basis.append("namespace")

        # Check node affinity
        node_keys = {a.resource_key for a in alert_keys_in_component if a.resource_key.startswith("node/")}
        if node_keys:
            basis.append("node_affinity")

        # Check control plane fan-out
        operator_alerts = [a for a in alert_keys_in_component if a.resource_key.startswith("operator/")]
        if operator_alerts:
            basis.append("control_plane_fan_out")

        if not basis:
            basis = ["temporal"]

        root_candidates = _pick_root_candidate(alert_keys_in_component, adj)

        cluster_idx += 1
        clusters.append(IssueCluster(
            cluster_id=f"ic-{cluster_idx:03d}",
            alerts=alert_keys_in_component,
            root_candidates=root_candidates,
            confidence=root_candidates[0].confidence if root_candidates else 0.5,
            correlation_basis=basis,
            affected_resources=[a.resource_key for a in alert_keys_in_component],
        ))

    logger.info("Alert correlation complete", extra={
        "action": "correlation_complete",
        "total_alerts": len(alerts),
        "cluster_count": len(clusters),
    })

    return {"issue_clusters": [c.model_dump(mode="json") for c in clusters]}

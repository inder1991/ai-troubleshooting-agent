"""Diagnostic evidence graph builder."""

from __future__ import annotations

from typing import TYPE_CHECKING
import uuid
from collections import defaultdict
from src.agents.cluster.state import DiagnosticNode, DiagnosticEdge, DiagnosticGraph, NormalizedSignal
from src.agents.cluster.graph_utils import bfs_reachable, graph_has_path
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig


logger = get_logger(__name__)

PATTERN_ROOT_SIGNALS = {
    "CRASHLOOP_OOM": "OOM_KILLED",
    "NODE_DISK_FULL": "NODE_DISK_PRESSURE",
    "STUCK_ROLLOUT": "ROLLOUT_STUCK",
    "NODE_PRESSURE_EVICTION": "NODE_DISK_PRESSURE",
    "NODE_MEMORY_EVICTION": "NODE_MEMORY_PRESSURE",
    "NETPOL_BLOCKING_CONFIRMED": "NETPOL_EMPTY_INGRESS",
}


def build_diagnostic_graph(
    signals: list[dict],
    topology: dict,
    pattern_matches: list[dict],
    temporal_data: dict,
) -> DiagnosticGraph:
    """Build cross-domain evidence graph from signals, topology, patterns."""
    nodes: dict[str, DiagnosticNode] = {}
    edges: list[DiagnosticEdge] = []

    resource_temporals = temporal_data.get("resource_temporals", {})
    topo_nodes = topology.get("nodes", {})
    topo_edges = topology.get("edges", [])

    # 1. Create nodes from normalized signals
    for sig_dict in signals:
        sig = NormalizedSignal(**sig_dict) if isinstance(sig_dict, dict) else sig_dict
        node_id = f"sig/{sig.signal_type}/{sig.resource_key}"
        rt = resource_temporals.get(sig.resource_key, {})

        nodes[node_id] = DiagnosticNode(
            node_id=node_id,
            node_type="signal",
            resource_key=sig.resource_key,
            signal_type=sig.signal_type,
            severity="high" if sig.reliability >= 0.8 else "medium",
            reliability=sig.reliability,
            first_seen=rt.get("first_seen", sig.timestamp),
            last_seen=rt.get("last_seen", sig.timestamp),
            event_age_seconds=rt.get("resource_age_seconds", 0),
            restart_velocity=rt.get("restart_velocity", 0.0),
            resource_age_seconds=rt.get("resource_age_seconds", 0),
            event_count_recent=rt.get("event_count_recent", 0),
            event_count_baseline=rt.get("event_count_baseline", 0),
            namespace=sig.namespace,
        )

    # 2. Create edges based on deterministic rules

    # Build resource_key -> node_ids index
    resource_nodes: dict[str, list[str]] = defaultdict(list)
    for nid, node in nodes.items():
        resource_nodes[node.resource_key].append(nid)

    # Build topology adjacency
    topo_adj: dict[str, set[str]] = defaultdict(set)
    for edge in topo_edges:
        fk = edge.get("from_key", "")
        tk = edge.get("to_key", "")
        if fk and tk:
            topo_adj[fk].add(tk)
            topo_adj[tk].add(fk)

    # Rule 1: Node pressure + pod eviction on same node -> CAUSES
    pressure_signals = {nid: n for nid, n in nodes.items()
                       if n.signal_type in ("NODE_DISK_PRESSURE", "NODE_MEMORY_PRESSURE", "NODE_PID_PRESSURE")}
    eviction_signals = {nid: n for nid, n in nodes.items()
                       if n.signal_type == "POD_EVICTION"}

    for p_id, p_node in pressure_signals.items():
        for e_id, e_node in eviction_signals.items():
            # Check if eviction is on a resource hosted by the pressured node
            p_resource = p_node.resource_key  # e.g., "node/node-1"
            e_resource = e_node.resource_key  # e.g., "pod/production/app-xyz"
            # Check topology: node hosts pod
            if e_resource in topo_adj.get(p_resource, set()) or p_resource in topo_adj.get(e_resource, set()):
                edges.append(DiagnosticEdge(
                    from_id=p_id, to_id=e_id, edge_type="CAUSES",
                    confidence=0.9, evidence=f"Node pressure on {p_resource} caused eviction of {e_resource}"
                ))

    # Rule 2: Deployment owns degraded pods -> AFFECTS
    deployment_signals = {nid: n for nid, n in nodes.items()
                         if n.signal_type in ("DEPLOYMENT_DEGRADED", "ROLLOUT_STUCK")}
    pod_signals = {nid: n for nid, n in nodes.items()
                  if n.signal_type in ("CRASHLOOP", "OOM_KILLED", "POD_PENDING", "IMAGE_PULL_BACKOFF")}

    for d_id, d_node in deployment_signals.items():
        for p_id, p_node in pod_signals.items():
            # Same namespace and topology dependency
            if d_node.namespace == p_node.namespace:
                d_res = d_node.resource_key
                p_res = p_node.resource_key
                if p_res in topo_adj.get(d_res, set()) or d_res in topo_adj.get(p_res, set()):
                    edges.append(DiagnosticEdge(
                        from_id=p_id, to_id=d_id, edge_type="AFFECTS",
                        confidence=0.8, evidence=f"Pod issue {p_node.signal_type} affects {d_res}"
                    ))

    # Rule 3: Service depends on degraded deployment -> DEPENDS_ON
    service_signals = {nid: n for nid, n in nodes.items()
                      if n.signal_type in ("SERVICE_ZERO_ENDPOINTS", "LB_PENDING")}

    for s_id, s_node in service_signals.items():
        for d_id, d_node in deployment_signals.items():
            if s_node.namespace == d_node.namespace:
                edges.append(DiagnosticEdge(
                    from_id=s_id, to_id=d_id, edge_type="DEPENDS_ON",
                    confidence=0.7, evidence=f"Service {s_node.resource_key} depends on {d_node.resource_key}"
                ))

    # Rule 4: Two signals on same resource -> OBSERVED_AFTER (temporal)
    for res_key, node_ids in resource_nodes.items():
        if len(node_ids) > 1:
            for i in range(len(node_ids)):
                for j in range(i + 1, len(node_ids)):
                    edges.append(DiagnosticEdge(
                        from_id=node_ids[i], to_id=node_ids[j], edge_type="OBSERVED_AFTER",
                        confidence=0.5, evidence=f"Both observed on {res_key}"
                    ))

    # Rule 5: Pattern match links signals -> SYMPTOM_OF
    for pm_dict in pattern_matches:
        pm_conditions = pm_dict.get("matched_conditions", [])
        pm_resources = pm_dict.get("affected_resources", [])
        pattern_id = pm_dict.get("pattern_id", "")
        if len(pm_conditions) > 1:
            root_type = PATTERN_ROOT_SIGNALS.get(pattern_id, pm_conditions[0])
            for symptom_type in pm_conditions:
                if symptom_type == root_type:
                    continue
                root_nodes = [nid for nid, n in nodes.items() if n.signal_type == root_type]
                symptom_nodes = [nid for nid, n in nodes.items() if n.signal_type == symptom_type]
                for r in root_nodes:
                    for s in symptom_nodes:
                        edges.append(DiagnosticEdge(
                            from_id=r, to_id=s, edge_type="SYMPTOM_OF",
                            confidence=0.7, evidence=f"Pattern links {root_type} -> {symptom_type}"
                        ))

    valid_edges = [e for e in edges if e.from_id in nodes and e.to_id in nodes]
    if len(valid_edges) < len(edges):
        logger.warning("Removed %d dangling edges", len(edges) - len(valid_edges))
    edges = valid_edges

    graph = DiagnosticGraph(nodes=nodes, edges=edges)
    logger.info("Built diagnostic graph: %d nodes, %d edges", len(nodes), len(edges))
    return graph


@traced_node(timeout_seconds=5)
async def diagnostic_graph_builder(state: dict, config: RunnableConfig) -> dict:
    """Build cross-domain diagnostic evidence graph. Deterministic, zero LLM cost."""
    signals = state.get("normalized_signals", [])
    topology = state.get("scoped_topology_graph") or state.get("topology_graph", {})
    pattern_matches = state.get("pattern_matches", [])
    temporal_data = state.get("temporal_analysis", {})

    graph = build_diagnostic_graph(signals, topology, pattern_matches, temporal_data)

    return {"diagnostic_graph": graph.model_dump(mode="json")}

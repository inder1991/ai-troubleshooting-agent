"""Topology Snapshot Resolver — LangGraph node that reads or builds cached topology."""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from src.agents.cluster.state import DiagnosticScope, TopologySnapshot
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Module-level cache: session_id -> (TopologySnapshot, timestamp)
_topology_cache: dict[str, tuple[TopologySnapshot, float]] = {}
TOPOLOGY_TTL_SECONDS = 300  # 5 minutes


def clear_topology_cache(session_id: str) -> None:
    """Clear cached topology for a session. Called on session cleanup."""
    _topology_cache.pop(session_id, None)


# ---------------------------------------------------------------------------
# Scope-aware topology pruning
# ---------------------------------------------------------------------------

# Infrastructure / cluster-scoped resource kinds that should be retained
# when pruning to namespace scope (they represent cross-namespace dependencies).
_INFRA_PARENT_KINDS = frozenset({
    "Node", "StorageClass", "ClusterOperator", "PersistentVolume", "MachineSet",
})

# Resource kinds relevant to each diagnostic domain.
_DOMAIN_RESOURCE_KINDS: dict[str, frozenset[str]] = {
    "ctrl_plane": frozenset({"ClusterOperator", "MachineSet", "Node", "APIServer", "ETCD"}),
    "node":       frozenset({"Node", "Pod", "DaemonSet", "MachineSet"}),
    "network":    frozenset({"Service", "Ingress", "Route", "NetworkPolicy", "Pod"}),
    "storage":    frozenset({"PersistentVolumeClaim", "PersistentVolume", "StorageClass", "Pod"}),
}

# BFS traversal rules ---------------------------------------------------------
# Never traverse outward from these resource kinds.
_STOP_TRAVERSE_FROM = frozenset({"StorageClass"})
# From a Node, only traverse to Pod (prevents exploding to entire cluster).
_NODE_ONLY_TO = frozenset({"Pod"})


def _find_workload_root(nodes: dict, workload_key: str) -> Optional[str]:
    """Locate the topology node matching a 'Kind/name' workload key."""
    kind, _, name = workload_key.partition("/")
    for nid, n in nodes.items():
        if n.get("kind", "").lower() == kind.lower() and n.get("name") == name:
            return nid
    return None


def _bfs_subgraph(root: Optional[str], nodes: dict, edges: list) -> set[str]:
    """Relation-type-aware BFS from *root*; returns set of reachable node ids.

    If *root* is None (workload not found), falls back to keeping all nodes.
    """
    if not root:
        return set(nodes.keys())  # Fallback: keep all

    # Build undirected adjacency list
    adj: dict[str, list[str]] = {}
    for e in edges:
        src, tgt = e["from_key"], e["to_key"]
        adj.setdefault(src, []).append(tgt)
        adj.setdefault(tgt, []).append(src)

    visited: set[str] = {root}
    queue: deque[tuple[str, int]] = deque([(root, 0)])
    MAX_SAFETY_DEPTH = 5  # Safety net only, not the real limit

    while queue:
        nid, depth = queue.popleft()
        if depth >= MAX_SAFETY_DEPTH:
            continue
        src_kind = nodes.get(nid, {}).get("kind", "")

        # Rule: don't traverse from StorageClass upward
        if src_kind in _STOP_TRAVERSE_FROM:
            continue

        for neighbor in adj.get(nid, []):
            if neighbor in visited:
                continue
            neighbor_kind = nodes.get(neighbor, {}).get("kind", "")
            # Rule: from Node, only traverse to Pod
            if src_kind == "Node" and neighbor_kind not in _NODE_ONLY_TO:
                continue
            visited.add(neighbor)
            queue.append((neighbor, depth + 1))
    return visited


def _prune_topology(topology: dict, scope: DiagnosticScope) -> dict:
    """Return a pruned copy of *topology* based on the diagnostic *scope*.

    The full snapshot is never mutated — a new dict is returned.

    Level behaviour:
    - cluster:   no pruning
    - namespace:  keep resources in target namespaces + infra parents + cluster-scoped + edge neighbours
    - workload:   BFS subgraph from workload root (relation-type-aware)
    - component:  keep only resource kinds relevant to the requested domains
    """
    if scope.level == "cluster":
        return topology  # No pruning

    nodes = topology.get("nodes", {})
    edges = topology.get("edges", [])

    if scope.level == "namespace":
        ns_set = set(scope.namespaces)
        keep: set[str] = set()
        for nid, n in nodes.items():
            if n.get("namespace") in ns_set:
                keep.add(nid)
            elif n.get("kind") in _INFRA_PARENT_KINDS:
                keep.add(nid)  # Keep infra parents for cross-NS deps
            elif not n.get("namespace"):
                keep.add(nid)  # Keep cluster-scoped resources
        # Also keep any node that is a direct edge neighbor of a kept node
        edge_neighbors: set[str] = set()
        for e in edges:
            src, tgt = e["from_key"], e["to_key"]
            if src in keep and tgt not in keep:
                edge_neighbors.add(tgt)
            elif tgt in keep and src not in keep:
                edge_neighbors.add(src)
        keep |= edge_neighbors

    elif scope.level == "workload":
        root = _find_workload_root(nodes, scope.workload_key or "")
        keep = _bfs_subgraph(root, nodes, edges)

    elif scope.level == "component":
        # Component = domain subset: keep only domain-relevant resource kinds
        relevant_kinds: set[str] = set()
        for d in scope.domains:
            relevant_kinds |= _DOMAIN_RESOURCE_KINDS.get(d, set())
        keep = {nid for nid, n in nodes.items() if n.get("kind") in relevant_kinds}

    else:
        return topology

    pruned_edges = [e for e in edges if e["from_key"] in keep and e["to_key"] in keep]
    pruned_nodes = {nid: n for nid, n in nodes.items() if nid in keep}
    return {**topology, "nodes": pruned_nodes, "edges": pruned_edges}


@traced_node(timeout_seconds=30)
async def topology_snapshot_resolver(state: dict, config: dict) -> dict:
    """LangGraph node: resolve or build topology snapshot."""
    session_id = state.get("diagnostic_id", "")
    client = config.get("configurable", {}).get("cluster_client")

    if not client:
        logger.warning("No cluster_client in config, skipping topology")
        return {
            "topology_graph": TopologySnapshot(stale=True).model_dump(mode="json"),
            "scoped_topology_graph": TopologySnapshot(stale=True).model_dump(mode="json"),
            "topology_freshness": {"timestamp": "", "stale": True},
        }

    # Check cache (atomic get avoids TOCTOU race with clear_topology_cache)
    cached = _topology_cache.get(session_id)
    if cached is not None:
        snapshot, cached_at = cached
        if (time.monotonic() - cached_at) < TOPOLOGY_TTL_SECONDS:
            logger.info("Using cached topology", extra={"action": "cache_hit", "node_count": len(snapshot.nodes)})
            topology_dict = snapshot.model_dump(mode="json")
            scope = DiagnosticScope(**(state.get("diagnostic_scope") or {}))
            scoped = _prune_topology(topology_dict, scope)
            return {
                "topology_graph": topology_dict,
                "scoped_topology_graph": scoped,
                "topology_freshness": {"timestamp": snapshot.built_at, "stale": False},
            }

    # Build fresh
    snapshot = await client.build_topology_snapshot()
    _topology_cache[session_id] = (snapshot, time.monotonic())

    logger.info("Built fresh topology", extra={
        "action": "topology_built",
        "node_count": len(snapshot.nodes),
        "edge_count": len(snapshot.edges),
    })

    topology_dict = snapshot.model_dump(mode="json")
    scope = DiagnosticScope(**(state.get("diagnostic_scope") or {}))
    scoped = _prune_topology(topology_dict, scope)

    return {
        "topology_graph": topology_dict,
        "scoped_topology_graph": scoped,
        "topology_freshness": {"timestamp": snapshot.built_at, "stale": False},
    }

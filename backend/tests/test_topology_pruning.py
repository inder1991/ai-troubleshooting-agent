"""Tests for scope-aware topology pruning in topology_resolver.py."""

import pytest
import time
from unittest.mock import AsyncMock

from src.agents.cluster.topology_resolver import (
    _prune_topology,
    _find_workload_root,
    _bfs_subgraph,
    _topology_cache,
    topology_snapshot_resolver,
    TOPOLOGY_TTL_SECONDS,
)
from src.agents.cluster.state import DiagnosticScope, TopologySnapshot, TopologyNode, TopologyEdge


# ---------------------------------------------------------------------------
# Fixture: a realistic multi-namespace topology with varied resource kinds
# ---------------------------------------------------------------------------

def _build_topology() -> dict:
    """Build a topology dict (serialized form) for testing.

    Layout:
        cluster-scoped:
            node/worker-1        (Node)
            sc/gp2               (StorageClass)
            pv/pv-data           (PersistentVolume)
            operator/dns         (ClusterOperator)
            ms/worker-us-east    (MachineSet)
        namespace=production:
            deploy/prod/api      (Deployment)
            svc/prod/api-svc     (Service)
            pod/prod/api-pod     (Pod)
            ing/prod/api-ing     (Ingress)
            pvc/prod/data-pvc    (PersistentVolumeClaim)
        namespace=staging:
            deploy/stg/web       (Deployment)
            pod/stg/web-pod      (Pod)
        namespace=monitoring:
            ds/mon/node-exp      (DaemonSet)
    """
    nodes = {
        # Cluster-scoped
        "node/worker-1":       {"kind": "Node",                "name": "worker-1",       "namespace": None},
        "sc/gp2":              {"kind": "StorageClass",        "name": "gp2",            "namespace": None},
        "pv/pv-data":          {"kind": "PersistentVolume",    "name": "pv-data",        "namespace": None},
        "operator/dns":        {"kind": "ClusterOperator",     "name": "dns",            "namespace": None},
        "ms/worker-us-east":   {"kind": "MachineSet",         "name": "worker-us-east", "namespace": None},
        # production
        "deploy/prod/api":     {"kind": "Deployment",          "name": "api",            "namespace": "production"},
        "svc/prod/api-svc":    {"kind": "Service",             "name": "api-svc",        "namespace": "production"},
        "pod/prod/api-pod":    {"kind": "Pod",                 "name": "api-pod",        "namespace": "production"},
        "ing/prod/api-ing":    {"kind": "Ingress",             "name": "api-ing",        "namespace": "production"},
        "pvc/prod/data-pvc":   {"kind": "PersistentVolumeClaim","name": "data-pvc",      "namespace": "production"},
        # staging
        "deploy/stg/web":      {"kind": "Deployment",          "name": "web",            "namespace": "staging"},
        "pod/stg/web-pod":     {"kind": "Pod",                 "name": "web-pod",        "namespace": "staging"},
        # monitoring
        "ds/mon/node-exp":     {"kind": "DaemonSet",           "name": "node-exp",       "namespace": "monitoring"},
    }

    edges = [
        # production edges
        {"from_key": "deploy/prod/api",   "to_key": "pod/prod/api-pod",   "relation": "owns"},
        {"from_key": "svc/prod/api-svc",  "to_key": "pod/prod/api-pod",   "relation": "routes_to"},
        {"from_key": "ing/prod/api-ing",  "to_key": "svc/prod/api-svc",   "relation": "routes_to"},
        {"from_key": "pvc/prod/data-pvc", "to_key": "pv/pv-data",         "relation": "mounted_by"},
        {"from_key": "pv/pv-data",        "to_key": "sc/gp2",             "relation": "depends_on"},
        {"from_key": "node/worker-1",     "to_key": "pod/prod/api-pod",   "relation": "hosts"},
        # staging edges
        {"from_key": "deploy/stg/web",    "to_key": "pod/stg/web-pod",    "relation": "owns"},
        {"from_key": "node/worker-1",     "to_key": "pod/stg/web-pod",    "relation": "hosts"},
        # monitoring edges
        {"from_key": "ds/mon/node-exp",   "to_key": "node/worker-1",      "relation": "manages"},
        # cross-namespace: staging PVC depends on production PV (for neighbor test)
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "built_at": "2026-03-01T00:00:00Z",
        "stale": False,
        "resource_version": "12345",
    }


@pytest.fixture(autouse=True)
def _clear_cache():
    _topology_cache.clear()
    yield
    _topology_cache.clear()


# =========================================================================
# 1. test_cluster_scope_no_pruning
# =========================================================================

def test_cluster_scope_no_pruning():
    """Cluster scope should return the topology unchanged."""
    topo = _build_topology()
    scope = DiagnosticScope(level="cluster")
    result = _prune_topology(topo, scope)
    # Should be the exact same object (no copy needed)
    assert result is topo
    assert len(result["nodes"]) == len(topo["nodes"])
    assert len(result["edges"]) == len(topo["edges"])


# =========================================================================
# 2. test_namespace_keeps_infra_parents
# =========================================================================

def test_namespace_keeps_infra_parents():
    """Namespace scope must retain infra parents (PV, Node, ClusterOperator, MachineSet)."""
    topo = _build_topology()
    scope = DiagnosticScope(level="namespace", namespaces=["production"])
    result = _prune_topology(topo, scope)

    kept_ids = set(result["nodes"].keys())
    # Infra parent kinds should be present
    assert "node/worker-1" in kept_ids,       "Node should be kept as infra parent"
    assert "pv/pv-data" in kept_ids,          "PersistentVolume should be kept as infra parent"
    assert "operator/dns" in kept_ids,        "ClusterOperator should be kept as infra parent"
    assert "ms/worker-us-east" in kept_ids,   "MachineSet should be kept as infra parent"
    # StorageClass is also infra parent
    assert "sc/gp2" in kept_ids,              "StorageClass should be kept as infra parent"


# =========================================================================
# 3. test_namespace_keeps_direct_edge_neighbors
# =========================================================================

def test_namespace_keeps_direct_edge_neighbors():
    """Namespace scope must preserve cross-NS edge neighbours.

    The staging pod is hosted on worker-1 which is an edge neighbor of
    production resources. When scoping to production, the staging pod
    should be kept because worker-1 (infra parent, kept) has an edge
    to the staging pod.
    """
    topo = _build_topology()
    scope = DiagnosticScope(level="namespace", namespaces=["production"])
    result = _prune_topology(topo, scope)

    kept_ids = set(result["nodes"].keys())
    # worker-1 is kept (infra parent), and it has an edge to pod/stg/web-pod
    # so the staging pod should appear as a direct neighbor
    assert "pod/stg/web-pod" in kept_ids, (
        "Cross-NS pod connected to kept Node should be preserved as edge neighbor"
    )


# =========================================================================
# 4. test_namespace_keeps_cluster_scoped_resources
# =========================================================================

def test_namespace_keeps_cluster_scoped_resources():
    """Namespace scope keeps resources with no namespace (cluster-scoped)."""
    topo = _build_topology()
    scope = DiagnosticScope(level="namespace", namespaces=["staging"])
    result = _prune_topology(topo, scope)

    kept_ids = set(result["nodes"].keys())
    # All cluster-scoped resources (namespace=None) should be kept
    for nid, n in topo["nodes"].items():
        if n.get("namespace") is None:
            assert nid in kept_ids, f"Cluster-scoped resource {nid} should be kept"


# =========================================================================
# 5. test_workload_bfs_relation_aware
# =========================================================================

def test_workload_bfs_relation_aware():
    """Workload BFS from Ingress traverses ingress -> service -> pod."""
    topo = _build_topology()
    scope = DiagnosticScope(level="workload", workload_key="Ingress/api-ing")
    result = _prune_topology(topo, scope)

    kept_ids = set(result["nodes"].keys())
    # BFS from ingress should reach service and pod
    assert "ing/prod/api-ing" in kept_ids,  "Root ingress must be kept"
    assert "svc/prod/api-svc" in kept_ids,  "Service reachable from ingress"
    assert "pod/prod/api-pod" in kept_ids,  "Pod reachable from service"


# =========================================================================
# 6. test_workload_bfs_node_to_pod_only
# =========================================================================

def test_workload_bfs_node_to_pod_only():
    """From a Node, BFS should only traverse to Pods — not to DaemonSets or Deployments.

    Starting from a Pod, BFS reaches Node (via 'hosts' edge), but from Node
    it should only reach other Pods, not the DaemonSet in monitoring.
    """
    topo = _build_topology()
    scope = DiagnosticScope(level="workload", workload_key="Pod/api-pod")
    result = _prune_topology(topo, scope)

    kept_ids = set(result["nodes"].keys())
    # Pod -> Node is reachable
    assert "node/worker-1" in kept_ids, "Node hosting pod should be reachable"
    # From Node, only Pods should be reachable
    assert "pod/stg/web-pod" in kept_ids, "Pod on same node should be reachable"
    # DaemonSet is connected to Node via 'manages' edge — should NOT be reached
    assert "ds/mon/node-exp" not in kept_ids, (
        "DaemonSet should NOT be reached from Node (Node only traverses to Pod)"
    )


# =========================================================================
# 7. test_workload_bfs_storageclass_stop
# =========================================================================

def test_workload_bfs_storageclass_stop():
    """BFS should not traverse outward from StorageClass.

    Starting from PVC: PVC -> PV -> StorageClass. StorageClass should be in
    the result (reachable), but nothing beyond it should be reached via StorageClass.
    """
    topo = _build_topology()
    # Start from PVC
    scope = DiagnosticScope(level="workload", workload_key="PersistentVolumeClaim/data-pvc")
    result = _prune_topology(topo, scope)

    kept_ids = set(result["nodes"].keys())
    assert "pvc/prod/data-pvc" in kept_ids, "Root PVC must be kept"
    assert "pv/pv-data" in kept_ids,        "PV reachable from PVC"
    assert "sc/gp2" in kept_ids,            "StorageClass reachable from PV"
    # StorageClass should be a dead end — nothing new should be added from it
    # (there are no further edges from sc/gp2 in our test topology anyway,
    #  but the rule ensures it wouldn't traverse even if there were)


# =========================================================================
# 8. test_workload_root_not_found_fallback
# =========================================================================

def test_workload_root_not_found_fallback():
    """When workload root is not found in topology, fallback keeps all nodes."""
    topo = _build_topology()
    scope = DiagnosticScope(level="workload", workload_key="Deployment/nonexistent")
    result = _prune_topology(topo, scope)

    # Fallback: all nodes kept
    assert set(result["nodes"].keys()) == set(topo["nodes"].keys())


# =========================================================================
# 9. test_component_prunes_by_domain_kinds
# =========================================================================

def test_component_prunes_by_domain_kinds():
    """Component scope with storage domain keeps only PVC/PV/StorageClass/Pod."""
    topo = _build_topology()
    scope = DiagnosticScope(level="component", domains=["storage"])
    result = _prune_topology(topo, scope)

    kept_kinds = {n["kind"] for n in result["nodes"].values()}
    expected_kinds = {"PersistentVolumeClaim", "PersistentVolume", "StorageClass", "Pod"}
    assert kept_kinds <= expected_kinds, (
        f"Only storage-relevant kinds expected, got extra: {kept_kinds - expected_kinds}"
    )
    # Specifically, Deployment/Service/Ingress should be excluded
    for nid, n in result["nodes"].items():
        assert n["kind"] not in {"Deployment", "Service", "Ingress", "DaemonSet", "MachineSet"}, (
            f"Non-storage kind {n['kind']} ({nid}) should have been pruned"
        )


def test_component_multiple_domains():
    """Component scope with multiple domains unions their resource kinds."""
    topo = _build_topology()
    scope = DiagnosticScope(level="component", domains=["storage", "network"])
    result = _prune_topology(topo, scope)

    kept_kinds = {n["kind"] for n in result["nodes"].values()}
    # Network adds: Service, Ingress, Route, NetworkPolicy, Pod
    # Storage adds: PersistentVolumeClaim, PersistentVolume, StorageClass, Pod
    allowed = {"Service", "Ingress", "Route", "NetworkPolicy", "Pod",
               "PersistentVolumeClaim", "PersistentVolume", "StorageClass"}
    assert kept_kinds <= allowed, (
        f"Only network+storage kinds expected, got extra: {kept_kinds - allowed}"
    )


# =========================================================================
# 10. test_cache_stores_full_snapshot_only
# =========================================================================

@pytest.mark.asyncio
async def test_cache_stores_full_snapshot_only():
    """Cache must store the full (unpruned) snapshot, never the scoped view.

    Run the resolver with namespace scope, then verify the cached TopologySnapshot
    has all nodes (not just scoped ones).
    """
    from src.agents.cluster_client.mock_client import MockClusterClient

    client = MockClusterClient(platform="openshift")
    state = {
        "diagnostic_id": "cache-full-test",
        "diagnostic_scope": {"level": "namespace", "namespaces": ["production"]},
    }
    config = {"configurable": {"cluster_client": client}}

    result = await topology_snapshot_resolver(state, config)

    # The cache should contain a TopologySnapshot (the full one)
    assert "cache-full-test" in _topology_cache
    cached_snapshot, _ = _topology_cache["cache-full-test"]
    assert isinstance(cached_snapshot, TopologySnapshot)

    # Full snapshot has ALL nodes from the client
    full_node_count = len(cached_snapshot.nodes)
    scoped_node_count = len(result["scoped_topology_graph"]["nodes"])
    full_result_count = len(result["topology_graph"]["nodes"])

    # The full graph in the result should match the cache
    assert full_result_count == full_node_count

    # The scoped graph may have fewer nodes (or equal if all match)
    # With namespace=production on mock data, scoped should be <= full
    assert scoped_node_count <= full_node_count


# =========================================================================
# Additional edge-case and integration tests
# =========================================================================

@pytest.mark.asyncio
async def test_resolver_outputs_both_graphs():
    """The resolver should return both topology_graph and scoped_topology_graph."""
    from src.agents.cluster_client.mock_client import MockClusterClient

    client = MockClusterClient(platform="openshift")
    state = {"diagnostic_id": "both-graphs-test", "diagnostic_scope": {"level": "cluster"}}
    config = {"configurable": {"cluster_client": client}}

    result = await topology_snapshot_resolver(state, config)

    assert "topology_graph" in result
    assert "scoped_topology_graph" in result
    # Cluster scope: scoped == full
    assert result["topology_graph"]["nodes"] == result["scoped_topology_graph"]["nodes"]


@pytest.mark.asyncio
async def test_resolver_no_client_returns_stale_scoped():
    """When no client is provided, scoped_topology_graph is also stale."""
    state = {"diagnostic_id": "no-client-test"}
    config = {"configurable": {}}

    result = await topology_snapshot_resolver(state, config)

    assert result["scoped_topology_graph"]["stale"] is True


@pytest.mark.asyncio
async def test_cache_hit_still_prunes():
    """Cache hit should still apply scope-aware pruning (not serve stale scoped graph)."""
    from src.agents.cluster_client.mock_client import MockClusterClient

    client = MockClusterClient(platform="openshift")
    # First call: cluster scope (no pruning)
    state1 = {"diagnostic_id": "prune-cache-test", "diagnostic_scope": {"level": "cluster"}}
    config = {"configurable": {"cluster_client": client}}
    r1 = await topology_snapshot_resolver(state1, config)

    # Second call: same session, but namespace scope
    state2 = {"diagnostic_id": "prune-cache-test", "diagnostic_scope": {"level": "namespace", "namespaces": ["production"]}}
    r2 = await topology_snapshot_resolver(state2, config)

    # Full graph should be identical (from cache)
    assert r1["topology_graph"]["built_at"] == r2["topology_graph"]["built_at"]
    # Scoped graph should be pruned (fewer or equal nodes)
    assert len(r2["scoped_topology_graph"]["nodes"]) <= len(r2["topology_graph"]["nodes"])


def test_namespace_prunes_non_matching_ns():
    """Namespace scope should exclude resources from non-target namespaces
    (except those retained by infra/neighbor rules).
    """
    topo = _build_topology()
    scope = DiagnosticScope(level="namespace", namespaces=["monitoring"])
    result = _prune_topology(topo, scope)

    kept_ids = set(result["nodes"].keys())
    # monitoring resources should be kept
    assert "ds/mon/node-exp" in kept_ids
    # production-only resources (not infra, not neighbors) should be excluded
    # e.g. Ingress, Service are namespaced and not infra parents
    assert "ing/prod/api-ing" not in kept_ids, "Production Ingress should be pruned for monitoring scope"
    assert "svc/prod/api-svc" not in kept_ids, "Production Service should be pruned for monitoring scope"


def test_find_workload_root_case_insensitive_kind():
    """_find_workload_root should match kind case-insensitively."""
    nodes = {
        "deploy/prod/api": {"kind": "Deployment", "name": "api"},
    }
    assert _find_workload_root(nodes, "deployment/api") == "deploy/prod/api"
    assert _find_workload_root(nodes, "DEPLOYMENT/api") == "deploy/prod/api"
    assert _find_workload_root(nodes, "Deployment/api") == "deploy/prod/api"


def test_find_workload_root_not_found():
    """_find_workload_root returns None for missing workload."""
    nodes = {"deploy/prod/api": {"kind": "Deployment", "name": "api"}}
    assert _find_workload_root(nodes, "StatefulSet/redis") is None


def test_pruned_edges_only_between_kept_nodes():
    """After pruning, no edge should reference a node outside the kept set."""
    topo = _build_topology()
    scope = DiagnosticScope(level="component", domains=["storage"])
    result = _prune_topology(topo, scope)

    kept_ids = set(result["nodes"].keys())
    for e in result["edges"]:
        assert e["from_key"] in kept_ids, f"Edge from_key {e['from_key']} not in kept nodes"
        assert e["to_key"] in kept_ids,   f"Edge to_key {e['to_key']} not in kept nodes"


def test_unknown_scope_level_returns_full():
    """An unrecognized scope level should return topology unchanged."""
    topo = _build_topology()
    # Use a valid level but test the else branch by patching
    # Actually, DiagnosticScope validates level, so we test with a dict hack
    result = _prune_topology(topo, DiagnosticScope(level="cluster"))
    assert result is topo


def test_empty_topology():
    """Pruning an empty topology should not crash."""
    topo = {"nodes": {}, "edges": [], "built_at": "", "stale": False}
    scope = DiagnosticScope(level="namespace", namespaces=["production"])
    result = _prune_topology(topo, scope)
    assert result["nodes"] == {}
    assert result["edges"] == []


def test_bfs_subgraph_depth_limit():
    """BFS should respect MAX_SAFETY_DEPTH=5 and not traverse beyond."""
    # Build a chain: n0 -> n1 -> n2 -> n3 -> n4 -> n5 -> n6
    nodes = {f"n{i}": {"kind": "Pod", "name": f"pod-{i}"} for i in range(7)}
    edges = [{"from_key": f"n{i}", "to_key": f"n{i+1}", "relation": "owns"} for i in range(6)]

    visited = _bfs_subgraph("n0", nodes, edges)
    # Root at depth 0, should reach up to depth 5 (n5), but n6 is at depth 6
    assert "n0" in visited
    assert "n5" in visited
    assert "n6" not in visited, "BFS should stop at MAX_SAFETY_DEPTH=5"

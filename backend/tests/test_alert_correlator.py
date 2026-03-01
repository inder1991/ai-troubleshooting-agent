import pytest
from src.agents.cluster.alert_correlator import (
    alert_correlator, _extract_alerts, _build_adjacency,
    _find_connected_component, _pick_root_candidate,
)
from src.agents.cluster.state import ClusterAlert


def _topo_with_alerts():
    """Topology with 6 alerts: should cluster into 2 groups."""
    return {
        "nodes": {
            "node/worker-1": {"kind": "node", "name": "worker-1", "status": "NotReady"},
            "pod/payments/auth-5b6q": {"kind": "pod", "name": "auth-5b6q", "namespace": "payments", "status": "CrashLoopBackOff", "node_name": "worker-1"},
            "pod/payments/api-7x2": {"kind": "pod", "name": "api-7x2", "namespace": "payments", "status": "Evicted", "node_name": "worker-1"},
            "operator/dns": {"kind": "operator", "name": "dns", "status": "Degraded"},
            "pod/kube-system/coredns-abc": {"kind": "pod", "name": "coredns-abc", "namespace": "kube-system", "status": "CrashLoopBackOff"},
            "pod/monitoring/prom-0": {"kind": "pod", "name": "prom-0", "namespace": "monitoring", "status": "Running"},
        },
        "edges": [
            {"from_key": "node/worker-1", "to_key": "pod/payments/auth-5b6q", "relation": "hosts"},
            {"from_key": "node/worker-1", "to_key": "pod/payments/api-7x2", "relation": "hosts"},
            {"from_key": "operator/dns", "to_key": "pod/kube-system/coredns-abc", "relation": "manages"},
        ],
    }


@pytest.mark.asyncio
async def test_six_alerts_become_two_clusters():
    state = {"topology_graph": _topo_with_alerts(), "diagnostic_id": "test"}
    result = await alert_correlator(state, {})
    clusters = result["issue_clusters"]
    assert len(clusters) == 2  # node cluster + operator cluster


@pytest.mark.asyncio
async def test_no_alerts_returns_empty():
    state = {
        "topology_graph": {
            "nodes": {"pod/ns/p1": {"kind": "pod", "name": "p1", "status": "Running"}},
            "edges": [],
        },
        "diagnostic_id": "test",
    }
    result = await alert_correlator(state, {})
    assert result["issue_clusters"] == []


@pytest.mark.asyncio
async def test_root_candidate_prefers_nodes():
    state = {"topology_graph": _topo_with_alerts(), "diagnostic_id": "test"}
    result = await alert_correlator(state, {})
    # Find the cluster with node/worker-1
    node_cluster = [c for c in result["issue_clusters"] if "node/worker-1" in c["affected_resources"]]
    assert len(node_cluster) == 1
    # Node should be top root candidate
    assert node_cluster[0]["root_candidates"][0]["resource_key"] == "node/worker-1"


@pytest.mark.asyncio
async def test_cluster_has_correlation_basis():
    state = {"topology_graph": _topo_with_alerts(), "diagnostic_id": "test"}
    result = await alert_correlator(state, {})
    for cluster in result["issue_clusters"]:
        assert len(cluster["correlation_basis"]) > 0


@pytest.mark.asyncio
async def test_no_topology_still_works():
    state = {"topology_graph": {}, "diagnostic_id": "test"}
    result = await alert_correlator(state, {})
    assert result["issue_clusters"] == []


@pytest.mark.asyncio
async def test_operator_cluster_has_control_plane_basis():
    state = {"topology_graph": _topo_with_alerts(), "diagnostic_id": "test"}
    result = await alert_correlator(state, {})
    op_cluster = [c for c in result["issue_clusters"] if any("operator/" in r for r in c["affected_resources"])]
    assert len(op_cluster) == 1
    assert "control_plane_fan_out" in op_cluster[0]["correlation_basis"]


def test_extract_alerts_filters_healthy():
    topo = {
        "nodes": {
            "pod/ns/healthy": {"kind": "pod", "name": "healthy", "status": "Running"},
            "pod/ns/sick": {"kind": "pod", "name": "sick", "status": "CrashLoopBackOff"},
        },
    }
    alerts = _extract_alerts({"topology_graph": topo})
    assert len(alerts) == 1
    assert alerts[0].resource_key == "pod/ns/sick"


def test_build_adjacency_bidirectional():
    edges = [{"from_key": "a", "to_key": "b", "relation": "hosts"}]
    adj = _build_adjacency(edges)
    assert "b" in adj["a"]
    assert "a" in adj["b"]

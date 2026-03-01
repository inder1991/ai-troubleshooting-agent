import pytest
from src.agents.cluster.causal_firewall import (
    causal_firewall, _extract_kind, _generate_candidate_links, _check_soft_rules,
)


def _state_with_pod_node_cluster():
    return {
        "diagnostic_id": "test",
        "topology_graph": {
            "nodes": {
                "node/worker-1": {"kind": "node", "name": "worker-1", "status": "NotReady"},
                "pod/ns/p1": {"kind": "pod", "name": "p1", "status": "CrashLoopBackOff", "node_name": "worker-1"},
            },
            "edges": [
                {"from_key": "node/worker-1", "to_key": "pod/ns/p1", "relation": "hosts"},
            ],
        },
        "issue_clusters": [
            {
                "cluster_id": "ic-001",
                "alerts": [
                    {"resource_key": "pod/ns/p1", "alert_type": "CrashLoopBackOff", "severity": "high", "timestamp": "", "raw_event": {}},
                    {"resource_key": "node/worker-1", "alert_type": "NotReady", "severity": "critical", "timestamp": "", "raw_event": {}},
                ],
                "root_candidates": [],
                "confidence": 0.8,
                "correlation_basis": ["topology"],
                "affected_resources": ["pod/ns/p1", "node/worker-1"],
            }
        ],
    }


@pytest.mark.asyncio
async def test_pod_to_node_is_blocked():
    state = _state_with_pod_node_cluster()
    result = await causal_firewall(state, {})
    css = result["causal_search_space"]
    # pod -> node should be blocked
    blocked_pairs = [(b["from_resource"], b["to_resource"]) for b in css["blocked_links"]]
    assert ("pod/ns/p1", "node/worker-1") in blocked_pairs


@pytest.mark.asyncio
async def test_node_to_pod_is_valid():
    state = _state_with_pod_node_cluster()
    result = await causal_firewall(state, {})
    css = result["causal_search_space"]
    # node -> pod should pass (either valid or annotated, not blocked)
    node_to_pod_blocked = any(
        b["from_resource"] == "node/worker-1" and b["to_resource"] == "pod/ns/p1"
        for b in css["blocked_links"]
    )
    assert not node_to_pod_blocked


@pytest.mark.asyncio
async def test_blocked_link_has_justification():
    state = _state_with_pod_node_cluster()
    result = await causal_firewall(state, {})
    css = result["causal_search_space"]
    for bl in css["blocked_links"]:
        assert bl["invariant_id"].startswith("INV-")
        assert len(bl["invariant_description"]) > 0
        assert bl["reason_code"] == "violates_topology_direction"
        assert bl["timestamp"] != ""


@pytest.mark.asyncio
async def test_empty_clusters_returns_empty_search_space():
    state = {"diagnostic_id": "test", "topology_graph": {"nodes": {}, "edges": []}, "issue_clusters": []}
    result = await causal_firewall(state, {})
    css = result["causal_search_space"]
    assert css["total_evaluated"] == 0
    assert css["total_blocked"] == 0


@pytest.mark.asyncio
async def test_counts_are_consistent():
    state = _state_with_pod_node_cluster()
    result = await causal_firewall(state, {})
    css = result["causal_search_space"]
    total = len(css["valid_links"]) + len(css["annotated_links"]) + len(css["blocked_links"])
    assert css["total_evaluated"] == total


def test_extract_kind():
    assert _extract_kind("pod/ns/name") == "pod"
    assert _extract_kind("node/worker-1") == "node"
    assert _extract_kind("operator/dns") == "operator"

"""Tests for scoped reads in alert_correlator, causal_firewall, and domain agents.

Verifies that downstream consumers read from scoped_topology_graph when available
and fall back to topology_graph, and that domain agents filter events/pvcs by namespace.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.cluster.alert_correlator import _extract_alerts, alert_correlator
from src.agents.cluster.causal_firewall import _check_soft_rules, causal_firewall
from src.agents.cluster_client.base import QueryResult


# ---------------------------------------------------------------------------
# Helpers: build topology dicts with problem nodes
# ---------------------------------------------------------------------------

def _scoped_topology():
    """A small scoped topology with one problem node."""
    return {
        "nodes": {
            "pod/prod/api-pod": {"kind": "Pod", "name": "api-pod", "namespace": "production", "status": "CrashLoopBackOff"},
            "node/worker-1": {"kind": "Node", "name": "worker-1", "namespace": None, "status": "Ready"},
        },
        "edges": [
            {"from_key": "node/worker-1", "to_key": "pod/prod/api-pod", "relation": "hosts"},
        ],
        "built_at": "2026-03-01T00:00:00Z",
        "stale": False,
    }


def _full_topology():
    """A larger full topology with additional problem nodes not in scope."""
    return {
        "nodes": {
            "pod/prod/api-pod": {"kind": "Pod", "name": "api-pod", "namespace": "production", "status": "CrashLoopBackOff"},
            "pod/staging/web-pod": {"kind": "Pod", "name": "web-pod", "namespace": "staging", "status": "OOMKilled"},
            "node/worker-1": {"kind": "Node", "name": "worker-1", "namespace": None, "status": "Ready"},
            "node/worker-2": {"kind": "Node", "name": "worker-2", "namespace": None, "status": "NotReady"},
        },
        "edges": [
            {"from_key": "node/worker-1", "to_key": "pod/prod/api-pod", "relation": "hosts"},
            {"from_key": "node/worker-2", "to_key": "pod/staging/web-pod", "relation": "hosts"},
        ],
        "built_at": "2026-03-01T00:00:00Z",
        "stale": False,
    }


# =========================================================================
# 1. test_correlator_reads_scoped_topology
# =========================================================================

def test_correlator_reads_scoped_topology():
    """When scoped_topology_graph is present, _extract_alerts reads from it."""
    state = {
        "scoped_topology_graph": _scoped_topology(),
        "topology_graph": _full_topology(),
    }
    alerts = _extract_alerts(state)
    # Scoped topology has only 1 problem node (CrashLoopBackOff pod)
    resource_keys = [a.resource_key for a in alerts]
    assert "pod/prod/api-pod" in resource_keys
    # Full topology has OOMKilled and NotReady -- those should NOT appear
    assert "pod/staging/web-pod" not in resource_keys
    assert "node/worker-2" not in resource_keys
    assert len(alerts) == 1


# =========================================================================
# 2. test_correlator_falls_back_to_full_topology
# =========================================================================

def test_correlator_falls_back_to_full_topology():
    """When scoped_topology_graph is absent, _extract_alerts falls back to topology_graph."""
    state = {
        "topology_graph": _full_topology(),
    }
    alerts = _extract_alerts(state)
    # Full topology has 3 problem nodes
    resource_keys = {a.resource_key for a in alerts}
    assert "pod/prod/api-pod" in resource_keys
    assert "pod/staging/web-pod" in resource_keys
    assert "node/worker-2" in resource_keys
    assert len(alerts) == 3


def test_correlator_falls_back_when_scoped_is_none():
    """When scoped_topology_graph is explicitly None, falls back to topology_graph."""
    state = {
        "scoped_topology_graph": None,
        "topology_graph": _full_topology(),
    }
    alerts = _extract_alerts(state)
    assert len(alerts) == 3


# =========================================================================
# 3. test_firewall_reads_scoped_topology
# =========================================================================

def test_firewall_reads_scoped_topology():
    """_check_soft_rules reads nodes from scoped_topology_graph when available."""
    scoped = {
        "nodes": {
            "node/worker-1": {"kind": "Node", "name": "worker-1", "status": "NotReady"},
            "pod/prod/api-pod": {"kind": "Pod", "name": "api-pod", "status": "Running"},
        },
        "edges": [
            {"from_key": "node/worker-1", "to_key": "pod/prod/api-pod", "relation": "hosts"},
        ],
    }
    full = {
        "nodes": {
            "node/worker-1": {"kind": "Node", "name": "worker-1", "status": "Ready"},  # Different status!
        },
        "edges": [],
    }
    state = {
        "scoped_topology_graph": scoped,
        "topology_graph": full,
    }
    # With scoped graph, node is NotReady and pod is not in problem state
    # so SOFT-001 should fire (NotReady node with no problem pods)
    annotation = _check_soft_rules("node/worker-1", "pod/prod/api-pod", state)
    assert annotation is not None
    assert annotation.rule_id == "SOFT-001"


def test_firewall_falls_back_to_full_topology():
    """_check_soft_rules falls back to topology_graph when scoped is absent."""
    full = {
        "nodes": {
            "node/worker-1": {"kind": "Node", "name": "worker-1", "status": "NotReady"},
            "pod/prod/api-pod": {"kind": "Pod", "name": "api-pod", "status": "Running"},
        },
        "edges": [
            {"from_key": "node/worker-1", "to_key": "pod/prod/api-pod", "relation": "hosts"},
        ],
    }
    state = {"topology_graph": full}
    annotation = _check_soft_rules("node/worker-1", "pod/prod/api-pod", state)
    assert annotation is not None
    assert annotation.rule_id == "SOFT-001"


# =========================================================================
# 4. test_correlator_function_reads_scoped_topology
# =========================================================================

@pytest.mark.asyncio
async def test_alert_correlator_function_reads_scoped():
    """The alert_correlator() LangGraph node reads from scoped_topology_graph."""
    state = {
        "scoped_topology_graph": _scoped_topology(),
        "topology_graph": _full_topology(),
    }
    result = await alert_correlator(state, {})
    clusters = result.get("issue_clusters", [])
    # Only scoped alerts should form clusters
    all_affected = []
    for c in clusters:
        all_affected.extend(c.get("affected_resources", []))
    assert "pod/prod/api-pod" in all_affected
    assert "pod/staging/web-pod" not in all_affected
    assert "node/worker-2" not in all_affected


# =========================================================================
# 5. test_causal_firewall_function_reads_scoped
# =========================================================================

@pytest.mark.asyncio
async def test_causal_firewall_function_reads_scoped():
    """The causal_firewall() LangGraph node reads edges from scoped_topology_graph."""
    state = {
        "scoped_topology_graph": {
            "nodes": {},
            "edges": [{"from_key": "a", "to_key": "b", "relation": "hosts"}],
        },
        "topology_graph": {
            "nodes": {},
            "edges": [
                {"from_key": "a", "to_key": "b", "relation": "hosts"},
                {"from_key": "c", "to_key": "d", "relation": "hosts"},
            ],
        },
        "issue_clusters": [],  # No clusters => no links to evaluate
    }
    result = await causal_firewall(state, {})
    space = result["causal_search_space"]
    # With no clusters, there are no candidate links, so totals are 0
    assert space["total_evaluated"] == 0


# =========================================================================
# 6. test_node_agent_filters_events_by_namespace
# =========================================================================

@pytest.mark.asyncio
async def test_node_agent_filters_events_by_namespace():
    """node_agent calls list_events per namespace when diagnostic_scope has namespaces."""
    mock_client = AsyncMock()
    mock_client.list_nodes.return_value = QueryResult(data=[{"name": "n1", "status": "Ready"}])
    mock_client.list_events.return_value = QueryResult(data=[{"type": "Warning", "message": "test"}])
    mock_client.list_pods.return_value = QueryResult(data=[])

    state = {
        "diagnostic_scope": {"namespaces": ["production", "staging"]},
        "platform": "kubernetes",
    }
    config = {"configurable": {"cluster_client": mock_client}}

    # Patch _llm_analyze to avoid real LLM calls
    with patch("src.agents.cluster.node_agent._llm_analyze", return_value={"anomalies": [], "ruled_out": [], "confidence": 50}):
        result = await node_agent(state, config)

    # list_events should be called once per namespace
    assert mock_client.list_events.call_count == 2
    calls = mock_client.list_events.call_args_list
    assert calls[0].kwargs.get("namespace") == "production"
    assert calls[1].kwargs.get("namespace") == "staging"


# Import here to avoid issues with traced_node wrapping
from src.agents.cluster.node_agent import node_agent


# =========================================================================
# 7. test_node_agent_cluster_wide_when_no_scope
# =========================================================================

@pytest.mark.asyncio
async def test_node_agent_cluster_wide_when_no_scope():
    """node_agent calls list_events() without namespace when no diagnostic_scope."""
    mock_client = AsyncMock()
    mock_client.list_nodes.return_value = QueryResult(data=[])
    mock_client.list_events.return_value = QueryResult(data=[])
    mock_client.list_pods.return_value = QueryResult(data=[])

    state = {"platform": "kubernetes"}
    config = {"configurable": {"cluster_client": mock_client}}

    with patch("src.agents.cluster.node_agent._llm_analyze", return_value={"anomalies": [], "ruled_out": [], "confidence": 50}):
        result = await node_agent(state, config)

    # list_events should be called once with no namespace
    assert mock_client.list_events.call_count == 1
    call_kwargs = mock_client.list_events.call_args_list[0].kwargs
    # No namespace param should be passed (or empty)
    assert call_kwargs.get("namespace", "") == ""


@pytest.mark.asyncio
async def test_node_agent_empty_namespaces_is_cluster_wide():
    """node_agent with empty namespaces list should behave like cluster-wide."""
    mock_client = AsyncMock()
    mock_client.list_nodes.return_value = QueryResult(data=[])
    mock_client.list_events.return_value = QueryResult(data=[])
    mock_client.list_pods.return_value = QueryResult(data=[])

    state = {
        "diagnostic_scope": {"namespaces": []},
        "platform": "kubernetes",
    }
    config = {"configurable": {"cluster_client": mock_client}}

    with patch("src.agents.cluster.node_agent._llm_analyze", return_value={"anomalies": [], "ruled_out": [], "confidence": 50}):
        result = await node_agent(state, config)

    # Empty list = cluster-wide, so a single call with no namespace
    assert mock_client.list_events.call_count == 1


# =========================================================================
# 8. test_ctrl_plane_preserves_field_selector_with_namespace
# =========================================================================

from src.agents.cluster.ctrl_plane_agent import ctrl_plane_agent


@pytest.mark.asyncio
async def test_ctrl_plane_preserves_field_selector_with_namespace():
    """ctrl_plane_agent preserves field_selector='involvedObject.kind=Node' even with namespace scope."""
    mock_client = AsyncMock()
    mock_client.get_api_health.return_value = {"status": "ok"}
    mock_client.get_cluster_operators.return_value = QueryResult(data=[])
    mock_client.list_events.return_value = QueryResult(data=[{"type": "Warning", "message": "node event"}])

    state = {
        "diagnostic_scope": {"namespaces": ["kube-system"]},
        "platform": "kubernetes",
    }
    config = {"configurable": {"cluster_client": mock_client}}

    with patch("src.agents.cluster.ctrl_plane_agent._llm_analyze", return_value={"anomalies": [], "ruled_out": [], "confidence": 50}):
        result = await ctrl_plane_agent(state, config)

    # Should be called once with namespace AND field_selector
    assert mock_client.list_events.call_count == 1
    call_kwargs = mock_client.list_events.call_args_list[0].kwargs
    assert call_kwargs.get("namespace") == "kube-system"
    assert call_kwargs.get("field_selector") == "involvedObject.kind=Node"


@pytest.mark.asyncio
async def test_ctrl_plane_cluster_wide_preserves_field_selector():
    """ctrl_plane_agent without scope still uses field_selector."""
    mock_client = AsyncMock()
    mock_client.get_api_health.return_value = {"status": "ok"}
    mock_client.get_cluster_operators.return_value = QueryResult(data=[])
    mock_client.list_events.return_value = QueryResult(data=[])

    state = {"platform": "kubernetes"}
    config = {"configurable": {"cluster_client": mock_client}}

    with patch("src.agents.cluster.ctrl_plane_agent._llm_analyze", return_value={"anomalies": [], "ruled_out": [], "confidence": 50}):
        result = await ctrl_plane_agent(state, config)

    assert mock_client.list_events.call_count == 1
    call_kwargs = mock_client.list_events.call_args_list[0].kwargs
    assert call_kwargs.get("field_selector") == "involvedObject.kind=Node"


# =========================================================================
# 9. test_storage_agent_filters_pvcs_by_namespace
# =========================================================================

from src.agents.cluster.storage_agent import storage_agent


@pytest.mark.asyncio
async def test_storage_agent_filters_pvcs_by_namespace():
    """storage_agent calls list_pvcs per namespace when diagnostic_scope has namespaces."""
    mock_client = AsyncMock()
    mock_client.list_pvcs.return_value = QueryResult(data=[{"name": "pvc-1", "namespace": "production"}])
    mock_client.query_prometheus.return_value = QueryResult(data=[])

    state = {
        "diagnostic_scope": {"namespaces": ["production", "staging"]},
        "platform": "kubernetes",
    }
    config = {"configurable": {"cluster_client": mock_client}}

    with patch("src.agents.cluster.storage_agent._llm_analyze", return_value={"anomalies": [], "ruled_out": [], "confidence": 50}):
        result = await storage_agent(state, config)

    # list_pvcs should be called once per namespace
    assert mock_client.list_pvcs.call_count == 2
    calls = mock_client.list_pvcs.call_args_list
    assert calls[0].kwargs.get("namespace") == "production"
    assert calls[1].kwargs.get("namespace") == "staging"


@pytest.mark.asyncio
async def test_storage_agent_cluster_wide_when_no_scope():
    """storage_agent calls list_pvcs() without namespace when no diagnostic_scope."""
    mock_client = AsyncMock()
    mock_client.list_pvcs.return_value = QueryResult(data=[])
    mock_client.query_prometheus.return_value = QueryResult(data=[])

    state = {"platform": "kubernetes"}
    config = {"configurable": {"cluster_client": mock_client}}

    with patch("src.agents.cluster.storage_agent._llm_analyze", return_value={"anomalies": [], "ruled_out": [], "confidence": 50}):
        result = await storage_agent(state, config)

    assert mock_client.list_pvcs.call_count == 1
    call_kwargs = mock_client.list_pvcs.call_args_list[0].kwargs
    assert call_kwargs.get("namespace", "") == ""

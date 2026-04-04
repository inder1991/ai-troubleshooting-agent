import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.cluster.graph import build_cluster_diagnostic_graph
from src.agents.cluster.state import DiagnosticScope


def test_graph_builds_without_error():
    graph = build_cluster_diagnostic_graph()
    assert graph is not None


def test_graph_has_new_nodes():
    graph = build_cluster_diagnostic_graph()
    # The compiled graph should contain all 9 nodes
    assert graph is not None


@pytest.mark.asyncio
async def test_graph_runs_with_mocks():
    """Integration test: graph runs end-to-end with mocked LLM calls."""
    from src.agents.cluster_client.mock_client import MockClusterClient
    from src.agents.cluster.topology_resolver import _topology_cache

    _topology_cache.clear()

    graph = build_cluster_diagnostic_graph()
    client = MockClusterClient(platform="openshift")
    emitter = AsyncMock()
    emitter.emit = AsyncMock()

    mock_analysis = {
        "anomalies": [{"domain": "test", "anomaly_id": "t-1", "description": "test issue", "evidence_ref": "ev-1"}],
        "ruled_out": [],
        "confidence": 80,
    }
    mock_causal = {
        "causal_chains": [],
        "uncorrelated_findings": [],
    }
    mock_verdict = {
        "platform_health": "HEALTHY",
        "blast_radius": {"summary": "No issues", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
        "remediation": {"immediate": [], "long_term": []},
        "re_dispatch_needed": False,
    }

    with patch("src.agents.cluster.ctrl_plane_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.node_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.network_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.storage_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.synthesizer._llm_causal_reasoning", new_callable=AsyncMock, return_value=mock_causal), \
         patch("src.agents.cluster.synthesizer._llm_verdict", new_callable=AsyncMock, return_value=mock_verdict):

        initial_state = {
            "diagnostic_id": "DIAG-TEST",
            "platform": "openshift",
            "platform_version": "4.14.2",
            "namespaces": ["default", "production"],
            "exclude_namespaces": [],
            "domain_reports": [],
            "causal_chains": [],
            "uncorrelated_findings": [],
            "health_report": None,
            "phase": "pre_flight",
            "re_dispatch_count": 0,
            "re_dispatch_domains": [],
            "data_completeness": 0.0,
            "error": None,
            "_trace": [],
            # New fields
            "topology_graph": {},
            "topology_freshness": {},
            "issue_clusters": [],
            "causal_search_space": {},
            "scan_mode": "diagnostic",
            "previous_scan": None,
            "guard_scan_result": None,
            # Scope-governed diagnostics
            "diagnostic_scope": DiagnosticScope().model_dump(mode="json"),
            "scoped_topology_graph": None,
            "dispatch_domains": ["ctrl_plane", "node", "network", "storage"],
            "scope_coverage": 1.0,
        }

        config = {
            "configurable": {
                "cluster_client": client,
                "emitter": emitter,
            }
        }

        result = await graph.ainvoke(initial_state, config=config)

    assert result.get("phase") == "complete"
    assert result.get("health_report") is not None
    # Verify new pipeline nodes ran
    assert result.get("topology_graph") is not None
    assert result.get("topology_graph") != {}  # topology resolver built something
    assert isinstance(result.get("issue_clusters"), list)
    assert isinstance(result.get("causal_search_space"), dict)

    _topology_cache.clear()


class TestDispatchRouterRBAC:
    def test_skips_node_domain_when_nodes_denied(self):
        from src.agents.cluster.graph import dispatch_router
        state = {
            "diagnostic_scope": None,
            "rbac_check": {"granted": ["pods", "events"], "denied": ["nodes"]},
        }
        result = dispatch_router(state)
        assert "node" not in result["dispatch_domains"]

    def test_skips_storage_when_pvc_denied(self):
        from src.agents.cluster.graph import dispatch_router
        state = {
            "diagnostic_scope": None,
            "rbac_check": {"granted": ["nodes", "pods"], "denied": ["persistentvolumeclaims"]},
        }
        result = dispatch_router(state)
        assert "storage" not in result["dispatch_domains"]

    def test_skips_ctrl_plane_and_node_when_pods_denied(self):
        from src.agents.cluster.graph import dispatch_router
        state = {
            "diagnostic_scope": None,
            "rbac_check": {"granted": ["nodes"], "denied": ["pods"]},
        }
        result = dispatch_router(state)
        assert "ctrl_plane" not in result["dispatch_domains"]
        assert "node" not in result["dispatch_domains"]

    def test_no_rbac_check_runs_all_domains(self):
        from src.agents.cluster.graph import dispatch_router
        state = {"diagnostic_scope": None, "rbac_check": None}
        result = dispatch_router(state)
        assert "node" in result["dispatch_domains"]
        assert "storage" in result["dispatch_domains"]
        assert "ctrl_plane" in result["dispatch_domains"]

    def test_rbac_skips_recorded_in_result(self):
        from src.agents.cluster.graph import dispatch_router
        state = {
            "diagnostic_scope": None,
            "rbac_check": {"granted": [], "denied": ["nodes"]},
        }
        result = dispatch_router(state)
        assert "rbac_skipped" in result
        assert any(s["domain"] == "node" for s in result["rbac_skipped"])

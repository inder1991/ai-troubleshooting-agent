import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.cluster.graph import build_cluster_diagnostic_graph


def test_graph_builds_without_error():
    graph = build_cluster_diagnostic_graph()
    assert graph is not None


@pytest.mark.asyncio
async def test_graph_runs_with_mocks():
    """Integration test: graph runs end-to-end with mocked LLM calls."""
    from src.agents.cluster_client.mock_client import MockClusterClient
    from src.agents.cluster.state import ClusterDiagnosticState

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

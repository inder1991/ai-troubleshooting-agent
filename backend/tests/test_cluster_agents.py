import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.cluster.ctrl_plane_agent import ctrl_plane_agent
from src.agents.cluster.node_agent import node_agent
from src.agents.cluster.network_agent import network_agent
from src.agents.cluster.storage_agent import storage_agent
from src.agents.cluster.state import ClusterDiagnosticState, DomainStatus


def _make_state():
    return ClusterDiagnosticState(
        diagnostic_id="DIAG-TEST",
        platform="openshift",
        platform_version="4.14.2",
        namespaces=["default", "production"],
    ).model_dump(mode="json")


def _make_config(mock_client):
    return {
        "configurable": {
            "cluster_client": mock_client,
            "emitter": AsyncMock(),
            "diagnostic_cache": MagicMock(),
        }
    }


@pytest.mark.asyncio
async def test_ctrl_plane_agent_mock():
    from src.agents.cluster_client.mock_client import MockClusterClient
    client = MockClusterClient(platform="openshift")
    state = _make_state()
    config = _make_config(client)

    with patch("src.agents.cluster.ctrl_plane_agent._llm_analyze", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "anomalies": [{"domain": "ctrl_plane", "anomaly_id": "cp-001", "description": "DNS operator degraded", "evidence_ref": "ev-001"}],
            "ruled_out": ["etcd healthy"],
            "confidence": 75,
        }
        result = await ctrl_plane_agent(state, config)

    assert "domain_reports" in result
    report = result["domain_reports"][0]
    assert report["domain"] == "ctrl_plane"


@pytest.mark.asyncio
async def test_node_agent_mock():
    from src.agents.cluster_client.mock_client import MockClusterClient
    client = MockClusterClient()
    state = _make_state()
    config = _make_config(client)

    with patch("src.agents.cluster.node_agent._llm_analyze", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "anomalies": [{"domain": "node", "anomaly_id": "node-003", "description": "infra-node-03 disk 97%", "evidence_ref": "ev-002"}],
            "ruled_out": [],
            "confidence": 90,
        }
        result = await node_agent(state, config)

    assert "domain_reports" in result
    report = result["domain_reports"][0]
    assert report["domain"] == "node"


@pytest.mark.asyncio
async def test_network_agent_mock():
    from src.agents.cluster_client.mock_client import MockClusterClient
    client = MockClusterClient()
    state = _make_state()
    config = _make_config(client)

    with patch("src.agents.cluster.network_agent._llm_analyze", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "anomalies": [{"domain": "network", "anomaly_id": "net-001", "description": "40% DNS failures", "evidence_ref": "ev-003"}],
            "ruled_out": [],
            "confidence": 80,
        }
        result = await network_agent(state, config)

    assert "domain_reports" in result


@pytest.mark.asyncio
async def test_storage_agent_mock():
    from src.agents.cluster_client.mock_client import MockClusterClient
    client = MockClusterClient()
    state = _make_state()
    config = _make_config(client)

    with patch("src.agents.cluster.storage_agent._llm_analyze", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "anomalies": [],
            "ruled_out": ["CSI healthy", "no stuck PVCs"],
            "confidence": 85,
        }
        result = await storage_agent(state, config)

    assert "domain_reports" in result
    report = result["domain_reports"][0]
    assert report["domain"] == "storage"


class TestNodeAgentPrometheus:
    def test_node_agent_queries_prometheus_when_client_available(self):
        """node_agent should call prometheus_client.query_instant() when injected."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch

        mock_prom = MagicMock()
        mock_prom.query_instant = AsyncMock(return_value={
            "data": {"resultType": "vector", "result": []}
        })

        def _make_query_result(data=None):
            r = MagicMock()
            r.data = data if data is not None else []
            r.permission_denied = False
            r.truncated = False
            r.total_available = 0
            r.returned = 0
            return r

        mock_cluster = MagicMock()
        mock_cluster.list_nodes = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_pods = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_events = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_deployments = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_statefulsets = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_daemonsets = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_hpas = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_pdbs = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_jobs = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_cronjobs = AsyncMock(return_value=_make_query_result())
        mock_cluster.query_prometheus = AsyncMock(return_value=_make_query_result())

        config = {"configurable": {
            "cluster_client": mock_cluster,
            "prometheus_client": mock_prom,
            "elk_client": None,
            "elk_index": "",
            "emitter": MagicMock(),
            "budget": MagicMock(should_skip=MagicMock(return_value=False), can_call=MagicMock(return_value=False)),
            "telemetry": MagicMock(),
        }}
        state = {
            "platform": "kubernetes",
            "platform_version": "1.28",
            "namespaces": ["default"],
            "diagnostic_scope": {},
            "dispatch_domains": ["node"],
            "scan_mode": "diagnostic",
            "cluster_url": "https://api.example.com:6443",
            "cluster_type": "kubernetes",
            "cluster_role": "",
        }

        with patch("src.agents.cluster.node_agent._heuristic_analyze", new_callable=AsyncMock) as mock_heuristic:

            mock_heuristic.return_value = {
                "anomalies": [],
                "ruled_out": [],
                "confidence": 50,
            }
            from src.agents.cluster.node_agent import node_agent
            asyncio.run(node_agent(state, config))

        # prometheus_client.query_instant should have been called
        assert mock_prom.query_instant.called

    def test_node_agent_skips_prometheus_when_client_is_none(self):
        """node_agent should not fail when prometheus_client is None."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch

        def _make_query_result(data=None):
            r = MagicMock()
            r.data = data if data is not None else []
            r.permission_denied = False
            r.truncated = False
            r.total_available = 0
            r.returned = 0
            return r

        mock_cluster = MagicMock()
        mock_cluster.list_nodes = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_pods = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_events = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_deployments = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_statefulsets = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_daemonsets = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_hpas = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_pdbs = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_jobs = AsyncMock(return_value=_make_query_result())
        mock_cluster.list_cronjobs = AsyncMock(return_value=_make_query_result())
        mock_cluster.query_prometheus = AsyncMock(return_value=_make_query_result())

        config = {"configurable": {
            "cluster_client": mock_cluster,
            "prometheus_client": None,  # No Prometheus
            "elk_client": None,
            "elk_index": "",
            "emitter": MagicMock(),
            "budget": MagicMock(should_skip=MagicMock(return_value=False), can_call=MagicMock(return_value=False)),
            "telemetry": MagicMock(),
        }}
        state = {
            "platform": "kubernetes",
            "platform_version": "1.28",
            "namespaces": ["default"],
            "diagnostic_scope": {},
            "dispatch_domains": ["node"],
            "scan_mode": "diagnostic",
            "cluster_url": "",
            "cluster_type": "",
            "cluster_role": "",
        }

        with patch("src.agents.cluster.node_agent._heuristic_analyze", new_callable=AsyncMock) as mock_heuristic:
            mock_heuristic.return_value = {
                "anomalies": [],
                "ruled_out": [],
                "confidence": 50,
            }
            from src.agents.cluster.node_agent import node_agent
            # Should not raise
            result = asyncio.run(node_agent(state, config))
        assert result is not None

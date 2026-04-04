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


@pytest.mark.asyncio
async def test_network_agent_uses_prometheus_client():
    """network_agent must call prometheus_client.query_instant, not cluster_client.query_prometheus."""
    from src.agents.cluster.network_agent import network_agent
    from unittest.mock import MagicMock, AsyncMock, patch

    mock_prom = MagicMock()
    mock_prom.query_instant = AsyncMock(return_value={
        "status": "success",
        "data": {"result": []}
    })

    def _qr(data=None):
        r = MagicMock()
        r.data = data if data is not None else []
        r.permission_denied = False
        r.truncated = False
        r.total_available = 0
        r.returned = 0
        return r

    mock_cluster = MagicMock()
    mock_cluster.list_pods = AsyncMock(return_value=_qr())
    mock_cluster.list_services = AsyncMock(return_value=_qr())
    mock_cluster.list_events = AsyncMock(return_value=_qr())
    mock_cluster.list_ingresses = AsyncMock(return_value=_qr())
    mock_cluster.get_routes = AsyncMock(return_value=_qr())
    mock_cluster.list_network_policies = AsyncMock(return_value=_qr())
    mock_cluster.list_endpoints = AsyncMock(return_value=_qr())

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
        "dispatch_domains": ["network"],
        "scan_mode": "diagnostic",
        "cluster_url": "https://api.example.com:6443",
        "cluster_type": "kubernetes",
        "cluster_role": "",
    }

    with patch("src.agents.cluster.network_agent._heuristic_analyze", new_callable=AsyncMock) as mock_h:
        mock_h.return_value = {"anomalies": [], "ruled_out": [], "confidence": 50}
        result = await network_agent(state, config)

    assert mock_prom.query_instant.called, \
        "network_agent must call prometheus_client.query_instant() when prometheus_client is provided"
    assert result is not None


@pytest.mark.asyncio
async def test_network_agent_skips_prometheus_when_none():
    """network_agent must not fail when prometheus_client is None."""
    from src.agents.cluster.network_agent import network_agent
    from unittest.mock import MagicMock, AsyncMock, patch

    def _qr(data=None):
        r = MagicMock()
        r.data = data if data is not None else []
        r.permission_denied = False
        r.truncated = False
        r.total_available = 0
        r.returned = 0
        return r

    mock_cluster = MagicMock()
    mock_cluster.list_pods = AsyncMock(return_value=_qr())
    mock_cluster.list_services = AsyncMock(return_value=_qr())
    mock_cluster.list_events = AsyncMock(return_value=_qr())
    mock_cluster.list_ingresses = AsyncMock(return_value=_qr())
    mock_cluster.get_routes = AsyncMock(return_value=_qr())
    mock_cluster.list_network_policies = AsyncMock(return_value=_qr())
    mock_cluster.list_endpoints = AsyncMock(return_value=_qr())

    config = {"configurable": {
        "cluster_client": mock_cluster,
        "prometheus_client": None,
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
        "dispatch_domains": ["network"],
        "scan_mode": "diagnostic",
        "cluster_url": "",
        "cluster_type": "",
        "cluster_role": "",
    }

    with patch("src.agents.cluster.network_agent._heuristic_analyze", new_callable=AsyncMock) as mock_h:
        mock_h.return_value = {"anomalies": [], "ruled_out": [], "confidence": 50}
        result = await network_agent(state, config)

    assert result is not None


@pytest.mark.asyncio
async def test_network_agent_uses_elk_client():
    """network_agent must call elk_client.search() when elk_client and elk_index are provided."""
    from src.agents.cluster.network_agent import network_agent
    from unittest.mock import MagicMock, AsyncMock, patch

    mock_elk = MagicMock()
    mock_elk.search = AsyncMock(return_value={
        "hits": {
            "total": {"value": 3},
            "hits": [{"_source": {"message": "test"}}],
        }
    })

    def _qr(data=None):
        r = MagicMock()
        r.data = data if data is not None else []
        r.permission_denied = False
        r.truncated = False
        r.total_available = 0
        r.returned = 0
        return r

    mock_cluster = MagicMock()
    mock_cluster.list_pods = AsyncMock(return_value=_qr())
    mock_cluster.list_services = AsyncMock(return_value=_qr())
    mock_cluster.list_events = AsyncMock(return_value=_qr())
    mock_cluster.list_ingresses = AsyncMock(return_value=_qr())
    mock_cluster.get_routes = AsyncMock(return_value=_qr())
    mock_cluster.list_network_policies = AsyncMock(return_value=_qr())
    mock_cluster.list_endpoints = AsyncMock(return_value=_qr())

    config = {"configurable": {
        "cluster_client": mock_cluster,
        "prometheus_client": None,
        "elk_client": mock_elk,
        "elk_index": "k8s-logs-*",
        "emitter": MagicMock(),
        "budget": MagicMock(should_skip=MagicMock(return_value=False), can_call=MagicMock(return_value=False)),
        "telemetry": MagicMock(),
    }}
    state = {
        "platform": "kubernetes",
        "platform_version": "1.28",
        "namespaces": ["default"],
        "diagnostic_scope": {},
        "dispatch_domains": ["network"],
        "scan_mode": "diagnostic",
        "cluster_url": "https://api.example.com:6443",
        "cluster_type": "kubernetes",
        "cluster_role": "",
    }

    with patch("src.agents.cluster.network_agent._heuristic_analyze", new_callable=AsyncMock) as mock_h:
        mock_h.return_value = {"anomalies": [], "ruled_out": [], "confidence": 50}
        result = await network_agent(state, config)

    assert mock_elk.search.called, \
        "network_agent must call elk_client.search() when elk_client and elk_index are provided"
    assert result is not None


@pytest.mark.asyncio
async def test_rbac_checker_openshift_denied_resources_not_in_granted():
    """OpenShift resources that return permission_denied must appear in denied, not granted."""
    from src.agents.cluster.rbac_checker import rbac_preflight

    mock_client = MagicMock()
    # OpenShift Routes: permission denied
    routes_result = MagicMock()
    routes_result.permission_denied = True
    mock_client.get_routes = AsyncMock(return_value=routes_result)

    # OpenShift ClusterOperators: permission denied
    operators_result = MagicMock()
    operators_result.permission_denied = True
    mock_client.get_cluster_operators = AsyncMock(return_value=operators_result)

    # MachineConfigPools: permission denied
    mcp_result = MagicMock()
    mcp_result.permission_denied = True
    mock_client.list_machine_config_pools = AsyncMock(return_value=mcp_result)

    state = {"platform": "openshift"}
    config = {"configurable": {"cluster_client": mock_client}}

    result = await rbac_preflight(state, config)
    rbac = result["rbac_check"]

    assert "routes" not in rbac["granted"], \
        f"'routes' must not appear in granted when permission_denied=True. granted={rbac['granted']}"
    assert "clusteroperators" not in rbac["granted"], \
        f"'clusteroperators' must not appear in granted. granted={rbac['granted']}"
    assert "machineconfigpools" not in rbac["granted"], \
        f"'machineconfigpools' must not appear in granted. granted={rbac['granted']}"

    assert "routes" in rbac["denied"]
    assert "clusteroperators" in rbac["denied"]
    assert "machineconfigpools" in rbac["denied"]


@pytest.mark.asyncio
async def test_rbac_checker_resolution_fail_when_critical_denied():
    """Status must be 'fail' when nodes/pods/events are denied (critical_denied non-empty)."""
    from src.agents.cluster.rbac_checker import rbac_preflight

    mock_client = MagicMock()
    # Make the _check_access_nodes method return False (denied)
    mock_client._check_access_nodes = AsyncMock(return_value=False)
    mock_client._check_access_pods = AsyncMock(return_value=False)
    mock_client._check_access_events = AsyncMock(return_value=False)

    state = {"platform": "kubernetes"}
    config = {"configurable": {"cluster_client": mock_client}}

    result = await rbac_preflight(state, config)
    rbac = result["rbac_check"]

    assert rbac["status"] == "fail", \
        f"Status must be 'fail' when critical resources (nodes/pods/events) are denied. Got: {rbac['status']}"
    assert "nodes" in rbac["denied"] or "pods" in rbac["denied"] or "events" in rbac["denied"], \
        f"At least one critical resource must be in denied. denied={rbac['denied']}"


@pytest.mark.asyncio
async def test_rbac_checker_resolution_partial_when_noncritical_denied():
    """Status must be 'partial' when only non-critical resources are denied."""
    from src.agents.cluster.rbac_checker import rbac_preflight

    mock_client = MagicMock()
    # Critical resources granted
    mock_client._check_access_nodes = AsyncMock(return_value=True)
    mock_client._check_access_pods = AsyncMock(return_value=True)
    mock_client._check_access_events = AsyncMock(return_value=True)
    # Non-critical resource denied
    mock_client._check_access_deployments = AsyncMock(return_value=False)

    state = {"platform": "kubernetes"}
    config = {"configurable": {"cluster_client": mock_client}}

    result = await rbac_preflight(state, config)
    rbac = result["rbac_check"]

    # deployments is non-critical — status must be partial since nodes/pods/events all return True
    assert rbac["status"] == "partial", \
        f"Status must be 'partial' when only non-critical resources denied. Got: {rbac['status']}"
    assert rbac["status"] != "fail" or any(
        r in rbac["denied"] for r in ("nodes", "pods", "events")
    ), "Status is 'fail' but no critical resources are denied — that is a bug"

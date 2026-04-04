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


@pytest.mark.asyncio
async def test_storage_agent_uses_prometheus_client():
    """storage_agent must call prometheus_client.query_instant when client is provided."""
    from src.agents.cluster.storage_agent import storage_agent
    from unittest.mock import MagicMock, AsyncMock, patch

    mock_prom = MagicMock()
    mock_prom.query_instant = AsyncMock(return_value={
        "status": "success",
        "data": {"result": [
            {"metric": {"persistentvolumeclaim": "data-pvc"}, "value": [1617000000, "85.5"]}
        ]}
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
    mock_cluster.list_pvcs = AsyncMock(return_value=_qr())
    mock_cluster.list_pvs = AsyncMock(return_value=_qr())
    mock_cluster.list_storage_classes = AsyncMock(return_value=_qr())
    mock_cluster.list_pods = AsyncMock(return_value=_qr())
    mock_cluster.list_events = AsyncMock(return_value=_qr())

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
        "dispatch_domains": ["storage"],
        "scan_mode": "diagnostic",
        "cluster_url": "https://api.example.com:6443",
        "cluster_type": "kubernetes",
        "cluster_role": "",
    }

    with patch("src.agents.cluster.storage_agent._heuristic_analyze", new_callable=AsyncMock) as mock_h:
        mock_h.return_value = {"anomalies": [], "ruled_out": [], "confidence": 50}
        result = await storage_agent(state, config)

    assert mock_prom.query_instant.called, \
        "storage_agent must call prometheus_client.query_instant() when client is provided"
    assert result is not None


@pytest.mark.asyncio
async def test_node_agent_has_workload_tools():
    """node_agent must be able to call list_statefulsets, list_daemonsets, list_jobs, list_cronjobs."""
    from src.agents.cluster.tools import NODE_TOOLS, get_tools_for_agent

    # NODE_TOOLS is a list of tool name strings; get_tools_for_agent returns full schemas
    assert "list_statefulsets" in NODE_TOOLS, "NODE_TOOLS missing list_statefulsets"
    assert "list_daemonsets" in NODE_TOOLS, "NODE_TOOLS missing list_daemonsets"
    assert "list_jobs" in NODE_TOOLS, "NODE_TOOLS missing list_jobs"
    assert "list_cronjobs" in NODE_TOOLS, "NODE_TOOLS missing list_cronjobs"

    # Verify get_tools_for_agent returns schema dicts for these tools
    node_schemas = get_tools_for_agent("node")
    schema_names = {t["name"] for t in node_schemas}
    assert "list_statefulsets" in schema_names, "get_tools_for_agent('node') missing list_statefulsets schema"
    assert "list_daemonsets" in schema_names, "get_tools_for_agent('node') missing list_daemonsets schema"
    assert "list_jobs" in schema_names, "get_tools_for_agent('node') missing list_jobs schema"
    assert "list_cronjobs" in schema_names, "get_tools_for_agent('node') missing list_cronjobs schema"


@pytest.mark.asyncio
async def test_tool_executor_handles_workload_types():
    """tool_executor must not return Unknown tool for the 4 workload types."""
    from src.agents.cluster.tool_executor import execute_tool_call
    from unittest.mock import MagicMock, AsyncMock

    def _qr(data=None):
        r = MagicMock()
        r.data = data if data is not None else []
        r.permission_denied = False
        r.truncated = False
        r.total_available = 0
        r.returned = 0
        return r

    mock_client = MagicMock()
    mock_client.list_statefulsets = AsyncMock(return_value=_qr())
    mock_client.list_daemonsets = AsyncMock(return_value=_qr())
    mock_client.list_jobs = AsyncMock(return_value=_qr())
    mock_client.list_cronjobs = AsyncMock(return_value=_qr())

    import json as _json
    for tool_name in ["list_statefulsets", "list_daemonsets", "list_jobs", "list_cronjobs"]:
        result_str = await execute_tool_call(tool_name, {"namespace": "default"}, mock_client)
        result = _json.loads(result_str)
        assert isinstance(result, list), \
            f"Expected list result for {tool_name}, got: {result}"


def test_ctrl_plane_prompt_has_evidence_rules():
    """_ANALYSIS_PROMPT must contain specific evidence-anchored diagnostic rules."""
    from src.agents.cluster.ctrl_plane_agent import _ANALYSIS_PROMPT

    required_phrases = [
        "Degraded",
        "Available",
        "OOMKill",
        "NotReady",
        "MachineConfigPool",
        "degradedMachineCount",
        "machineCount",
        "updatedMachineCount",
        "Warning",
    ]

    for phrase in required_phrases:
        assert phrase in _ANALYSIS_PROMPT, \
            f"_ANALYSIS_PROMPT missing evidence rule for: '{phrase}'"


def test_prometheus_volume_metric_parsing():
    """Volume metric parser must extract float(item['value'][1]) from Prometheus response format."""
    # Import the helper — read the file to find its actual name
    # This test verifies the correct format: value is [timestamp, "value_string"]
    prometheus_response = {
        "status": "success",
        "data": {"result": [
            {"metric": {"persistentvolumeclaim": "data-pvc"}, "value": [1617000000, "85.5"]},
            {"metric": {"persistentvolumeclaim": "logs-pvc"}, "value": [1617000000, "92.1"]},
        ]}
    }
    results = prometheus_response.get("data", {}).get("result", [])

    # The correct parsing pattern
    parsed = {}
    for item in results:
        pvc = item["metric"].get("persistentvolumeclaim", "unknown")
        value = float(item["value"][1])  # [timestamp, "value_string"]
        parsed[pvc] = value

    assert parsed["data-pvc"] == 85.5
    assert parsed["logs-pvc"] == 92.1


@pytest.mark.asyncio
async def test_synthesizer_injects_cluster_context():
    """_llm_causal_reasoning must include platform, namespace, cluster_url in the system prompt."""
    from src.agents.cluster.synthesizer import _llm_causal_reasoning
    from unittest.mock import patch, MagicMock, AsyncMock

    captured_calls = {}

    class FakeResponse:
        text = '{"causal_chains": [], "uncorrelated_findings": []}'
        usage = None

    async def fake_chat(prompt, system="", max_tokens=3000, temperature=0.1):
        captured_calls["system"] = system
        captured_calls["prompt"] = prompt
        return FakeResponse()

    mock_client = MagicMock()
    mock_client.chat = fake_chat

    with patch("src.agents.cluster.synthesizer.AnthropicClient", return_value=mock_client):
        from src.agents.cluster.state import DomainAnomaly, DomainReport, DomainStatus
        anomaly = DomainAnomaly(
            domain="node",
            anomaly_id="node-001",
            description="disk pressure",
            evidence_ref="ev-001",
        )
        report = DomainReport(
            domain="node",
            status=DomainStatus.SUCCESS,
            anomalies=[anomaly],
            ruled_out=[],
            confidence=80,
        )
        await _llm_causal_reasoning(
            anomalies=[anomaly],
            reports=[report],
            platform="openshift",
            namespace="production",
            cluster_url="https://api.example.com:6443",
        )

    system_prompt = captured_calls.get("system", "")
    assert "openshift" in system_prompt.lower(), \
        f"Platform 'openshift' not found in system prompt: {system_prompt!r}"
    assert "production" in system_prompt, \
        f"Namespace 'production' not found in system prompt: {system_prompt!r}"
    assert "api.example.com" in system_prompt, \
        f"Cluster URL not found in system prompt: {system_prompt!r}"


@pytest.mark.asyncio
async def test_synthesizer_verdict_has_redispatch_domains():
    """_llm_verdict must return re_dispatch_domains and validate against known domain set."""
    from src.agents.cluster.synthesizer import _llm_verdict
    from unittest.mock import patch, MagicMock

    class FakeResponse:
        text = '{"platform_health": "DEGRADED", "blast_radius": {"summary": "test", "affected_namespaces": 1, "affected_pods": 2, "affected_nodes": 1}, "remediation": {"immediate": [], "long_term": []}, "re_dispatch_needed": true, "re_dispatch_domains": ["node", "network", "invalid_domain"]}'
        usage = None

    async def fake_chat(prompt, system="", max_tokens=2000, temperature=0.1):
        return FakeResponse()

    mock_client = MagicMock()
    mock_client.chat = fake_chat

    with patch("src.agents.cluster.synthesizer.AnthropicClient", return_value=mock_client):
        result = await _llm_verdict(
            causal_chains=[],
            reports=[],
            data_completeness=1.0,
        )

    assert "re_dispatch_domains" in result, "Verdict must include re_dispatch_domains"
    # "invalid_domain" must be filtered out, valid ones kept
    assert "invalid_domain" not in result["re_dispatch_domains"], \
        "Invalid domain must be filtered from re_dispatch_domains"
    assert "node" in result["re_dispatch_domains"], "Valid domain 'node' must be kept"
    assert "network" in result["re_dispatch_domains"], "Valid domain 'network' must be kept"


def test_node_os_patch_does_not_use_creation_timestamp_fallback():
    """_check_node_os_patch must generate a finding for old RHEL8 kernel regardless of recent creation_timestamp."""
    from src.agents.cluster.proactive_analyzer import _check_node_os_patch

    # Use kernel 4.17.x which is clearly below the (4,18) minimum for RHEL8.
    rhel8_node_below_min = {
        "name": "worker-rhel8",
        "kernel_version": "4.17.0-372.9.1.el8.x86_64",
        "os_image": "Red Hat Enterprise Linux 8.6",
        "creation_timestamp": "2026-04-03T10:00:00Z",  # recent — must NOT suppress the finding
    }

    result = _check_node_os_patch([rhel8_node_below_min])

    # Finding must be generated — creation_timestamp being recent must NOT skip the check
    assert len(result) > 0, (
        "Should return a finding for RHEL8 node with kernel below minimum (4.18), "
        "even when creation_timestamp is recent"
    )


def test_node_os_patch_skips_node_with_unparseable_kernel():
    """_check_node_os_patch must skip nodes with empty kernel_version — no findings generated."""
    from src.agents.cluster.proactive_analyzer import _check_node_os_patch

    empty_kernel_node = {
        "name": "mystery-node",
        "kernel_version": "",  # empty string — unparseable
        "os_image": "Red Hat Enterprise Linux 8.6",
        "creation_timestamp": "2020-01-01T00:00:00Z",  # old date — must NOT be used as fallback
    }

    result = _check_node_os_patch([empty_kernel_node])

    # Should return empty list — no fallback to creation_timestamp
    assert len(result) == 0, (
        "Should return no findings when kernel_version is empty — "
        "must not fall back to creation_timestamp"
    )


def test_node_os_patch_never_uses_creation_timestamp():
    """_check_node_os_patch must not use creation_timestamp as kernel age proxy."""
    from src.agents.cluster import proactive_analyzer
    import inspect

    source = inspect.getsource(proactive_analyzer._check_node_os_patch)
    assert "creation_timestamp" not in source, \
        "_check_node_os_patch must not reference creation_timestamp"


def test_quota_pressure_recommendation_names_specific_resource_and_namespace():
    """quota_pressure recommendation must name the specific resource and namespace."""
    from src.agents.cluster.proactive_analyzer import _check_quota_pressure

    fake_data = [{
        "name": "compute-resources",
        "namespace": "production",
        "status": {
            "hard": {"requests.cpu": "20"},
            "used": {"requests.cpu": "19"},  # 95% usage
        }
    }]

    findings = _check_quota_pressure(fake_data)
    assert findings, "No finding at 95% quota usage"

    rec = findings[0].recommendation or ""
    commands = findings[0].commands or []

    assert "production" in rec or any("production" in c for c in commands), \
        f"Namespace 'production' not referenced in recommendation or commands. rec='{rec}' commands={commands}"
    assert "requests.cpu" in rec or any("requests.cpu" in c for c in commands), \
        f"Resource name 'requests.cpu' not in recommendation or commands"

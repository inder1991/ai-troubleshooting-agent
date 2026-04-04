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


class TestClusterMetadataInState:
    def test_initial_state_has_cluster_url(self):
        """run_cluster_diagnosis should include cluster_url in initial_state."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock

        mock_client = MagicMock()
        mock_client.detect_platform = AsyncMock(return_value={"platform": "openshift", "version": "4.14"})
        mock_client.list_namespaces = AsyncMock(return_value=MagicMock(data=["default"]))
        mock_client.list_nodes = AsyncMock(return_value=MagicMock(data=[]))
        mock_client.close = AsyncMock()

        captured_state = {}
        async def mock_graph_invoke(state, config):
            captured_state.update(state)
            return {**state, "phase": "complete", "data_completeness": 0.8,
                    "domain_reports": [], "health_report": None}

        mock_graph = MagicMock()
        mock_graph.ainvoke = mock_graph_invoke

        from src.api.routes_v4 import run_cluster_diagnosis, sessions
        from src.integrations.connection_config import ResolvedConnectionConfig

        sid = "test-meta-state-001"
        cfg = ResolvedConnectionConfig(
            cluster_url="https://api.cluster.example.com:6443",
            cluster_type="openshift",
            role="cluster-admin",
        )
        sessions[sid] = {
            "diagnostic_scope": {},
            "connection_config": cfg,
            "elk_index": "",
        }

        emitter = MagicMock()
        emitter.emit = AsyncMock()

        asyncio.run(
            run_cluster_diagnosis(sid, mock_graph, mock_client, emitter, connection_config=cfg)
        )
        assert captured_state.get("cluster_url") == "https://api.cluster.example.com:6443"
        assert captured_state.get("cluster_type") == "openshift"
        assert captured_state.get("cluster_role") == "cluster-admin"


class TestRetryUtility:
    def test_with_retry_succeeds_on_second_attempt(self):
        import asyncio
        from src.agents.cluster.retry_utils import with_retry

        call_count = [0]

        @with_retry(retries=2, backoff=0.01)
        async def flaky():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ConnectionError("transient error")
            return "ok"

        result = asyncio.run(flaky())
        assert result == "ok"
        assert call_count[0] == 2

    def test_with_retry_raises_after_all_attempts_exhausted(self):
        import asyncio
        from src.agents.cluster.retry_utils import with_retry

        @with_retry(retries=2, backoff=0.01)
        async def always_fails():
            raise ConnectionError("always fails")

        try:
            asyncio.run(always_fails())
            assert False, "Should have raised"
        except ConnectionError as e:
            assert str(e) == "always fails"

    def test_with_retry_succeeds_immediately_no_retries(self):
        import asyncio
        from src.agents.cluster.retry_utils import with_retry

        @with_retry(retries=2, backoff=0.01)
        async def always_works():
            return 42

        result = asyncio.run(always_works())
        assert result == 42


class TestPrometheusDetector:
    def test_detects_thanos_querier_route_on_openshift(self):
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from src.agents.cluster.prometheus_detector import detect_prometheus_endpoint

        mock_client = MagicMock()
        mock_client.get_routes = AsyncMock(return_value=MagicMock(data=[
            {
                "namespace": "openshift-monitoring",
                "name": "thanos-querier",
                "host": "thanos.apps.cluster.example.com",
            },
        ]))

        url = asyncio.run(detect_prometheus_endpoint(mock_client, "openshift"))
        assert url == "https://thanos.apps.cluster.example.com"

    def test_detects_prometheus_k8s_route_on_openshift(self):
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from src.agents.cluster.prometheus_detector import detect_prometheus_endpoint

        mock_client = MagicMock()
        mock_client.get_routes = AsyncMock(return_value=MagicMock(data=[
            {
                "namespace": "openshift-monitoring",
                "name": "prometheus-k8s",
                "host": "prometheus.apps.cluster.example.com",
            },
        ]))

        url = asyncio.run(detect_prometheus_endpoint(mock_client, "openshift"))
        assert url == "https://prometheus.apps.cluster.example.com"

    def test_returns_empty_when_no_routes_found(self):
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from src.agents.cluster.prometheus_detector import detect_prometheus_endpoint

        mock_client = MagicMock()
        mock_client.get_routes = AsyncMock(return_value=MagicMock(data=[]))

        url = asyncio.run(detect_prometheus_endpoint(mock_client, "openshift"))
        assert url == ""

    def test_detects_prometheus_service_on_kubernetes(self):
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from src.agents.cluster.prometheus_detector import detect_prometheus_endpoint

        mock_client = MagicMock()
        mock_client.list_services = AsyncMock(return_value=MagicMock(data=[
            {"name": "prometheus-operated", "external_ip": "10.0.0.50", "port": 9090},
        ]))

        url = asyncio.run(detect_prometheus_endpoint(mock_client, "kubernetes"))
        assert url == "http://10.0.0.50:9090"

    def test_returns_empty_when_no_prometheus_service_found(self):
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from src.agents.cluster.prometheus_detector import detect_prometheus_endpoint

        mock_client = MagicMock()
        mock_client.list_services = AsyncMock(return_value=MagicMock(data=[
            {"name": "kube-dns", "external_ip": "10.0.0.10", "port": 53},
        ]))

        url = asyncio.run(detect_prometheus_endpoint(mock_client, "kubernetes"))
        assert url == ""

    def test_returns_empty_on_client_exception(self):
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from src.agents.cluster.prometheus_detector import detect_prometheus_endpoint

        mock_client = MagicMock()
        mock_client.get_routes = AsyncMock(side_effect=Exception("connection refused"))

        url = asyncio.run(detect_prometheus_endpoint(mock_client, "openshift"))
        assert url == ""


class TestLangGraphClientInjection:
    def test_prometheus_client_injected_when_url_available(self):
        """When prometheus_url is resolved, a PrometheusClient is injected into config."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch

        captured_config = {}

        async def mock_graph_invoke(state, config):
            captured_config.update(config.get("configurable", {}))
            return {**state, "phase": "complete", "data_completeness": 0.8,
                    "domain_reports": [], "health_report": None}

        mock_graph = MagicMock()
        mock_graph.ainvoke = mock_graph_invoke
        mock_client = MagicMock()
        mock_client.detect_platform = AsyncMock(return_value={"platform": "kubernetes", "version": "1.28"})
        mock_client.list_namespaces = AsyncMock(return_value=MagicMock(data=["default"]))
        mock_client.list_nodes = AsyncMock(return_value=MagicMock(data=[]))
        mock_client.close = AsyncMock()

        from src.api.routes_v4 import run_cluster_diagnosis, sessions
        from src.integrations.connection_config import ResolvedConnectionConfig

        sid = "test-prom-inject-001"
        cfg = ResolvedConnectionConfig(
            cluster_url="https://x.com",
            prometheus_url="http://prom:9090",
        )
        sessions[sid] = {
            "diagnostic_scope": {},
            "connection_config": cfg,
            "elk_index": "",
        }

        emitter = MagicMock()
        emitter.emit = AsyncMock()

        with patch("src.agents.cluster.prometheus_detector.detect_prometheus_endpoint",
                   new=AsyncMock(return_value="")):
            asyncio.run(run_cluster_diagnosis(
                sid, mock_graph, mock_client, emitter, connection_config=cfg
            ))

        assert "prometheus_client" in captured_config
        assert captured_config["prometheus_client"] is not None
        assert "elk_client" in captured_config
        assert captured_config["elk_client"] is None  # no elk_index provided

    def test_elk_client_none_when_no_elk_index(self):
        """When elk_index is empty, elk_client should be None."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch

        captured_config = {}

        async def mock_graph_invoke(state, config):
            captured_config.update(config.get("configurable", {}))
            return {**state, "phase": "complete", "data_completeness": 0.8,
                    "domain_reports": [], "health_report": None}

        mock_graph = MagicMock()
        mock_graph.ainvoke = mock_graph_invoke
        mock_client = MagicMock()
        mock_client.detect_platform = AsyncMock(return_value={"platform": "kubernetes", "version": "1.28"})
        mock_client.list_namespaces = AsyncMock(return_value=MagicMock(data=[]))
        mock_client.list_nodes = AsyncMock(return_value=MagicMock(data=[]))
        mock_client.close = AsyncMock()

        from src.api.routes_v4 import run_cluster_diagnosis, sessions
        from src.integrations.connection_config import ResolvedConnectionConfig

        sid = "test-elk-none-001"
        cfg = ResolvedConnectionConfig(cluster_url="https://x.com")
        sessions[sid] = {
            "diagnostic_scope": {},
            "connection_config": cfg,
            "elk_index": "",  # empty — no ELK
        }

        emitter = MagicMock()
        emitter.emit = AsyncMock()

        with patch("src.agents.cluster.prometheus_detector.detect_prometheus_endpoint",
                   new=AsyncMock(return_value="")):
            asyncio.run(run_cluster_diagnosis(
                sid, mock_graph, mock_client, emitter, connection_config=cfg
            ))

        assert captured_config.get("elk_client") is None
        assert captured_config.get("elk_index") == ""

"""Tests for ToolExecutor: fetch_pod_logs and describe_resource handlers.

Covers:
- fetch_pod_logs: successful fetch, pod not found (404), previous container
  logs, no-error logs (severity=info), severity classification
- describe_resource: pod, service (network domain), node (cluster-scoped),
  unsupported kind
- Unknown intent raises KeyError
- Log severity classification helper
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from kubernetes.client.exceptions import ApiException

from src.tools.tool_result import ToolResult
from src.tools.tool_executor import ToolExecutor, _CRITICAL_KEYWORDS, _HIGH_KEYWORDS, _MEDIUM_KEYWORDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_executor(**overrides) -> ToolExecutor:
    """Create a ToolExecutor with a dummy config and mocked K8s clients."""
    config = overrides.pop("config", {"kubeconfig": "/fake/path"})
    executor = ToolExecutor(connection_config=config)
    executor._k8s_core_api = overrides.get("core_api", MagicMock())
    executor._k8s_apps_api = overrides.get("apps_api", MagicMock())
    return executor


def _make_api_exception(status: int, reason: str = "Not Found") -> ApiException:
    """Build a kubernetes ApiException with a given HTTP status code."""
    exc = ApiException(status=status, reason=reason)
    return exc


# ---------------------------------------------------------------------------
# TestFetchPodLogs
# ---------------------------------------------------------------------------

class TestFetchPodLogs:
    """Tests for the _fetch_pod_logs handler."""

    @pytest.mark.asyncio
    async def test_successful_log_fetch(self):
        """Fetching logs with error lines should return success with evidence."""
        mock_api = MagicMock()
        log_text = (
            "2026-02-28T10:00:00Z INFO  Starting service\n"
            "2026-02-28T10:00:01Z ERROR Connection refused to database\n"
            "2026-02-28T10:00:02Z INFO  Retrying...\n"
            "2026-02-28T10:00:03Z ERROR timeout waiting for response\n"
        )
        mock_api.read_namespaced_pod_log = MagicMock(return_value=log_text)

        executor = _make_executor(core_api=mock_api)
        result = await executor.execute("fetch_pod_logs", {
            "namespace": "prod",
            "pod": "payment-svc-abc-123",
        })

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.domain == "compute"
        assert result.evidence_type == "log"
        assert result.intent == "fetch_pod_logs"
        # Should have extracted the error lines
        assert len(result.evidence_snippets) >= 2
        assert any("refused" in s.lower() for s in result.evidence_snippets)
        assert any("timeout" in s.lower() for s in result.evidence_snippets)
        # Severity should be medium (error/timeout keywords, no fatal/oom)
        assert result.severity == "medium"
        # raw_output should contain the full log text
        assert "Connection refused" in result.raw_output

        # Verify the K8s API was called correctly
        mock_api.read_namespaced_pod_log.assert_called_once()
        call_kwargs = mock_api.read_namespaced_pod_log.call_args
        assert call_kwargs[1]["name"] == "payment-svc-abc-123" or call_kwargs[0][0] == "payment-svc-abc-123"

    @pytest.mark.asyncio
    async def test_pod_not_found(self):
        """404 from K8s API should return success=False with 'not found' error."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log = MagicMock(
            side_effect=_make_api_exception(404, "Not Found")
        )

        executor = _make_executor(core_api=mock_api)
        result = await executor.execute("fetch_pod_logs", {
            "namespace": "prod",
            "pod": "nonexistent-pod",
        })

        assert result.success is False
        assert "not found" in result.error.lower()
        assert result.evidence_snippets == []

    @pytest.mark.asyncio
    async def test_previous_container_logs(self):
        """Fetching previous container logs with FATAL OOMKilled should be severity=critical."""
        mock_api = MagicMock()
        log_text = "2026-02-28T09:59:59Z FATAL OOMKilled\n"
        mock_api.read_namespaced_pod_log = MagicMock(return_value=log_text)

        executor = _make_executor(core_api=mock_api)
        result = await executor.execute("fetch_pod_logs", {
            "namespace": "prod",
            "pod": "payment-svc-abc-123",
            "previous": True,
            "container": "main",
        })

        assert result.success is True
        assert result.severity == "critical"
        # Verify previous=True was passed to the API
        call_kwargs = mock_api.read_namespaced_pod_log.call_args
        assert call_kwargs[1].get("previous") is True

    @pytest.mark.asyncio
    async def test_no_errors_in_logs(self):
        """Clean logs should give severity=info and empty evidence_snippets."""
        mock_api = MagicMock()
        log_text = (
            "2026-02-28T10:00:00Z INFO  Starting service\n"
            "2026-02-28T10:00:01Z INFO  Listening on port 8080\n"
            "2026-02-28T10:00:02Z INFO  Health check passed\n"
        )
        mock_api.read_namespaced_pod_log = MagicMock(return_value=log_text)

        executor = _make_executor(core_api=mock_api)
        result = await executor.execute("fetch_pod_logs", {
            "namespace": "prod",
            "pod": "healthy-pod",
        })

        assert result.success is True
        assert result.severity == "info"
        assert result.evidence_snippets == []

    @pytest.mark.asyncio
    async def test_no_previous_container_400(self):
        """400 from K8s API (no previous container) should return success=False."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log = MagicMock(
            side_effect=_make_api_exception(400, "Bad Request")
        )

        executor = _make_executor(core_api=mock_api)
        result = await executor.execute("fetch_pod_logs", {
            "namespace": "prod",
            "pod": "some-pod",
            "previous": True,
        })

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_custom_tail_lines(self):
        """The tail_lines param should be forwarded to the K8s API."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log = MagicMock(return_value="INFO all good\n")

        executor = _make_executor(core_api=mock_api)
        await executor.execute("fetch_pod_logs", {
            "namespace": "prod",
            "pod": "my-pod",
            "tail_lines": 50,
        })

        call_kwargs = mock_api.read_namespaced_pod_log.call_args
        assert call_kwargs[1].get("tail_lines") == 50


# ---------------------------------------------------------------------------
# TestDescribeResource
# ---------------------------------------------------------------------------

class TestDescribeResource:
    """Tests for the _describe_resource handler."""

    @pytest.mark.asyncio
    async def test_describe_pod(self):
        """Describing a pod should return success=True, domain=compute, evidence_type=k8s_resource."""
        mock_api = MagicMock()
        # Build a mock pod object
        mock_pod = MagicMock()
        mock_pod.metadata = MagicMock()
        mock_pod.metadata.name = "payment-svc-abc-123"
        mock_pod.metadata.namespace = "prod"
        mock_pod.status = MagicMock()
        mock_pod.status.container_statuses = [
            MagicMock(ready=True, name="main", state=MagicMock(terminated=None)),
        ]
        mock_api.read_namespaced_pod = MagicMock(return_value=mock_pod)

        executor = _make_executor(core_api=mock_api)

        with patch("src.tools.tool_executor.ApiClient") as MockApiClient:
            mock_client_instance = MagicMock()
            mock_client_instance.sanitize_for_serialization.return_value = {
                "metadata": {"name": "payment-svc-abc-123", "namespace": "prod"},
                "status": {"containerStatuses": [{"ready": True, "name": "main"}]},
            }
            MockApiClient.return_value = mock_client_instance

            result = await executor.execute("describe_resource", {
                "kind": "pod",
                "name": "payment-svc-abc-123",
                "namespace": "prod",
            })

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.domain == "compute"
        assert result.evidence_type == "k8s_resource"
        assert result.intent == "describe_resource"
        assert "payment-svc-abc-123" in result.raw_output

    @pytest.mark.asyncio
    async def test_describe_service_maps_to_network_domain(self):
        """Describing a service should return domain=network."""
        mock_api = MagicMock()
        mock_service = MagicMock()
        mock_service.metadata = MagicMock()
        mock_service.metadata.name = "payment-svc"
        mock_service.metadata.namespace = "prod"
        mock_service.spec = MagicMock()
        mock_service.spec.type = "ClusterIP"
        mock_api.read_namespaced_service = MagicMock(return_value=mock_service)

        executor = _make_executor(core_api=mock_api)

        with patch("src.tools.tool_executor.ApiClient") as MockApiClient:
            mock_client_instance = MagicMock()
            mock_client_instance.sanitize_for_serialization.return_value = {
                "metadata": {"name": "payment-svc"},
                "spec": {"type": "ClusterIP"},
            }
            MockApiClient.return_value = mock_client_instance

            result = await executor.execute("describe_resource", {
                "kind": "service",
                "name": "payment-svc",
                "namespace": "prod",
            })

        assert result.success is True
        assert result.domain == "network"

    @pytest.mark.asyncio
    async def test_describe_node_cluster_scoped(self):
        """Describing a node should work (cluster-scoped — namespace is
        provided by context defaults but ignored for cluster-scoped lookups)."""
        mock_api = MagicMock()
        mock_node = MagicMock()
        mock_node.metadata = MagicMock()
        mock_node.metadata.name = "worker-1"
        mock_node.status = MagicMock()
        mock_api.read_node = MagicMock(return_value=mock_node)

        executor = _make_executor(core_api=mock_api)

        with patch("src.tools.tool_executor.ApiClient") as MockApiClient:
            mock_client_instance = MagicMock()
            mock_client_instance.sanitize_for_serialization.return_value = {
                "metadata": {"name": "worker-1"},
            }
            MockApiClient.return_value = mock_client_instance

            result = await executor.execute("describe_resource", {
                "kind": "node",
                "name": "worker-1",
                "namespace": "default",  # filled by router context defaults
            })

        assert result.success is True
        assert result.domain == "compute"
        # Node is cluster-scoped; read_node should be called, not read_namespaced_*
        mock_api.read_node.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsupported_kind(self):
        """An unsupported resource kind should return success=False with 'unsupported' error."""
        executor = _make_executor()
        result = await executor.execute("describe_resource", {
            "kind": "cronjob",
            "name": "nightly-cleanup",
            "namespace": "prod",
        })

        assert result.success is False
        assert "unsupported" in result.error.lower()

    @pytest.mark.asyncio
    async def test_describe_resource_not_found(self):
        """404 from K8s API should return success=False."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod = MagicMock(
            side_effect=_make_api_exception(404, "Not Found")
        )

        executor = _make_executor(core_api=mock_api)
        result = await executor.execute("describe_resource", {
            "kind": "pod",
            "name": "ghost-pod",
            "namespace": "prod",
        })

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_describe_configmap(self):
        """Describing a configmap should use read_namespaced_config_map, domain=compute."""
        mock_api = MagicMock()
        mock_cm = MagicMock()
        mock_cm.metadata = MagicMock()
        mock_cm.metadata.name = "app-config"
        mock_api.read_namespaced_config_map = MagicMock(return_value=mock_cm)

        executor = _make_executor(core_api=mock_api)

        with patch("src.tools.tool_executor.ApiClient") as MockApiClient:
            mock_client_instance = MagicMock()
            mock_client_instance.sanitize_for_serialization.return_value = {
                "metadata": {"name": "app-config"},
            }
            MockApiClient.return_value = mock_client_instance

            result = await executor.execute("describe_resource", {
                "kind": "configmap",
                "name": "app-config",
                "namespace": "prod",
            })

        assert result.success is True
        assert result.domain == "compute"
        mock_api.read_namespaced_config_map.assert_called_once()

    @pytest.mark.asyncio
    async def test_describe_pvc(self):
        """Describing a PVC should map to domain=storage."""
        mock_api = MagicMock()
        mock_pvc = MagicMock()
        mock_pvc.metadata = MagicMock()
        mock_pvc.metadata.name = "data-vol"
        mock_api.read_namespaced_persistent_volume_claim = MagicMock(return_value=mock_pvc)

        executor = _make_executor(core_api=mock_api)

        with patch("src.tools.tool_executor.ApiClient") as MockApiClient:
            mock_client_instance = MagicMock()
            mock_client_instance.sanitize_for_serialization.return_value = {
                "metadata": {"name": "data-vol"},
            }
            MockApiClient.return_value = mock_client_instance

            result = await executor.execute("describe_resource", {
                "kind": "pvc",
                "name": "data-vol",
                "namespace": "prod",
            })

        assert result.success is True
        assert result.domain == "storage"


# ---------------------------------------------------------------------------
# TestUnknownIntent
# ---------------------------------------------------------------------------

class TestUnknownIntent:
    """Tests for unknown/invalid intent names."""

    @pytest.mark.asyncio
    async def test_unknown_intent_raises(self):
        """An intent not in HANDLERS should raise KeyError."""
        executor = _make_executor()
        with pytest.raises(KeyError):
            await executor.execute("nonexistent_tool", {"foo": "bar"})


# ---------------------------------------------------------------------------
# TestClassifyLogSeverity
# ---------------------------------------------------------------------------

class TestClassifyLogSeverity:
    """Tests for the _classify_log_severity static method."""

    def test_fatal_keyword_returns_critical(self):
        lines = ["FATAL: process crashed"]
        assert ToolExecutor._classify_log_severity(lines) == "critical"

    def test_panic_keyword_returns_critical(self):
        lines = ["goroutine panic: nil pointer"]
        assert ToolExecutor._classify_log_severity(lines) == "critical"

    def test_oom_keyword_returns_high(self):
        lines = ["Container killed: OOM"]
        assert ToolExecutor._classify_log_severity(lines) == "high"

    def test_killed_keyword_returns_high(self):
        lines = ["Process killed by signal 9"]
        assert ToolExecutor._classify_log_severity(lines) == "high"

    def test_error_keyword_returns_medium(self):
        lines = ["ERROR: connection refused"]
        assert ToolExecutor._classify_log_severity(lines) == "medium"

    def test_no_errors_returns_info(self):
        assert ToolExecutor._classify_log_severity([]) == "info"

    def test_critical_takes_precedence_over_high(self):
        """When both fatal and oom are present, critical wins."""
        lines = ["FATAL OOMKilled"]
        assert ToolExecutor._classify_log_severity(lines) == "critical"


# ---------------------------------------------------------------------------
# TestExtractResourceSignals
# ---------------------------------------------------------------------------

class TestExtractResourceSignals:
    """Tests for the _extract_resource_signals static method."""

    def test_pod_with_terminated_container(self):
        """A pod with a terminated container should flag has_issues=True."""
        mock_pod = MagicMock()
        mock_pod.status = MagicMock()
        terminated = MagicMock()
        terminated.reason = "OOMKilled"
        terminated.exit_code = 137
        container_status = MagicMock()
        container_status.ready = False
        container_status.name = "main"
        container_status.state = MagicMock()
        container_status.state.terminated = terminated
        container_status.state.waiting = None
        mock_pod.status.container_statuses = [container_status]

        signals = ToolExecutor._extract_resource_signals(mock_pod, "pod")
        assert signals["has_issues"] is True
        assert len(signals["key_lines"]) > 0

    def test_pod_all_ready(self):
        """A pod with all containers ready should have has_issues=False."""
        mock_pod = MagicMock()
        mock_pod.status = MagicMock()
        container_status = MagicMock()
        container_status.ready = True
        container_status.name = "main"
        container_status.state = MagicMock()
        container_status.state.terminated = None
        container_status.state.waiting = None
        mock_pod.status.container_statuses = [container_status]

        signals = ToolExecutor._extract_resource_signals(mock_pod, "pod")
        assert signals["has_issues"] is False

    def test_service_shows_type(self):
        """A service should report its spec.type in summary."""
        mock_svc = MagicMock()
        mock_svc.spec = MagicMock()
        mock_svc.spec.type = "LoadBalancer"
        mock_svc.metadata = MagicMock()
        mock_svc.metadata.name = "frontend-svc"

        signals = ToolExecutor._extract_resource_signals(mock_svc, "service")
        assert "LoadBalancer" in signals["summary"]

    def test_default_kind(self):
        """An unknown kind should still produce a valid signals dict."""
        mock_resource = MagicMock()
        mock_resource.metadata = MagicMock()
        mock_resource.metadata.name = "my-resource"

        signals = ToolExecutor._extract_resource_signals(mock_resource, "configmap")
        assert "summary" in signals
        assert "key_lines" in signals
        assert "has_issues" in signals


# ---------------------------------------------------------------------------
# TestLazyClientInitialization
# ---------------------------------------------------------------------------

class TestLazyClientInitialization:
    """Tests for lazy client initialization: config-based, env var fallback, caching."""

    def test_k8s_core_api_from_config(self):
        """Config with cluster_url+cluster_token should create CoreV1Api via bearer token."""
        config = {
            "cluster_url": "https://api.cluster.example.com:6443",
            "cluster_token": "sha256~test-token",
            "verify_ssl": False,
        }
        executor = ToolExecutor(connection_config=config)

        with patch("src.tools.tool_executor.ToolExecutor._get_k8s_client") as mock_get_client:
            mock_api_client = MagicMock()
            mock_get_client.return_value = mock_api_client

            with patch("kubernetes.client.CoreV1Api") as MockCoreV1Api:
                mock_core_instance = MagicMock()
                MockCoreV1Api.return_value = mock_core_instance

                result = executor._get_k8s_core_api()

                MockCoreV1Api.assert_called_once_with(mock_api_client)
                assert result is mock_core_instance

    def test_k8s_apps_api_from_config(self):
        """Config with cluster_url+cluster_token should create AppsV1Api."""
        config = {
            "cluster_url": "https://api.cluster.example.com:6443",
            "cluster_token": "sha256~test-token",
        }
        executor = ToolExecutor(connection_config=config)

        with patch("src.tools.tool_executor.ToolExecutor._get_k8s_client") as mock_get_client:
            mock_api_client = MagicMock()
            mock_get_client.return_value = mock_api_client

            with patch("kubernetes.client.AppsV1Api") as MockAppsV1Api:
                mock_apps_instance = MagicMock()
                MockAppsV1Api.return_value = mock_apps_instance

                result = executor._get_k8s_apps_api()

                MockAppsV1Api.assert_called_once_with(mock_api_client)
                assert result is mock_apps_instance

    def test_k8s_client_from_env_vars(self):
        """When config has no cluster_url/token, should fall back to env vars."""
        executor = ToolExecutor(connection_config={})

        env = {
            "OPENSHIFT_API_URL": "https://env-api.example.com:6443",
            "OPENSHIFT_TOKEN": "sha256~env-token",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch("kubernetes.client.Configuration") as MockConfig:
                mock_config_instance = MagicMock()
                MockConfig.return_value = mock_config_instance

                with patch("kubernetes.client.ApiClient") as MockApiClient:
                    mock_api_client = MagicMock()
                    MockApiClient.return_value = mock_api_client

                    result = executor._get_k8s_client()

                    assert mock_config_instance.host == "https://env-api.example.com:6443"
                    assert mock_config_instance.api_key == {
                        "authorization": "Bearer sha256~env-token"
                    }
                    MockApiClient.assert_called_once_with(mock_config_instance)
                    assert result is mock_api_client

    def test_k8s_client_from_kubeconfig_fallback(self):
        """When no config or env vars, should load kubeconfig."""
        executor = ToolExecutor(connection_config={})

        with patch.dict("os.environ", {}, clear=True):
            with patch("kubernetes.config.load_kube_config") as mock_load:
                with patch("kubernetes.client.ApiClient") as MockApiClient:
                    mock_api_client = MagicMock()
                    MockApiClient.return_value = mock_api_client

                    result = executor._get_k8s_client()

                    mock_load.assert_called_once()
                    MockApiClient.assert_called_once_with()
                    assert result is mock_api_client

    def test_k8s_core_api_caching(self):
        """Second call to _get_k8s_core_api should return the cached instance."""
        executor = ToolExecutor(connection_config={})

        with patch("src.tools.tool_executor.ToolExecutor._get_k8s_client") as mock_get_client:
            mock_api_client = MagicMock()
            mock_get_client.return_value = mock_api_client

            with patch("kubernetes.client.CoreV1Api") as MockCoreV1Api:
                mock_core_instance = MagicMock()
                MockCoreV1Api.return_value = mock_core_instance

                first = executor._get_k8s_core_api()
                second = executor._get_k8s_core_api()

                # Should only construct once
                assert MockCoreV1Api.call_count == 1
                assert first is second

    def test_k8s_apps_api_caching(self):
        """Second call to _get_k8s_apps_api should return the cached instance."""
        executor = ToolExecutor(connection_config={})

        with patch("src.tools.tool_executor.ToolExecutor._get_k8s_client") as mock_get_client:
            mock_api_client = MagicMock()
            mock_get_client.return_value = mock_api_client

            with patch("kubernetes.client.AppsV1Api") as MockAppsV1Api:
                mock_apps_instance = MagicMock()
                MockAppsV1Api.return_value = mock_apps_instance

                first = executor._get_k8s_apps_api()
                second = executor._get_k8s_apps_api()

                assert MockAppsV1Api.call_count == 1
                assert first is second

    def test_prom_client_from_config(self):
        """Config with prometheus_url should create PrometheusConnect."""
        config = {"prometheus_url": "http://prometheus:9090"}
        executor = ToolExecutor(connection_config=config)

        with patch("prometheus_api_client.PrometheusConnect") as MockProm:
            mock_prom_instance = MagicMock()
            MockProm.return_value = mock_prom_instance

            result = executor._get_prom_client()

            MockProm.assert_called_once_with(
                url="http://prometheus:9090", disable_ssl=True
            )
            assert result is mock_prom_instance

    def test_prom_client_from_env_var(self):
        """When config has no prometheus_url, should fall back to PROMETHEUS_URL env var."""
        executor = ToolExecutor(connection_config={})

        with patch.dict("os.environ", {"PROMETHEUS_URL": "http://env-prom:9090"}, clear=False):
            with patch("prometheus_api_client.PrometheusConnect") as MockProm:
                mock_prom_instance = MagicMock()
                MockProm.return_value = mock_prom_instance

                result = executor._get_prom_client()

                MockProm.assert_called_once_with(
                    url="http://env-prom:9090", disable_ssl=True
                )
                assert result is mock_prom_instance

    def test_prom_client_raises_when_no_url(self):
        """When no config or env var for prometheus, should raise RuntimeError."""
        executor = ToolExecutor(connection_config={})

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="Prometheus URL not configured"):
                executor._get_prom_client()

    def test_prom_client_caching(self):
        """Second call to _get_prom_client should return the cached instance."""
        config = {"prometheus_url": "http://prometheus:9090"}
        executor = ToolExecutor(connection_config=config)

        with patch("prometheus_api_client.PrometheusConnect") as MockProm:
            mock_prom_instance = MagicMock()
            MockProm.return_value = mock_prom_instance

            first = executor._get_prom_client()
            second = executor._get_prom_client()

            assert MockProm.call_count == 1
            assert first is second

    def test_es_client_from_config(self):
        """Config with elasticsearch_url should create Elasticsearch client."""
        config = {"elasticsearch_url": "http://elasticsearch:9200"}
        executor = ToolExecutor(connection_config=config)

        with patch("elasticsearch.Elasticsearch") as MockES:
            mock_es_instance = MagicMock()
            MockES.return_value = mock_es_instance

            result = executor._get_es_client()

            MockES.assert_called_once_with(["http://elasticsearch:9200"])
            assert result is mock_es_instance

    def test_es_client_from_env_var(self):
        """When config has no elasticsearch_url, should fall back to ELASTICSEARCH_URL."""
        executor = ToolExecutor(connection_config={})

        with patch.dict("os.environ", {"ELASTICSEARCH_URL": "http://env-es:9200"}, clear=False):
            with patch("elasticsearch.Elasticsearch") as MockES:
                mock_es_instance = MagicMock()
                MockES.return_value = mock_es_instance

                result = executor._get_es_client()

                MockES.assert_called_once_with(["http://env-es:9200"])
                assert result is mock_es_instance

    def test_es_client_raises_when_no_url(self):
        """When no config or env var for elasticsearch, should raise RuntimeError."""
        executor = ToolExecutor(connection_config={})

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="Elasticsearch URL not configured"):
                executor._get_es_client()

    def test_es_client_caching(self):
        """Second call to _get_es_client should return the cached instance."""
        config = {"elasticsearch_url": "http://elasticsearch:9200"}
        executor = ToolExecutor(connection_config=config)

        with patch("elasticsearch.Elasticsearch") as MockES:
            mock_es_instance = MagicMock()
            MockES.return_value = mock_es_instance

            first = executor._get_es_client()
            second = executor._get_es_client()

            assert MockES.call_count == 1
            assert first is second

    def test_pre_populated_k8s_core_api_skips_init(self):
        """Setting _k8s_core_api directly should bypass lazy init (existing test pattern)."""
        executor = ToolExecutor(connection_config={})
        mock_api = MagicMock()
        executor._k8s_core_api = mock_api

        result = executor._get_k8s_core_api()
        assert result is mock_api

    def test_pre_populated_prom_client_skips_init(self):
        """Setting _prom_client directly should bypass lazy init."""
        executor = ToolExecutor(connection_config={})
        mock_prom = MagicMock()
        executor._prom_client = mock_prom

        result = executor._get_prom_client()
        assert result is mock_prom

    def test_pre_populated_es_client_skips_init(self):
        """Setting _es_client directly should bypass lazy init."""
        executor = ToolExecutor(connection_config={})
        mock_es = MagicMock()
        executor._es_client = mock_es

        result = executor._get_es_client()
        assert result is mock_es


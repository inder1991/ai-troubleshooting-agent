"""Tests for ToolExecutor Phase 1 handlers: query_prometheus, search_logs,
check_pod_status, get_events.

Covers:
- query_prometheus: successful query with stats, empty result, domain inference
  (network, control_plane, compute), client error
- search_logs: successful search, no results, ES client error
- check_pod_status: healthy pods, unhealthy (CrashLoopBackOff), label_selector
- get_events: warning events, no events, time-window filtering
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

from src.tools.tool_executor import ToolExecutor
from src.tools.tool_result import ToolResult


def _make_executor(**overrides) -> ToolExecutor:
    """Create a ToolExecutor with a dummy config and mocked clients."""
    config = overrides.pop("config", {"kubeconfig": "/fake/path"})
    executor = ToolExecutor(connection_config=config)
    executor._k8s_core_api = overrides.get("core_api", MagicMock())
    executor._k8s_apps_api = overrides.get("apps_api", MagicMock())
    executor._prom_client = overrides.get("prom_client", MagicMock())
    executor._es_client = overrides.get("es_client", MagicMock())
    return executor


class TestQueryPrometheus:
    @pytest.mark.asyncio
    async def test_successful_query(self):
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(return_value={
            "data": {
                "resultType": "matrix",
                "result": [{
                    "metric": {"__name__": "container_memory_working_set_bytes", "pod": "auth-5b6q"},
                    "values": [[1709100000, "104857600"], [1709100060, "209715200"], [1709100120, "524288000"]],
                }],
            },
        })

        executor = _make_executor(prom_client=mock_prom)
        result = await executor.execute("query_prometheus", {
            "query": "container_memory_working_set_bytes{pod='auth-5b6q'}",
            "range_minutes": 60,
        })

        assert result.success is True
        assert result.evidence_type == "metric"
        assert result.domain == "compute"
        assert result.metadata["series_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_result(self):
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(return_value={"data": {"result": []}})

        executor = _make_executor(prom_client=mock_prom)
        result = await executor.execute("query_prometheus", {
            "query": "nonexistent_metric",
        })
        assert result.success is True
        assert "no data" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_network_domain_inference(self):
        """PromQL containing 'coredns' should infer domain=network."""
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(return_value={
            "data": {"result": [{"metric": {}, "values": [[1, "1"]]}]},
        })

        executor = _make_executor(prom_client=mock_prom)
        result = await executor.execute("query_prometheus", {
            "query": "coredns_dns_request_count_total",
        })
        assert result.domain == "network"

    @pytest.mark.asyncio
    async def test_control_plane_domain_inference(self):
        """PromQL containing 'apiserver' should infer domain=control_plane."""
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(return_value={
            "data": {"result": [{"metric": {}, "values": [[1, "1"]]}]},
        })

        executor = _make_executor(prom_client=mock_prom)
        result = await executor.execute("query_prometheus", {
            "query": "apiserver_request_total",
        })
        assert result.domain == "control_plane"

    @pytest.mark.asyncio
    async def test_prom_client_error(self):
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(side_effect=Exception("Connection refused"))

        executor = _make_executor(prom_client=mock_prom)
        result = await executor.execute("query_prometheus", {
            "query": "up",
        })
        assert result.success is False
        assert result.error is not None


class TestSearchLogs:
    @pytest.mark.asyncio
    async def test_successful_search(self):
        mock_es = MagicMock()
        mock_es.search = MagicMock(return_value={
            "hits": {
                "total": {"value": 3},
                "hits": [
                    {"_source": {"@timestamp": "2026-02-28T10:00:00Z", "message": "Connection timeout", "level": "ERROR"}},
                    {"_source": {"@timestamp": "2026-02-28T10:00:01Z", "message": "Retrying", "level": "WARN"}},
                    {"_source": {"@timestamp": "2026-02-28T10:00:02Z", "message": "Connection refused", "level": "ERROR"}},
                ],
            },
        })

        executor = _make_executor(es_client=mock_es)
        result = await executor.execute("search_logs", {
            "query": "Connection",
            "index": "app-logs-*",
            "since_minutes": 60,
        })

        assert result.success is True
        assert result.evidence_type == "log"
        assert result.domain == "unknown"
        assert result.metadata["total"] == 3

    @pytest.mark.asyncio
    async def test_no_results(self):
        mock_es = MagicMock()
        mock_es.search = MagicMock(return_value={"hits": {"total": {"value": 0}, "hits": []}})

        executor = _make_executor(es_client=mock_es)
        result = await executor.execute("search_logs", {"query": "nonexistent"})
        assert result.success is True
        assert result.metadata["total"] == 0

    @pytest.mark.asyncio
    async def test_es_client_error(self):
        mock_es = MagicMock()
        mock_es.search = MagicMock(side_effect=Exception("ES connection error"))

        executor = _make_executor(es_client=mock_es)
        result = await executor.execute("search_logs", {"query": "error"})
        assert result.success is False
        assert result.error is not None


class TestCheckPodStatus:
    @pytest.mark.asyncio
    async def test_healthy_pods(self):
        mock_api = MagicMock()
        mock_pod = MagicMock()
        mock_pod.metadata.name = "auth-5b6q"
        mock_pod.status.phase = "Running"
        mock_cs = MagicMock(ready=True, restart_count=0, name="auth")
        mock_cs.state = MagicMock()
        mock_cs.state.waiting = None
        mock_cs.state.terminated = None
        mock_pod.status.container_statuses = [mock_cs]

        mock_api.list_namespaced_pod = MagicMock(return_value=MagicMock(items=[mock_pod]))
        executor = _make_executor(core_api=mock_api)

        result = await executor.execute("check_pod_status", {"namespace": "payment-api"})
        assert result.success is True
        assert result.metadata["unhealthy"] == 0
        assert result.severity == "info"

    @pytest.mark.asyncio
    async def test_unhealthy_pod_crashloop(self):
        mock_api = MagicMock()
        mock_pod = MagicMock()
        mock_pod.metadata.name = "auth-crash"
        mock_pod.status.phase = "CrashLoopBackOff"
        mock_cs = MagicMock(ready=False, restart_count=5, name="auth")
        mock_cs.state = MagicMock()
        mock_cs.state.waiting = MagicMock()
        mock_cs.state.waiting.reason = "CrashLoopBackOff"
        mock_cs.state.terminated = None
        mock_pod.status.container_statuses = [mock_cs]

        mock_api.list_namespaced_pod = MagicMock(return_value=MagicMock(items=[mock_pod]))
        executor = _make_executor(core_api=mock_api)

        result = await executor.execute("check_pod_status", {"namespace": "payment-api"})
        assert result.severity == "critical"
        assert result.metadata["unhealthy"] == 1

    @pytest.mark.asyncio
    async def test_label_selector(self):
        mock_api = MagicMock()
        mock_api.list_namespaced_pod = MagicMock(return_value=MagicMock(items=[]))
        executor = _make_executor(core_api=mock_api)

        await executor.execute("check_pod_status", {
            "namespace": "payment-api",
            "label_selector": "app=auth",
        })

        call_kwargs = mock_api.list_namespaced_pod.call_args
        assert call_kwargs[1].get("label_selector") == "app=auth" or \
               (len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "app=auth")


class TestGetEvents:
    @pytest.mark.asyncio
    async def test_warning_events(self):
        mock_api = MagicMock()
        mock_event = MagicMock()
        mock_event.last_timestamp = datetime.now(timezone.utc)
        mock_event.type = "Warning"
        mock_event.reason = "OOMKilling"
        mock_event.message = "Pod exceeded memory limit"
        mock_event.count = 3
        mock_event.involved_object = MagicMock()
        mock_event.involved_object.name = "auth-5b6q"
        mock_event.involved_object.kind = "Pod"

        mock_api.list_namespaced_event = MagicMock(return_value=MagicMock(items=[mock_event]))
        executor = _make_executor(core_api=mock_api)

        result = await executor.execute("get_events", {
            "namespace": "payment-api",
            "since_minutes": 60,
        })

        assert result.success is True
        assert result.evidence_type == "k8s_event"
        assert result.domain == "compute"
        assert result.metadata["warning_count"] == 1

    @pytest.mark.asyncio
    async def test_no_events(self):
        mock_api = MagicMock()
        mock_api.list_namespaced_event = MagicMock(return_value=MagicMock(items=[]))
        executor = _make_executor(core_api=mock_api)

        result = await executor.execute("get_events", {
            "namespace": "payment-api",
        })

        assert result.success is True
        assert result.metadata["warning_count"] == 0

    @pytest.mark.asyncio
    async def test_events_filtered_by_time(self):
        """Events older than since_minutes should be filtered out."""
        mock_api = MagicMock()
        old_event = MagicMock()
        old_event.last_timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
        old_event.type = "Warning"
        old_event.reason = "OldWarning"
        old_event.message = "Old event"
        old_event.count = 1
        old_event.involved_object = MagicMock()
        old_event.involved_object.name = "old-pod"
        old_event.involved_object.kind = "Pod"

        recent_event = MagicMock()
        recent_event.last_timestamp = datetime.now(timezone.utc) - timedelta(minutes=5)
        recent_event.type = "Warning"
        recent_event.reason = "RecentWarning"
        recent_event.message = "Recent event"
        recent_event.count = 1
        recent_event.involved_object = MagicMock()
        recent_event.involved_object.name = "recent-pod"
        recent_event.involved_object.kind = "Pod"

        mock_api.list_namespaced_event = MagicMock(return_value=MagicMock(items=[old_event, recent_event]))
        executor = _make_executor(core_api=mock_api)

        result = await executor.execute("get_events", {
            "namespace": "payment-api",
            "since_minutes": 60,
        })

        # Only the recent event should be included
        assert result.metadata["warning_count"] == 1

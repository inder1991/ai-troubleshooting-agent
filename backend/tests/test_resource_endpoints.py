"""Tests for ToolExecutor resource accessor methods (Surgical Telescope).

Covers:
- get_resource_yaml: successful pod read, unsupported kind, API failure
- get_resource_events: successful event listing with field_selector
- get_pod_logs: successful log read, container kwarg passthrough, tail_lines clamping
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.tools.tool_executor import ToolExecutor, _KIND_TO_API_METHOD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_executor(**overrides) -> ToolExecutor:
    """Create a ToolExecutor with a dummy config and mocked K8s clients."""
    config = overrides.pop("config", {"kubeconfig": "/fake/path"})
    executor = ToolExecutor(connection_config=config)
    executor._k8s_core_api = overrides.get("core_api", MagicMock())
    executor._k8s_apps_api = overrides.get("apps_api", MagicMock())
    executor._k8s_networking_api = overrides.get("networking_api", MagicMock())
    return executor


def _make_pod_resource():
    """Create a mock K8s pod resource object."""
    pod = MagicMock()
    pod.metadata = MagicMock()
    pod.metadata.name = "payment-svc-abc-123"
    pod.metadata.namespace = "prod"
    pod.spec = MagicMock()
    pod.status = MagicMock()
    pod.status.phase = "Running"
    return pod


# ---------------------------------------------------------------------------
# TestGetResourceYaml
# ---------------------------------------------------------------------------

class TestGetResourceYaml:
    """Tests for the get_resource_yaml public method."""

    def test_get_resource_yaml_pod(self):
        """Reading a pod resource should return a YAML (JSON) string."""
        mock_api = MagicMock()
        pod = _make_pod_resource()
        mock_api.read_namespaced_pod = MagicMock(return_value=pod)

        executor = _make_executor(core_api=mock_api)

        # Mock ApiClient().sanitize_for_serialization to return a dict
        with patch("src.tools.tool_executor.ApiClient") as MockApiClient:
            mock_instance = MagicMock()
            mock_instance.sanitize_for_serialization.return_value = {
                "kind": "Pod",
                "metadata": {"name": "payment-svc-abc-123", "namespace": "prod"},
                "status": {"phase": "Running"},
            }
            MockApiClient.return_value = mock_instance

            result = executor.get_resource_yaml("pod", "payment-svc-abc-123", "prod")

        assert "error" not in result or result.get("error") is None
        assert "yaml" in result
        parsed = json.loads(result["yaml"])
        assert parsed["kind"] == "Pod"
        assert parsed["metadata"]["name"] == "payment-svc-abc-123"

        # Verify the K8s API was called with correct args
        mock_api.read_namespaced_pod.assert_called_once_with(
            name="payment-svc-abc-123", namespace="prod",
        )

    def test_get_resource_yaml_deployment(self):
        """Reading a deployment should use the apps API client."""
        mock_apps_api = MagicMock()
        deploy = MagicMock()
        mock_apps_api.read_namespaced_deployment = MagicMock(return_value=deploy)

        executor = _make_executor(apps_api=mock_apps_api)

        with patch("src.tools.tool_executor.ApiClient") as MockApiClient:
            mock_instance = MagicMock()
            mock_instance.sanitize_for_serialization.return_value = {
                "kind": "Deployment",
                "metadata": {"name": "web-deploy"},
            }
            MockApiClient.return_value = mock_instance

            result = executor.get_resource_yaml("deployment", "web-deploy", "default")

        assert "yaml" in result
        assert "error" not in result or result.get("error") is None
        mock_apps_api.read_namespaced_deployment.assert_called_once_with(
            name="web-deploy", namespace="default",
        )

    def test_get_resource_yaml_unsupported_kind(self):
        """Requesting an unsupported kind should return an error."""
        executor = _make_executor()
        result = executor.get_resource_yaml("cronjob", "my-job", "default")

        assert "error" in result
        assert "Unsupported resource kind" in result["error"]
        assert "cronjob" in result["error"]

    def test_get_resource_yaml_api_failure(self):
        """When the K8s API raises, return a generic error (no internals)."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod = MagicMock(
            side_effect=Exception("connection timeout to api-server"),
        )

        executor = _make_executor(core_api=mock_api)
        result = executor.get_resource_yaml("pod", "my-pod", "default")

        assert "error" in result
        assert result["error"] == "Failed to fetch resource"
        # Must NOT leak internal details
        assert "connection timeout" not in result.get("error", "")
        assert "yaml" not in result or result.get("yaml") is None

    def test_get_resource_yaml_node_cluster_scoped(self):
        """Node is cluster-scoped — should not pass namespace."""
        mock_api = MagicMock()
        node = MagicMock()
        mock_api.read_node = MagicMock(return_value=node)

        executor = _make_executor(core_api=mock_api)

        with patch("src.tools.tool_executor.ApiClient") as MockApiClient:
            mock_instance = MagicMock()
            mock_instance.sanitize_for_serialization.return_value = {"kind": "Node"}
            MockApiClient.return_value = mock_instance

            result = executor.get_resource_yaml("node", "worker-1", "default")

        assert "yaml" in result
        # Cluster-scoped: called with name only, no namespace
        mock_api.read_node.assert_called_once_with(name="worker-1")


# ---------------------------------------------------------------------------
# TestGetResourceEvents
# ---------------------------------------------------------------------------

class TestGetResourceEvents:
    """Tests for the get_resource_events public method."""

    def test_get_resource_events(self):
        """Listing events should return structured event dicts."""
        mock_api = MagicMock()

        event1 = MagicMock()
        event1.type = "Warning"
        event1.reason = "BackOff"
        event1.message = "Back-off restarting failed container"
        event1.count = 5
        event1.first_timestamp = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
        event1.last_timestamp = datetime(2026, 3, 1, 10, 5, 0, tzinfo=timezone.utc)
        event1.source = MagicMock()
        event1.source.component = "kubelet"

        event2 = MagicMock()
        event2.type = "Normal"
        event2.reason = "Pulling"
        event2.message = "Pulling image nginx:latest"
        event2.count = 1
        event2.first_timestamp = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        event2.last_timestamp = datetime(2026, 3, 1, 9, 0, 5, tzinfo=timezone.utc)
        event2.source = MagicMock()
        event2.source.component = "kubelet"

        mock_event_list = MagicMock()
        mock_event_list.items = [event1, event2]
        mock_api.list_namespaced_event = MagicMock(return_value=mock_event_list)

        executor = _make_executor(core_api=mock_api)
        events = executor.get_resource_events("pod", "payment-svc-abc-123", "prod")

        assert len(events) == 2

        # Verify first event structure
        assert events[0]["type"] == "Warning"
        assert events[0]["reason"] == "BackOff"
        assert events[0]["message"] == "Back-off restarting failed container"
        assert events[0]["count"] == 5
        assert events[0]["source_component"] == "kubelet"
        assert events[0]["first_timestamp"] is not None
        assert events[0]["last_timestamp"] is not None

        # Verify second event
        assert events[1]["type"] == "Normal"
        assert events[1]["reason"] == "Pulling"

        # Verify field_selector includes both name and kind
        mock_api.list_namespaced_event.assert_called_once_with(
            namespace="prod",
            field_selector="involvedObject.name=payment-svc-abc-123,involvedObject.kind=Pod",
        )

    def test_get_resource_events_api_failure(self):
        """When the K8s API raises, return an empty list."""
        mock_api = MagicMock()
        mock_api.list_namespaced_event = MagicMock(
            side_effect=Exception("API server unreachable"),
        )

        executor = _make_executor(core_api=mock_api)
        events = executor.get_resource_events("pod", "my-pod", "default")

        assert events == []

    def test_get_resource_events_empty(self):
        """No events returned should yield an empty list."""
        mock_api = MagicMock()
        mock_event_list = MagicMock()
        mock_event_list.items = []
        mock_api.list_namespaced_event = MagicMock(return_value=mock_event_list)

        executor = _make_executor(core_api=mock_api)
        events = executor.get_resource_events("service", "payment-svc", "prod")

        assert events == []


# ---------------------------------------------------------------------------
# TestGetPodLogs
# ---------------------------------------------------------------------------

class TestGetPodLogs:
    """Tests for the get_pod_logs public method."""

    def test_get_pod_logs(self):
        """Successfully reading pod logs should return the log text."""
        mock_api = MagicMock()
        log_text = (
            "2026-03-01T10:00:00Z INFO Starting service\n"
            "2026-03-01T10:00:01Z ERROR Connection refused\n"
        )
        mock_api.read_namespaced_pod_log = MagicMock(return_value=log_text)

        executor = _make_executor(core_api=mock_api)
        result = executor.get_pod_logs("payment-svc-abc-123", "prod")

        assert "logs" in result
        assert result["logs"] == log_text
        assert "error" not in result or result.get("error") is None

        # Verify API call
        mock_api.read_namespaced_pod_log.assert_called_once_with(
            name="payment-svc-abc-123",
            namespace="prod",
            tail_lines=500,
            timestamps=True,
        )

    def test_get_pod_logs_with_container(self):
        """When container is specified, it should be passed to the K8s API."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log = MagicMock(return_value="log line")

        executor = _make_executor(core_api=mock_api)
        result = executor.get_pod_logs(
            "payment-svc-abc-123", "prod", container="sidecar",
        )

        assert "logs" in result
        mock_api.read_namespaced_pod_log.assert_called_once_with(
            name="payment-svc-abc-123",
            namespace="prod",
            tail_lines=500,
            timestamps=True,
            container="sidecar",
        )

    def test_get_pod_logs_clamps_tail_lines(self):
        """tail_lines should be clamped to max 5000."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log = MagicMock(return_value="")

        executor = _make_executor(core_api=mock_api)

        # Request 10000 lines — should be clamped to 5000
        executor.get_pod_logs("my-pod", "default", tail_lines=10000)

        call_kwargs = mock_api.read_namespaced_pod_log.call_args
        assert call_kwargs.kwargs.get("tail_lines") == 5000 or call_kwargs[1].get("tail_lines") == 5000

    def test_get_pod_logs_clamps_negative_tail_lines(self):
        """Negative tail_lines should be clamped to 1."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log = MagicMock(return_value="")

        executor = _make_executor(core_api=mock_api)
        executor.get_pod_logs("my-pod", "default", tail_lines=-50)

        call_kwargs = mock_api.read_namespaced_pod_log.call_args
        assert call_kwargs.kwargs.get("tail_lines") == 1 or call_kwargs[1].get("tail_lines") == 1

    def test_get_pod_logs_api_failure(self):
        """When the K8s API raises, return a generic error."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log = MagicMock(
            side_effect=Exception("pod has no running containers"),
        )

        executor = _make_executor(core_api=mock_api)
        result = executor.get_pod_logs("my-pod", "default")

        assert "error" in result
        assert result["error"] == "Failed to fetch pod logs"
        # Must NOT leak internal details
        assert "no running containers" not in result.get("error", "")


# ---------------------------------------------------------------------------
# TestGetApiForKind
# ---------------------------------------------------------------------------

class TestGetApiForKind:
    """Tests for the _get_api_for_kind helper method."""

    def test_returns_core_api_for_pod(self):
        mock_core = MagicMock()
        executor = _make_executor(core_api=mock_core)
        assert executor._get_api_for_kind("pod") is mock_core

    def test_returns_apps_api_for_deployment(self):
        mock_apps = MagicMock()
        executor = _make_executor(apps_api=mock_apps)
        assert executor._get_api_for_kind("deployment") is mock_apps

    def test_returns_networking_api_for_ingress(self):
        mock_net = MagicMock()
        executor = _make_executor(networking_api=mock_net)
        assert executor._get_api_for_kind("ingress") is mock_net

    def test_returns_none_for_unknown_kind(self):
        executor = _make_executor()
        assert executor._get_api_for_kind("cronjob") is None

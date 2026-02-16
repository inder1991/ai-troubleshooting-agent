import pytest
from unittest.mock import AsyncMock, patch
from backend.src.integrations.models import IntegrationConfig
from backend.src.integrations.probe import ClusterProbe, ProbeResult


def _make_openshift_config():
    return IntegrationConfig(
        name="prod-openshift",
        cluster_type="openshift",
        cluster_url="https://api.ocp.example.com:6443",
        auth_method="token",
        auth_data="sha256~fake-token",
    )


def _make_kubernetes_config():
    return IntegrationConfig(
        name="staging-k8s",
        cluster_type="kubernetes",
        cluster_url="https://k8s.example.com:6443",
        auth_method="token",
        auth_data="fake-token",
    )


def test_get_cli_tool():
    probe = ClusterProbe()
    assert probe.get_cli_tool("openshift") == "oc"
    assert probe.get_cli_tool("kubernetes") == "kubectl"


@pytest.mark.asyncio
@patch("backend.src.integrations.probe.run_command")
async def test_probe_openshift_discovers_prometheus(mock_run):
    mock_run.side_effect = [
        # Prometheus route lookup -> success
        (0, "prometheus-k8s-openshift-monitoring.apps.ocp.example.com", ""),
        # Kibana route lookup -> not found (non-zero but no connection error)
        (1, "", "not found"),
        # Version -> success
        (0, "4.14.5", ""),
    ]
    probe = ClusterProbe()
    config = _make_openshift_config()
    result = await probe.probe(config)

    assert result.reachable is True
    assert result.prometheus_url == "https://prometheus-k8s-openshift-monitoring.apps.ocp.example.com"
    assert result.cluster_version == "4.14.5"
    assert result.errors == []


@pytest.mark.asyncio
@patch("backend.src.integrations.probe.run_command")
async def test_probe_kubernetes(mock_run):
    mock_run.side_effect = [
        # prometheus-server svc -> success
        (0, "prometheus-server.monitoring.svc.cluster.local", ""),
        # elasticsearch svc -> success
        (0, "elasticsearch.logging.svc.cluster.local", ""),
        # version -> success
        (0, "v1.28.3", ""),
    ]
    probe = ClusterProbe()
    config = _make_kubernetes_config()
    result = await probe.probe(config)

    assert result.reachable is True
    assert result.prometheus_url == "http://prometheus-server.monitoring.svc.cluster.local:9090"
    assert result.elasticsearch_url == "http://elasticsearch.logging.svc.cluster.local:9200"
    assert result.cluster_version == "v1.28.3"


@pytest.mark.asyncio
@patch("backend.src.integrations.probe.run_command")
async def test_probe_handles_unreachable(mock_run):
    mock_run.return_value = (1, "", "Unable to connect to the server: dial tcp: connection refused")
    probe = ClusterProbe()
    config = _make_openshift_config()
    result = await probe.probe(config)

    assert result.reachable is False
    assert len(result.errors) == 1
    assert "Unable to connect" in result.errors[0]

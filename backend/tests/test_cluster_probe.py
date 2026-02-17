import json
import pytest
from unittest.mock import AsyncMock, patch
from src.integrations.models import IntegrationConfig
from src.integrations.probe import ClusterProbe, ProbeResult


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


def _version_json(git_version: str, openshift_version: str = "") -> str:
    """Build kubectl/oc version -o json response."""
    data = {"serverVersion": {"gitVersion": git_version}}
    if openshift_version:
        data["openshiftVersion"] = openshift_version
    return json.dumps(data)


def test_get_cli_tool():
    probe = ClusterProbe()
    assert probe.get_cli_tool("openshift") == "oc"
    assert probe.get_cli_tool("kubernetes") == "kubectl"


@pytest.mark.asyncio
@patch("src.integrations.probe.run_command")
async def test_probe_openshift_discovers_prometheus(mock_run):
    mock_run.side_effect = [
        # 1. Version (connectivity check) -> JSON success
        (0, _version_json("v1.27.6", "4.14.5"), ""),
        # 2. Prometheus route lookup -> success
        (0, "prometheus-k8s-openshift-monitoring.apps.ocp.example.com", ""),
        # 3. Kibana route lookup -> not found
        (1, "", "not found"),
    ]
    probe = ClusterProbe()
    config = _make_openshift_config()
    result = await probe.probe(config)

    assert result.reachable is True
    assert result.prometheus_url == "https://prometheus-k8s-openshift-monitoring.apps.ocp.example.com"
    assert result.cluster_version == "4.14.5"
    assert result.errors == []


@pytest.mark.asyncio
@patch("src.integrations.probe.run_command")
async def test_probe_kubernetes_finds_by_label(mock_run):
    """Prometheus found on first label selector query."""
    mock_run.side_effect = [
        # 1. Version (connectivity check) -> JSON success
        (0, _version_json("v1.28.3"), ""),
        # 2. Prometheus label search -> found
        (0, "prometheus-kube-prom.monitoring.svc.cluster.local", ""),
        # 3. Elasticsearch label search -> found
        (0, "elasticsearch-master.elastic.svc.cluster.local", ""),
    ]
    probe = ClusterProbe()
    config = _make_kubernetes_config()
    result = await probe.probe(config)

    assert result.reachable is True
    assert result.prometheus_url == "http://prometheus-kube-prom.monitoring.svc.cluster.local:9090"
    assert result.elasticsearch_url == "http://elasticsearch-master.elastic.svc.cluster.local:9200"
    assert result.cluster_version == "v1.28.3"


@pytest.mark.asyncio
@patch("src.integrations.probe.run_command")
async def test_probe_kubernetes_cluster_reachable_services_missing(mock_run):
    """Cluster reachable but no Prometheus/ES found — should still be reachable."""
    mock_run.side_effect = [
        # 1. Version -> JSON success (cluster reachable)
        (0, _version_json("v1.28.3"), ""),
    ] + [
        # All subsequent label + name lookups fail
        (1, "", 'Error from server (NotFound): not found')
    ] * 50  # enough for all label + name attempts
    probe = ClusterProbe()
    config = _make_kubernetes_config()
    result = await probe.probe(config)

    assert result.reachable is True
    assert result.prometheus_url is None
    assert result.elasticsearch_url is None
    assert "not found" in result.endpoint_results["prometheus"].error.lower()


@pytest.mark.asyncio
@patch("src.integrations.probe.run_command")
async def test_probe_handles_unreachable(mock_run):
    mock_run.return_value = (1, "", "Unable to connect to the server: dial tcp: connection refused")
    probe = ClusterProbe()
    config = _make_openshift_config()
    result = await probe.probe(config)

    assert result.reachable is False
    assert len(result.errors) == 1
    assert "Unable to connect" in result.errors[0]

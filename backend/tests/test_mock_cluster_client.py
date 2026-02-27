import pytest
from src.agents.cluster_client.mock_client import MockClusterClient

@pytest.mark.asyncio
async def test_mock_detect_platform():
    client = MockClusterClient(platform="openshift")
    info = await client.detect_platform()
    assert info["platform"] == "openshift"
    assert "version" in info

@pytest.mark.asyncio
async def test_mock_list_nodes():
    client = MockClusterClient()
    result = await client.list_nodes()
    assert len(result.data) > 0
    assert result.truncated is False

@pytest.mark.asyncio
async def test_mock_list_events_truncation():
    client = MockClusterClient()
    result = await client.list_events()
    assert result.returned <= 500

@pytest.mark.asyncio
async def test_mock_openshift_operators():
    client = MockClusterClient(platform="openshift")
    result = await client.get_cluster_operators()
    assert len(result.data) > 0

@pytest.mark.asyncio
async def test_mock_k8s_operators_empty():
    client = MockClusterClient(platform="kubernetes")
    result = await client.get_cluster_operators()
    assert len(result.data) == 0

@pytest.mark.asyncio
async def test_mock_prometheus_query():
    client = MockClusterClient()
    result = await client.query_prometheus("node_cpu_utilisation")
    assert len(result.data) > 0

@pytest.mark.asyncio
async def test_mock_query_logs():
    client = MockClusterClient()
    result = await client.query_logs("cluster-logs", {"query": "error"})
    assert len(result.data) > 0

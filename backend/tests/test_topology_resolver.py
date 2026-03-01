import pytest
import time
from unittest.mock import AsyncMock, patch

from src.agents.cluster.topology_resolver import (
    topology_snapshot_resolver, _topology_cache, clear_topology_cache, TOPOLOGY_TTL_SECONDS,
)
from src.agents.cluster.state import TopologySnapshot, TopologyNode, TopologyEdge
from src.agents.cluster_client.mock_client import MockClusterClient


def _make_config(client):
    return {"configurable": {"cluster_client": client}}


def _make_state(session_id="test-session"):
    return {"diagnostic_id": session_id, "platform": "openshift"}


@pytest.fixture(autouse=True)
def _clear_cache():
    _topology_cache.clear()
    yield
    _topology_cache.clear()


@pytest.mark.asyncio
async def test_builds_topology_from_client():
    client = MockClusterClient(platform="openshift")
    result = await topology_snapshot_resolver(_make_state(), _make_config(client))
    topo = result["topology_graph"]
    assert len(topo["nodes"]) > 0
    assert result["topology_freshness"]["stale"] is False


@pytest.mark.asyncio
async def test_cache_hit_returns_same_snapshot():
    client = MockClusterClient()
    state = _make_state("cached-session")
    r1 = await topology_snapshot_resolver(state, _make_config(client))
    r2 = await topology_snapshot_resolver(state, _make_config(client))
    assert r1["topology_graph"]["built_at"] == r2["topology_graph"]["built_at"]


@pytest.mark.asyncio
async def test_cache_miss_after_ttl():
    client = MockClusterClient()
    state = _make_state("ttl-session")
    await topology_snapshot_resolver(state, _make_config(client))
    # Manually expire cache
    _topology_cache["ttl-session"] = (_topology_cache["ttl-session"][0], time.monotonic() - TOPOLOGY_TTL_SECONDS - 1)
    r2 = await topology_snapshot_resolver(state, _make_config(client))
    assert r2["topology_freshness"]["stale"] is False


@pytest.mark.asyncio
async def test_no_client_returns_stale():
    result = await topology_snapshot_resolver(_make_state(), {"configurable": {}})
    assert result["topology_freshness"]["stale"] is True


@pytest.mark.asyncio
async def test_clear_cache():
    client = MockClusterClient()
    await topology_snapshot_resolver(_make_state("clear-test"), _make_config(client))
    assert "clear-test" in _topology_cache
    clear_topology_cache("clear-test")
    assert "clear-test" not in _topology_cache


@pytest.mark.asyncio
async def test_openshift_includes_operators():
    client = MockClusterClient(platform="openshift")
    result = await topology_snapshot_resolver(_make_state(), _make_config(client))
    nodes = result["topology_graph"]["nodes"]
    operator_keys = [k for k in nodes if k.startswith("operator/")]
    assert len(operator_keys) > 0


@pytest.mark.asyncio
async def test_edges_have_valid_relations():
    client = MockClusterClient()
    result = await topology_snapshot_resolver(_make_state(), _make_config(client))
    valid_relations = {"hosts", "owns", "routes_to", "mounted_by", "manages", "depends_on"}
    for edge in result["topology_graph"]["edges"]:
        assert edge["relation"] in valid_relations


@pytest.mark.asyncio
async def test_kubernetes_no_operators():
    client = MockClusterClient(platform="kubernetes")
    result = await topology_snapshot_resolver(_make_state(), _make_config(client))
    nodes = result["topology_graph"]["nodes"]
    operator_keys = [k for k in nodes if k.startswith("operator/")]
    assert len(operator_keys) == 0

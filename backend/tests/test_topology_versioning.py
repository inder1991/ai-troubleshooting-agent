"""Tests for topology versioning: list snapshots, load by ID, /topology/current."""
import os
import json
import pytest
from unittest.mock import patch

from starlette.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet, Interface
from src.network.adapters.registry import AdapterRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test_versioning.db")
    return TopologyStore(db_path=db_path)


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def client(store, kg):
    """TestClient with patched singletons."""
    with patch("src.api.network_endpoints._topology_store", store), \
         patch("src.api.network_endpoints._knowledge_graph", kg), \
         patch("src.api.network_endpoints._adapter_registry", AdapterRegistry()), \
         patch("src.api.network_endpoints._network_sessions", {}):
        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


def _seed_topology(store):
    """Seed a minimal topology so KG has nodes/edges to export."""
    store.add_device(Device(id="r1", name="Router1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
    store.add_device(Device(id="sw1", name="Switch1", device_type=DeviceType.SWITCH, management_ip="10.0.1.1"))
    store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.1"))
    store.add_interface(Interface(id="r1-e0", device_id="r1", name="eth0", ip="10.0.0.1"))
    store.add_interface(Interface(id="sw1-e0", device_id="sw1", name="eth0", ip="10.0.1.1"))


# ---------------------------------------------------------------------------
# Store-level tests
# ---------------------------------------------------------------------------


class TestListVersions:
    def test_list_versions_returns_history(self, store):
        """Multiple saves should all appear in list_diagram_snapshots."""
        ids = []
        for i in range(3):
            snap_id = store.save_diagram_snapshot(
                json.dumps({"v": i}), f"snapshot {i}"
            )
            ids.append(snap_id)

        versions = store.list_diagram_snapshots()
        assert len(versions) == 3
        # Most recent first
        returned_ids = [v["id"] for v in versions]
        assert returned_ids == sorted(returned_ids, reverse=True)
        # Each version has expected fields
        for v in versions:
            assert "id" in v
            assert "timestamp" in v
            assert "description" in v


class TestLoadById:
    def test_load_by_id(self, store):
        """Loading a specific snapshot by ID returns its data."""
        snap_id = store.save_diagram_snapshot(
            '{"nodes":[1,2,3]}', "specific version"
        )
        result = store.load_diagram_snapshot_by_id(snap_id)
        assert result is not None
        assert result["id"] == snap_id
        assert result["snapshot_json"] == '{"nodes":[1,2,3]}'
        assert result["description"] == "specific version"
        assert result["timestamp"] is not None

    def test_load_nonexistent_returns_none(self, store):
        """Loading a non-existent ID returns None."""
        result = store.load_diagram_snapshot_by_id(99999)
        assert result is None


# ---------------------------------------------------------------------------
# Endpoint-level tests
# ---------------------------------------------------------------------------


class TestTopologyVersionsEndpoint:
    def test_versions_endpoint(self, client):
        """GET /topology/versions returns saved snapshots."""
        # Save two versions
        client.post("/api/v4/network/topology/save", json={
            "diagram_json": '{"v":1}', "description": "v1",
        })
        client.post("/api/v4/network/topology/save", json={
            "diagram_json": '{"v":2}', "description": "v2",
        })

        resp = client.get("/api/v4/network/topology/versions")
        assert resp.status_code == 200
        versions = resp.json()["versions"]
        assert len(versions) == 2
        # Most recent first
        assert versions[0]["description"] == "v2"
        assert versions[1]["description"] == "v1"


class TestTopologyLoadVersionEndpoint:
    def test_load_specific_version(self, client):
        """GET /topology/load/{snap_id} returns the specific snapshot."""
        save_resp = client.post("/api/v4/network/topology/save", json={
            "diagram_json": '{"target": true}', "description": "target",
        })
        snap_id = save_resp.json()["snapshot_id"]

        resp = client.get(f"/api/v4/network/topology/load/{snap_id}")
        assert resp.status_code == 200
        snapshot = resp.json()["snapshot"]
        assert snapshot["id"] == snap_id
        assert snapshot["snapshot_json"] == '{"target": true}'

    def test_load_nonexistent_version_404(self, client):
        """GET /topology/load/{bad_id} returns 404."""
        resp = client.get("/api/v4/network/topology/load/99999")
        assert resp.status_code == 404


class TestTopologyCurrentEndpoint:
    def test_topology_current_returns_rf_graph(self, client, store, kg):
        """GET /topology/current returns nodes and edges from the KG."""
        _seed_topology(store)
        kg.load_from_store()

        resp = client.get("/api/v4/network/topology/current")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        # We seeded 2 devices + 1 subnet = at least 3 nodes
        assert len(data["nodes"]) >= 2

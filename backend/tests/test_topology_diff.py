"""Tests for topology snapshot diff endpoint."""
import json
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    snap1_data = json.dumps({
        "nodes": [
            {"id": "r1", "data": {"label": "Router1", "device_type": "router"}},
            {"id": "r2", "data": {"label": "Router2", "device_type": "router"}},
        ],
        "edges": [{"source": "r1", "target": "r2"}],
    })
    snap2_data = json.dumps({
        "nodes": [
            {"id": "r1", "data": {"label": "Router1-Updated", "device_type": "router"}},
            {"id": "r3", "data": {"label": "Router3", "device_type": "switch"}},
        ],
        "edges": [{"source": "r1", "target": "r3"}],
    })
    store.save_diagram_snapshot(snap1_data, "v1")
    store.save_diagram_snapshot(snap2_data, "v2")

    from src.api.main import app
    from src.api import network_endpoints
    orig = network_endpoints._get_topology_store
    network_endpoints._get_topology_store = lambda: store
    client = TestClient(app)
    yield store, client
    network_endpoints._get_topology_store = orig


class TestTopologyDiff:
    def test_diff_two_snapshots(self, store_and_client):
        store, client = store_and_client
        versions = store.list_diagram_snapshots()
        v1_id = versions[-1]["id"]  # oldest first (list is DESC, so last = oldest)
        v2_id = versions[0]["id"]   # newest
        resp = client.get(f"/api/v4/network/topology/diff?v1={v1_id}&v2={v2_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "added" in data
        assert "removed" in data
        assert "changed" in data
        # r2 was removed, r3 was added, r1 was changed (label updated)
        added_ids = [n["id"] for n in data["added"]]
        removed_ids = [n["id"] for n in data["removed"]]
        changed_ids = [c["id"] for c in data["changed"]]
        assert "r3" in added_ids
        assert "r2" in removed_ids
        assert "r1" in changed_ids

    def test_diff_missing_version(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/topology/diff?v1=999&v2=998")
        assert resp.status_code == 404

    def test_diff_missing_params(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/topology/diff")
        assert resp.status_code == 422

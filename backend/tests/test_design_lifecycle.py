"""Integration tests for the full design lifecycle."""
import json
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    return TopologyStore(db_path=db_path)


@pytest.fixture
def kg(store):
    kg = NetworkKnowledgeGraph(store)
    return kg


@pytest.fixture
def live_env(store, kg):
    """Set up a minimal live environment."""
    store.add_device(Device(
        id="gw-1", name="gw-1", device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1",
    ))
    kg.add_device(Device(
        id="gw-1", name="gw-1", device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1",
    ))
    return store, kg


def _snap(nodes, edges=None):
    return json.dumps({"nodes": nodes, "edges": edges or []})


def _planned(id, label, ip=""):
    return {
        "id": id, "type": "device", "position": {"x": 0, "y": 0},
        "data": {"label": label, "deviceType": "host", "ip": ip, "_source": "planned"},
    }


class TestFullLifecycle:
    def test_draft_to_applied(self, live_env):
        store, kg = live_env
        # Create design
        snap = _snap([_planned("web-1", "web-1", "10.0.1.1")])
        design = store.create_design("d1", "Web Tier Expansion", snapshot_json=snap)
        assert design["status"] == "draft"

        # Review
        store.update_design_status("d1", "reviewed")
        d = store.get_design("d1")
        assert d["status"] == "reviewed"

        # Simulate (status update)
        store.update_design_status("d1", "simulated")
        d = store.get_design("d1")
        assert d["status"] == "simulated"

        # Approve
        store.update_design_status("d1", "approved")
        d = store.get_design("d1")
        assert d["status"] == "approved"

        # Diff + Apply
        diff = store.compute_design_diff("d1")
        assert diff["can_apply"] is True
        result = kg.apply_design("d1", expected_live_hash=diff["live_hash"])
        assert result["devices_added"] == 1

        # Verify device exists in inventory
        assert store.get_device("web-1") is not None

        # Design status should be applied
        d = store.get_design("d1")
        assert d["status"] == "applied"

        # Mark verified
        store.update_design_status("d1", "verified")
        d = store.get_design("d1")
        assert d["status"] == "verified"


class TestDesignCRUD:
    def test_create_and_get(self, store):
        store.create_design("d1", "Test Design", description="desc", snapshot_json="{}")
        d = store.get_design("d1")
        assert d is not None
        assert d["name"] == "Test Design"
        assert d["description"] == "desc"
        assert d["status"] == "draft"

    def test_list_designs(self, store):
        store.create_design("d1", "A", snapshot_json="{}")
        store.create_design("d2", "B", snapshot_json="{}")
        designs = store.list_designs()
        assert len(designs) == 2

    def test_list_by_status(self, store):
        store.create_design("d1", "A", snapshot_json="{}")
        store.create_design("d2", "B", snapshot_json="{}")
        store.update_design_status("d2", "reviewed")
        drafts = store.list_designs(status="draft")
        assert len(drafts) == 1
        assert drafts[0]["id"] == "d1"

    def test_delete(self, store):
        store.create_design("d1", "A", snapshot_json="{}")
        assert store.delete_design("d1") is True
        assert store.get_design("d1") is None

    def test_update_with_version(self, store):
        store.create_design("d1", "A", snapshot_json="{}")
        d = store.get_design("d1")
        assert d["version"] == 1
        store.update_design("d1", name="B", expected_version=1)
        d = store.get_design("d1")
        assert d["version"] == 2
        assert d["name"] == "B"


class TestLiveInventoryEndpoint:
    def test_returns_reactflow_format(self, live_env):
        store, _ = live_env
        data = store.get_live_inventory_as_reactflow()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) >= 1
        node = data["nodes"][0]
        assert "id" in node
        assert "type" in node
        assert "position" in node
        assert node["data"]["_source"] == "live"
        assert node["data"]["_locked"] is True

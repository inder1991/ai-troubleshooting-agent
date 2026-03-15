"""Unit tests for apply_design() — TOCTOU, optimistic locking, rollback."""
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
def setup_live(store, kg):
    store.add_device(Device(
        id="fw-1", name="fw-1", device_type=DeviceType.FIREWALL,
        management_ip="10.0.0.1", vendor="palo_alto",
    ))
    kg.add_device(Device(
        id="fw-1", name="fw-1", device_type=DeviceType.FIREWALL,
        management_ip="10.0.0.1", vendor="palo_alto",
    ))
    return store, kg


def _snap(nodes, edges=None):
    return json.dumps({"nodes": nodes, "edges": edges or []})


def _planned(id, label, ip=""):
    return {
        "id": id, "type": "device", "position": {"x": 0, "y": 0},
        "data": {"label": label, "deviceType": "host", "ip": ip, "_source": "planned"},
    }


class TestApplyHappyPath:
    def test_apply_succeeds(self, setup_live):
        store, kg = setup_live
        snap = _snap([_planned("host-new", "host-new", "10.0.1.1")])
        store.create_design("d1", "test", snapshot_json=snap)
        # Compute diff first to set live_hash
        store.compute_design_diff("d1")
        design = store.get_design("d1")
        result = kg.apply_design("d1", expected_live_hash=design["live_hash"])
        assert result["devices_added"] == 1
        assert store.get_device("host-new") is not None


class TestTOCTOU:
    def test_rejects_stale_hash(self, setup_live):
        store, kg = setup_live
        snap = _snap([_planned("host-new", "host-new", "10.0.1.1")])
        store.create_design("d1", "test", snapshot_json=snap)
        store.compute_design_diff("d1")
        # Modify live inventory after diff
        store.add_device(Device(
            id="sneaky", name="sneaky", device_type=DeviceType.HOST,
            management_ip="10.0.9.9",
        ))
        design = store.get_design("d1")
        with pytest.raises(ValueError, match="LIVE_DRIFT"):
            kg.apply_design("d1", expected_live_hash=design["live_hash"])


class TestConflictRecheck:
    def test_rejects_on_conflict(self, setup_live):
        store, kg = setup_live
        # Design with conflicting IP
        snap = _snap([_planned("new", "new", "10.0.0.1")])
        store.create_design("d1", "test", snapshot_json=snap)
        with pytest.raises(ValueError, match="CONFLICTS"):
            kg.apply_design("d1")


class TestOptimisticLocking:
    def test_version_conflict(self, store):
        store.create_design("d1", "test", snapshot_json="{}")
        store.update_design("d1", name="v1")
        with pytest.raises(ValueError, match="VERSION_CONFLICT"):
            store.update_design("d1", name="v2", expected_version=1)

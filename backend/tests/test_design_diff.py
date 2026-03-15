"""Unit tests for compute_design_diff() conflict detection."""
import json
import pytest
from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    s = TopologyStore(db_path=db_path)
    return s


@pytest.fixture
def store_with_devices(store):
    """Store pre-loaded with 2 live devices."""
    store.add_device(Device(
        id="fw-prod-1", name="fw-prod-1", device_type=DeviceType.FIREWALL,
        management_ip="10.0.0.1", vendor="palo_alto", zone_id="dmz",
    ))
    store.add_device(Device(
        id="sw-core-1", name="sw-core-1", device_type=DeviceType.SWITCH,
        management_ip="10.0.0.2", vendor="cisco", zone_id="core",
    ))
    return store


def _make_design_snapshot(nodes, edges=None):
    return json.dumps({"nodes": nodes, "edges": edges or []})


def _planned_node(id, label, ip="", zone="", device_type="firewall", **extra):
    return {
        "id": id, "type": "device",
        "position": {"x": 0, "y": 0},
        "data": {"label": label, "deviceType": device_type, "ip": ip, "zone": zone, "_source": "planned", **extra},
    }


def _planned_edge(id, source, target, label="connected_to"):
    return {
        "id": id, "source": source, "target": target,
        "data": {"label": label, "_source": "planned"},
    }


class TestNoConflicts:
    def test_clean_diff(self, store_with_devices):
        store = store_with_devices
        snap = _make_design_snapshot([_planned_node("fw-new", "fw-new", ip="10.0.1.1")])
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert diff["can_apply"] is True
        assert len(diff["conflicts"]) == 0
        assert len(diff["added"]) == 1


class TestIPConflicts:
    def test_ip_conflict_blocks_apply(self, store_with_devices):
        store = store_with_devices
        snap = _make_design_snapshot([_planned_node("fw-new", "fw-new", ip="10.0.0.1")])
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert diff["can_apply"] is False
        assert any(c["type"] == "ip_conflict" for c in diff["conflicts"])

    def test_intra_design_ip_conflict(self, store_with_devices):
        store = store_with_devices
        snap = _make_design_snapshot([
            _planned_node("a", "dev-a", ip="10.0.2.1"),
            _planned_node("b", "dev-b", ip="10.0.2.1"),
        ])
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert diff["can_apply"] is False
        ip_conflicts = [c for c in diff["conflicts"] if c["type"] == "ip_conflict"]
        assert len(ip_conflicts) >= 1


class TestHostnameConflicts:
    def test_hostname_conflict_blocks_apply(self, store_with_devices):
        store = store_with_devices
        snap = _make_design_snapshot([_planned_node("new-id", "fw-prod-1", ip="10.0.3.1")])
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert diff["can_apply"] is False
        assert any(c["type"] == "hostname_conflict" for c in diff["conflicts"])


class TestIDConflicts:
    def test_id_conflict_blocks_apply(self, store_with_devices):
        store = store_with_devices
        snap = _make_design_snapshot([_planned_node("fw-prod-1", "different-name", ip="10.0.4.1")])
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert diff["can_apply"] is False
        assert any(c["type"] == "id_conflict" for c in diff["conflicts"])


class TestSubnetOverlap:
    def test_subnet_overlap_with_live(self, store_with_devices):
        """Planned subnet CIDR overlapping a live subnet is flagged."""
        store = store_with_devices
        # Add a live subnet
        from src.network.models import Subnet
        store.add_subnet(Subnet(id="sub-live", cidr="10.1.0.0/16", zone_id="core"))
        snap = _make_design_snapshot([
            _planned_node("sub-new", "sub-new", device_type="subnet", cidr="10.1.5.0/24"),
        ])
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert diff["can_apply"] is False
        assert any(c["type"] == "subnet_overlap" for c in diff["conflicts"])

    def test_intra_design_subnet_overlap(self, store_with_devices):
        """Two planned subnets with overlapping CIDRs within the same design."""
        store = store_with_devices
        snap = _make_design_snapshot([
            _planned_node("sub-a", "sub-a", device_type="subnet", cidr="10.2.0.0/16"),
            _planned_node("sub-b", "sub-b", device_type="subnet", cidr="10.2.1.0/24"),
        ])
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert diff["can_apply"] is False
        overlap_conflicts = [c for c in diff["conflicts"] if c["type"] == "subnet_overlap"]
        assert len(overlap_conflicts) >= 1


class TestVLANConflict:
    def test_intra_design_vlan_conflict(self, store_with_devices):
        """Two planned nodes with the same VLAN in the same zone."""
        store = store_with_devices
        snap = _make_design_snapshot([
            _planned_node("sw-a", "sw-a", device_type="switch", zone="dmz", vlan="100"),
            _planned_node("sw-b", "sw-b", device_type="switch", zone="dmz", vlan="100"),
        ])
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert diff["can_apply"] is False
        vlan_conflicts = [c for c in diff["conflicts"] if c["type"] == "vlan_conflict"]
        assert len(vlan_conflicts) >= 1


class TestEdgeValidation:
    def test_type_incompatible_edge(self, store_with_devices):
        """Edge between incompatible device types is flagged."""
        store = store_with_devices
        snap = _make_design_snapshot(
            [
                _planned_node("vpn-1", "vpn-1", ip="10.0.7.1", device_type="vpn_tunnel"),
                _planned_node("dc-1", "dc-1", ip="10.0.7.2", device_type="direct_connect"),
            ],
            [_planned_edge("e1", "vpn-1", "dc-1")],
        )
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert any(e["type"] == "type_incompatible" for e in diff["edge_errors"])

    def test_dangling_edge_detected(self, store_with_devices):
        store = store_with_devices
        snap = _make_design_snapshot(
            [_planned_node("fw-new", "fw-new", ip="10.0.5.1")],
            [_planned_edge("e1", "fw-new", "nonexistent-device")],
        )
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert diff["can_apply"] is False
        assert any(e["type"] == "dangling_edge" for e in diff["edge_errors"])

    def test_zone_violation_detected(self, store_with_devices):
        store = store_with_devices
        snap = _make_design_snapshot(
            [
                _planned_node("host-a", "host-a", ip="10.0.6.1", zone="dmz", device_type="host"),
                _planned_node("host-b", "host-b", ip="10.0.6.2", zone="core", device_type="host"),
            ],
            [_planned_edge("e1", "host-a", "host-b")],
        )
        store.create_design("d1", "test", snapshot_json=snap)
        diff = store.compute_design_diff("d1")
        assert any(e["type"] == "zone_violation" for e in diff["edge_errors"])


class TestLiveHash:
    def test_live_hash_computed(self, store_with_devices):
        store = store_with_devices
        h = store.compute_live_hash()
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_live_hash_changes_with_inventory(self, store_with_devices):
        store = store_with_devices
        h1 = store.compute_live_hash()
        store.add_device(Device(
            id="new-dev", name="new-dev", device_type=DeviceType.HOST,
            management_ip="10.0.9.1",
        ))
        h2 = store.compute_live_hash()
        assert h1 != h2

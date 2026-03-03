"""Tests for HA group model and store."""
import os
import pytest
from pydantic import ValidationError
from src.network.models import HAGroup, HAMode, HARole, Device, DeviceType, Subnet
from src.network.ha_validation import validate_ha_group
from src.network.topology_store import TopologyStore


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


class TestHAGroupModel:
    def test_valid_ha_group(self):
        g = HAGroup(id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
                    member_ids=["d1", "d2"], virtual_ips=["10.0.0.1"],
                    active_member_id="d1")
        assert g.ha_mode == HAMode.ACTIVE_PASSIVE
        assert len(g.member_ids) == 2

    def test_ha_group_needs_2_members(self):
        with pytest.raises(ValidationError, match="at least 2"):
            HAGroup(id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
                    member_ids=["d1"])

    def test_vip_must_be_valid_ip(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            HAGroup(id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
                    member_ids=["d1", "d2"], virtual_ips=["not-an-ip"])

    def test_device_ha_fields(self):
        d = Device(id="d1", name="fw-01", ha_group_id="ha1", ha_role="active")
        assert d.ha_group_id == "ha1"
        assert d.ha_role == "active"


class TestHAGroupStore:
    def test_add_and_get_ha_group(self, store):
        g = HAGroup(id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
                    member_ids=["d1", "d2"], virtual_ips=["10.0.0.1"],
                    active_member_id="d1")
        store.add_ha_group(g)
        loaded = store.get_ha_group("ha1")
        assert loaded is not None
        assert loaded.name == "FW-HA"
        assert loaded.member_ids == ["d1", "d2"]
        assert loaded.virtual_ips == ["10.0.0.1"]

    def test_list_ha_groups(self, store):
        g1 = HAGroup(id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
                     member_ids=["d1", "d2"])
        g2 = HAGroup(id="ha2", name="LB-HA", ha_mode=HAMode.ACTIVE_ACTIVE,
                     member_ids=["d3", "d4"])
        store.add_ha_group(g1)
        store.add_ha_group(g2)
        groups = store.list_ha_groups()
        assert len(groups) == 2

    def test_device_with_ha_fields_roundtrip(self, store):
        d = Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL,
                   management_ip="10.0.0.2", ha_group_id="ha1", ha_role="active")
        store.add_device(d)
        loaded = store.get_device("d1")
        assert loaded.ha_group_id == "ha1"
        assert loaded.ha_role == "active"


class TestHAValidation:
    def test_members_must_be_same_device_type(self, store):
        store.add_device(Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
        store.add_device(Device(id="d2", name="rtr-01", device_type=DeviceType.ROUTER, management_ip="10.0.0.2"))
        errors = validate_ha_group(store, HAGroup(
            id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"]))
        assert any("same device type" in e for e in errors)

    def test_members_must_be_in_same_subnet(self, store):
        store.add_device(Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
        store.add_device(Device(id="d2", name="fw-02", device_type=DeviceType.FIREWALL, management_ip="192.168.1.1"))
        errors = validate_ha_group(store, HAGroup(
            id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"]))
        assert any("same subnet" in e.lower() for e in errors)

    def test_vip_must_be_in_member_subnet(self, store):
        store.add_device(Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
        store.add_device(Device(id="d2", name="fw-02", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))
        errors = validate_ha_group(store, HAGroup(
            id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"], virtual_ips=["192.168.1.100"]))
        assert any("VIP" in e and "not within" in e for e in errors)

    def test_active_passive_needs_one_active(self, store):
        store.add_device(Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
        store.add_device(Device(id="d2", name="fw-02", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        errors = validate_ha_group(store, HAGroup(
            id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"], active_member_id=""))
        assert any("active member" in e.lower() for e in errors)

    def test_valid_ha_group_no_errors(self, store):
        store.add_device(Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
        store.add_device(Device(id="d2", name="fw-02", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))
        errors = validate_ha_group(store, HAGroup(
            id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"], virtual_ips=["10.0.0.100"],
            active_member_id="d1"))
        assert len(errors) == 0

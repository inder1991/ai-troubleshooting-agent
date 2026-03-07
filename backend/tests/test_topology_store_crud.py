"""Comprehensive unit tests for TopologyStore CRUD operations.

Covers: Device, Interface, Subnet, Route, Zone, FirewallRule, NATRule,
        HAGroup, VPC, and DiagramSnapshot CRUD paths.
"""
import json
import os
import tempfile
import pytest

from src.network.topology_store import TopologyStore
from src.network.models import (
    Device, DeviceType, Interface, Subnet, Zone,
    Route, NATRule, NATDirection, FirewallRule, PolicyAction,
    HAGroup, HAMode,
    VPC, CloudProvider,
)


@pytest.fixture()
def store(tmp_path):
    """Create a TopologyStore backed by a temporary SQLite file."""
    db_path = os.path.join(str(tmp_path), "data", "test_topology.db")
    return TopologyStore(db_path=db_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_device(id: str = "dev-1", name: str = "router-a", **kw) -> Device:
    return Device(id=id, name=name, device_type=DeviceType.ROUTER, **kw)


def _make_interface(id: str = "if-1", device_id: str = "dev-1", **kw) -> Interface:
    defaults = dict(name="eth0", ip="10.0.0.1")
    defaults.update(kw)
    return Interface(id=id, device_id=device_id, **defaults)


def _make_subnet(id: str = "sub-1", cidr: str = "10.0.0.0/24", **kw) -> Subnet:
    return Subnet(id=id, cidr=cidr, **kw)


def _make_zone(id: str = "zone-1", name: str = "dmz", **kw) -> Zone:
    return Zone(id=id, name=name, **kw)


def _make_route(id: str = "rt-1", device_id: str = "dev-1", **kw) -> Route:
    defaults = dict(destination_cidr="0.0.0.0/0", next_hop="10.0.0.254")
    defaults.update(kw)
    return Route(id=id, device_id=device_id, **defaults)


def _make_nat_rule(id: str = "nat-1", device_id: str = "dev-1", **kw) -> NATRule:
    defaults = dict(original_src="10.0.0.5", translated_src="203.0.113.1",
                    direction=NATDirection.SNAT)
    defaults.update(kw)
    return NATRule(id=id, device_id=device_id, **defaults)


def _make_firewall_rule(id: str = "fw-1", device_id: str = "dev-1", **kw) -> FirewallRule:
    defaults = dict(rule_name="deny-all", src_zone="inside", dst_zone="outside",
                    src_ips=["10.0.0.0/8"], dst_ips=["0.0.0.0/0"],
                    ports=[80, 443], protocol="tcp",
                    action=PolicyAction.DENY, logged=True, order=100)
    defaults.update(kw)
    return FirewallRule(id=id, device_id=device_id, **defaults)


def _make_ha_group(id: str = "ha-1", **kw) -> HAGroup:
    defaults = dict(name="fw-pair", ha_mode=HAMode.ACTIVE_PASSIVE,
                    member_ids=["dev-1", "dev-2"],
                    virtual_ips=["10.0.0.100"], active_member_id="dev-1",
                    priority_map={"dev-1": 100, "dev-2": 50},
                    sync_interface="eth3")
    defaults.update(kw)
    return HAGroup(id=id, **defaults)


def _make_vpc(id: str = "vpc-1", **kw) -> VPC:
    defaults = dict(name="prod-vpc", cloud_provider=CloudProvider.AWS,
                    region="us-east-1", cidr_blocks=["10.0.0.0/16"],
                    account_id="123456789012")
    defaults.update(kw)
    return VPC(id=id, **defaults)


# ===================================================================
# 1. Device CRUD
# ===================================================================

class TestDeviceCRUD:

    def test_add_and_get_device(self, store):
        dev = _make_device()
        store.add_device(dev)
        got = store.get_device("dev-1")
        assert got is not None
        assert got.id == "dev-1"
        assert got.name == "router-a"
        assert got.device_type == DeviceType.ROUTER

    def test_get_device_not_found(self, store):
        assert store.get_device("nonexistent") is None

    def test_list_devices_empty(self, store):
        assert store.list_devices() == []

    def test_list_devices_returns_all(self, store):
        store.add_device(_make_device("d1", "r1"))
        store.add_device(_make_device("d2", "r2"))
        store.add_device(_make_device("d3", "r3"))
        devs = store.list_devices()
        assert len(devs) == 3
        ids = {d.id for d in devs}
        assert ids == {"d1", "d2", "d3"}

    def test_list_devices_pagination(self, store):
        for i in range(5):
            store.add_device(_make_device(f"d{i}", f"device-{i}"))
        page = store.list_devices(offset=1, limit=2)
        assert len(page) == 2

    def test_count_devices(self, store):
        assert store.count_devices() == 0
        store.add_device(_make_device("d1", "r1"))
        store.add_device(_make_device("d2", "r2"))
        assert store.count_devices() == 2

    def test_update_device(self, store):
        store.add_device(_make_device())
        updated = store.update_device("dev-1", name="router-b", vendor="cisco")
        assert updated is not None
        assert updated.name == "router-b"
        assert updated.vendor == "cisco"

    def test_update_device_not_found(self, store):
        assert store.update_device("nonexistent", name="x") is None

    def test_update_device_ignores_unknown_fields(self, store):
        store.add_device(_make_device())
        updated = store.update_device("dev-1", bogus_field="ignored")
        assert updated is not None
        assert updated.name == "router-a"  # unchanged

    def test_add_device_upsert(self, store):
        store.add_device(_make_device(vendor="juniper"))
        store.add_device(_make_device(vendor="cisco"))
        got = store.get_device("dev-1")
        assert got.vendor == "cisco"  # replaced

    def test_delete_device_cascades(self, store):
        """Deleting a device must also delete its interfaces, routes,
        NAT rules, and firewall rules."""
        store.add_device(_make_device())
        store.add_interface(_make_interface())
        store.add_route(_make_route())
        store.add_nat_rule(_make_nat_rule())
        store.add_firewall_rule(_make_firewall_rule())

        store.delete_device("dev-1")

        assert store.get_device("dev-1") is None
        assert store.list_interfaces(device_id="dev-1") == []
        assert store.list_routes(device_id="dev-1") == []
        assert store.list_nat_rules(device_id="dev-1") == []
        assert store.list_firewall_rules(device_id="dev-1") == []


# ===================================================================
# 2. Interface CRUD
# ===================================================================

class TestInterfaceCRUD:

    def test_add_and_list_interfaces(self, store):
        store.add_device(_make_device())
        store.add_interface(_make_interface())
        ifaces = store.list_interfaces()
        assert len(ifaces) == 1
        assert ifaces[0].id == "if-1"
        assert ifaces[0].ip == "10.0.0.1"

    def test_list_interfaces_filter_by_device(self, store):
        store.add_device(_make_device("dev-1", "r1"))
        store.add_device(_make_device("dev-2", "r2"))
        store.add_interface(_make_interface("if-1", "dev-1"))
        store.add_interface(_make_interface("if-2", "dev-2", ip="10.0.0.2"))
        assert len(store.list_interfaces(device_id="dev-1")) == 1
        assert len(store.list_interfaces(device_id="dev-2")) == 1

    def test_find_interface_by_ip(self, store):
        store.add_device(_make_device())
        store.add_interface(_make_interface())
        found = store.find_interface_by_ip("10.0.0.1")
        assert found is not None
        assert found.id == "if-1"

    def test_find_interface_by_ip_not_found(self, store):
        assert store.find_interface_by_ip("192.168.1.1") is None

    def test_delete_interface(self, store):
        store.add_device(_make_device())
        store.add_interface(_make_interface())
        store.delete_interface("if-1")
        assert store.list_interfaces() == []


# ===================================================================
# 3. Subnet CRUD
# ===================================================================

class TestSubnetCRUD:

    def test_add_and_list_subnets(self, store):
        store.add_subnet(_make_subnet())
        subs = store.list_subnets()
        assert len(subs) == 1
        assert subs[0].cidr == "10.0.0.0/24"

    def test_delete_subnet(self, store):
        store.add_subnet(_make_subnet())
        store.delete_subnet("sub-1")
        assert store.list_subnets() == []

    def test_subnet_upsert(self, store):
        store.add_subnet(_make_subnet(description="old"))
        store.add_subnet(_make_subnet(description="new"))
        subs = store.list_subnets()
        assert len(subs) == 1
        assert subs[0].description == "new"


# ===================================================================
# 4. Route CRUD
# ===================================================================

class TestRouteCRUD:

    def test_add_and_list_routes(self, store):
        store.add_device(_make_device())
        store.add_route(_make_route())
        routes = store.list_routes()
        assert len(routes) == 1
        assert routes[0].destination_cidr == "0.0.0.0/0"
        assert routes[0].next_hop == "10.0.0.254"

    def test_list_routes_filter_by_device(self, store):
        store.add_device(_make_device("dev-1", "r1"))
        store.add_device(_make_device("dev-2", "r2"))
        store.add_route(_make_route("rt-1", "dev-1"))
        store.add_route(_make_route("rt-2", "dev-2", destination_cidr="10.1.0.0/16",
                                    next_hop="10.1.0.1"))
        assert len(store.list_routes(device_id="dev-1")) == 1
        assert len(store.list_routes(device_id="dev-2")) == 1

    def test_bulk_add_routes(self, store):
        store.add_device(_make_device())
        routes = [
            _make_route("rt-1", destination_cidr="10.0.0.0/8", next_hop="10.0.0.1"),
            _make_route("rt-2", destination_cidr="172.16.0.0/12", next_hop="10.0.0.2"),
            _make_route("rt-3", destination_cidr="192.168.0.0/16", next_hop="10.0.0.3"),
        ]
        store.bulk_add_routes(routes)
        assert len(store.list_routes()) == 3

    def test_delete_route(self, store):
        store.add_device(_make_device())
        store.add_route(_make_route())
        store.delete_route("rt-1")
        assert store.list_routes() == []


# ===================================================================
# 5. Zone CRUD
# ===================================================================

class TestZoneCRUD:

    def test_add_and_list_zones(self, store):
        store.add_zone(_make_zone())
        zones = store.list_zones()
        assert len(zones) == 1
        assert zones[0].name == "dmz"

    def test_delete_zone(self, store):
        store.add_zone(_make_zone())
        store.delete_zone("zone-1")
        assert store.list_zones() == []


# ===================================================================
# 6. Firewall Rule CRUD
# ===================================================================

class TestFirewallRuleCRUD:

    def test_add_and_list_firewall_rules(self, store):
        store.add_device(_make_device())
        store.add_firewall_rule(_make_firewall_rule())
        rules = store.list_firewall_rules()
        assert len(rules) == 1
        r = rules[0]
        assert r.rule_name == "deny-all"
        assert r.src_ips == ["10.0.0.0/8"]
        assert r.dst_ips == ["0.0.0.0/0"]
        assert r.ports == [80, 443]
        assert r.action == PolicyAction.DENY
        assert r.logged is True
        assert r.order == 100

    def test_list_firewall_rules_filter_by_device(self, store):
        store.add_device(_make_device("dev-1", "fw1"))
        store.add_device(_make_device("dev-2", "fw2"))
        store.add_firewall_rule(_make_firewall_rule("fw-1", "dev-1"))
        store.add_firewall_rule(_make_firewall_rule("fw-2", "dev-2", rule_name="allow-http"))
        assert len(store.list_firewall_rules(device_id="dev-1")) == 1
        assert len(store.list_firewall_rules(device_id="dev-2")) == 1


# ===================================================================
# 7. NAT Rule CRUD
# ===================================================================

class TestNATRuleCRUD:

    def test_add_and_list_nat_rules(self, store):
        store.add_device(_make_device())
        store.add_nat_rule(_make_nat_rule())
        rules = store.list_nat_rules()
        assert len(rules) == 1
        assert rules[0].original_src == "10.0.0.5"
        assert rules[0].translated_src == "203.0.113.1"
        assert rules[0].direction == NATDirection.SNAT

    def test_list_nat_rules_filter_by_device(self, store):
        store.add_device(_make_device("dev-1", "fw1"))
        store.add_device(_make_device("dev-2", "fw2"))
        store.add_nat_rule(_make_nat_rule("nat-1", "dev-1"))
        store.add_nat_rule(_make_nat_rule("nat-2", "dev-2"))
        assert len(store.list_nat_rules(device_id="dev-1")) == 1
        assert len(store.list_nat_rules(device_id="dev-2")) == 1


# ===================================================================
# 8. HA Group CRUD
# ===================================================================

class TestHAGroupCRUD:

    def test_add_and_get_ha_group(self, store):
        store.add_ha_group(_make_ha_group())
        got = store.get_ha_group("ha-1")
        assert got is not None
        assert got.name == "fw-pair"
        assert got.ha_mode == HAMode.ACTIVE_PASSIVE
        assert got.member_ids == ["dev-1", "dev-2"]
        assert got.virtual_ips == ["10.0.0.100"]
        assert got.active_member_id == "dev-1"
        assert got.priority_map == {"dev-1": 100, "dev-2": 50}
        assert got.sync_interface == "eth3"

    def test_get_ha_group_not_found(self, store):
        assert store.get_ha_group("nonexistent") is None

    def test_list_ha_groups(self, store):
        store.add_ha_group(_make_ha_group("ha-1"))
        store.add_ha_group(_make_ha_group("ha-2", name="sw-cluster",
                                          ha_mode=HAMode.ACTIVE_ACTIVE,
                                          member_ids=["dev-3", "dev-4"],
                                          virtual_ips=[]))
        groups = store.list_ha_groups()
        assert len(groups) == 2

    def test_delete_ha_group(self, store):
        store.add_ha_group(_make_ha_group())
        store.delete_ha_group("ha-1")
        assert store.get_ha_group("ha-1") is None
        assert store.list_ha_groups() == []


# ===================================================================
# 9. VPC CRUD
# ===================================================================

class TestVPCCRUD:

    def test_add_and_get_vpc(self, store):
        store.add_vpc(_make_vpc())
        got = store.get_vpc("vpc-1")
        assert got is not None
        assert got.name == "prod-vpc"
        assert got.cloud_provider == CloudProvider.AWS
        assert got.region == "us-east-1"
        assert got.cidr_blocks == ["10.0.0.0/16"]
        assert got.account_id == "123456789012"

    def test_get_vpc_not_found(self, store):
        assert store.get_vpc("nonexistent") is None

    def test_list_vpcs(self, store):
        store.add_vpc(_make_vpc("vpc-1"))
        store.add_vpc(_make_vpc("vpc-2", name="staging-vpc",
                                region="us-west-2",
                                cidr_blocks=["172.16.0.0/16"]))
        vpcs = store.list_vpcs()
        assert len(vpcs) == 2

    def test_delete_vpc(self, store):
        store.add_vpc(_make_vpc())
        store.delete_vpc("vpc-1")
        assert store.get_vpc("vpc-1") is None
        assert store.list_vpcs() == []


# ===================================================================
# 10. Diagram Snapshot CRUD
# ===================================================================

class TestDiagramSnapshotCRUD:

    def test_save_and_load_latest(self, store):
        snap_data = json.dumps({"nodes": ["a", "b"], "edges": []})
        snap_id = store.save_diagram_snapshot(snap_data, description="initial")
        assert isinstance(snap_id, int)

        loaded = store.load_diagram_snapshot()
        assert loaded is not None
        assert loaded["id"] == snap_id
        assert loaded["snapshot_json"] == snap_data
        assert loaded["description"] == "initial"
        assert loaded["timestamp"]  # non-empty

    def test_load_latest_returns_none_when_empty(self, store):
        assert store.load_diagram_snapshot() is None

    def test_load_by_id(self, store):
        id1 = store.save_diagram_snapshot('{"v":1}', "first")
        id2 = store.save_diagram_snapshot('{"v":2}', "second")
        loaded = store.load_diagram_snapshot_by_id(id1)
        assert loaded is not None
        assert loaded["snapshot_json"] == '{"v":1}'

    def test_load_by_id_not_found(self, store):
        assert store.load_diagram_snapshot_by_id(9999) is None

    def test_list_diagram_snapshots(self, store):
        store.save_diagram_snapshot('{"v":1}', "s1")
        store.save_diagram_snapshot('{"v":2}', "s2")
        store.save_diagram_snapshot('{"v":3}', "s3")
        snaps = store.list_diagram_snapshots(limit=2)
        assert len(snaps) == 2
        # Most recent first
        assert snaps[0]["description"] == "s3"
        assert snaps[1]["description"] == "s2"

    def test_load_latest_returns_most_recent(self, store):
        store.save_diagram_snapshot('{"v":"old"}', "old")
        store.save_diagram_snapshot('{"v":"new"}', "new")
        loaded = store.load_diagram_snapshot()
        assert loaded["description"] == "new"

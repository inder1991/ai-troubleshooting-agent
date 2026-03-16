"""Tests for SQLiteRepository — the adapter wrapping TopologyStore."""

import pytest
from datetime import datetime, timezone

from src.network.topology_store import TopologyStore
from src.network.models import (
    Device as PydanticDevice,
    DeviceType,
    Interface as PydanticInterface,
    Route as PydanticRoute,
    FirewallRule,
    PolicyAction,
)
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.repository.domain import (
    Device,
    Interface,
    IPAddress,
    Route,
    SecurityPolicy,
    NeighborLink,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = TopologyStore(db_path)
    return SQLiteRepository(store)


@pytest.fixture
def seeded_repo(repo):
    store = repo._store

    # Device 1 — router
    store.add_device(PydanticDevice(
        id="dev-1",
        name="core-rtr-01",
        vendor="Cisco",
        device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1",
        model="ISR4451",
        serial_number="FTX1234ABCD",
        site_id="site-east",
    ))

    # Device 2 — firewall
    store.add_device(PydanticDevice(
        id="dev-2",
        name="edge-fw-01",
        vendor="Palo Alto",
        device_type=DeviceType.FIREWALL,
        management_ip="10.0.0.2",
        model="PA-5260",
        serial_number="PA9876WXYZ",
        site_id="site-east",
    ))

    # Interfaces on device 1
    store.add_interface(PydanticInterface(
        id="dev-1:Gi0/0",
        device_id="dev-1",
        name="Gi0/0",
        ip="10.1.1.1",
        mac="00:1A:2B:3C:4D:5E",
        speed="1G",
        status="up",
    ))
    store.add_interface(PydanticInterface(
        id="dev-1:Gi0/1",
        device_id="dev-1",
        name="Gi0/1",
        ip="10.2.2.1",
        mac="00:1A:2B:3C:4D:5F",
        speed="10G",
        status="up",
    ))

    # Route on device 1
    store.add_route(PydanticRoute(
        id="route-1",
        device_id="dev-1",
        destination_cidr="192.168.0.0/16",
        next_hop="10.1.1.254",
        protocol="ospf",
        metric=110,
        vrf="default",
    ))

    # Firewall rule on device 2
    store.add_firewall_rule(FirewallRule(
        id="fw-rule-1",
        device_id="dev-2",
        rule_name="deny-telnet",
        src_zone="outside",
        dst_zone="inside",
        src_ips=["0.0.0.0/0"],
        dst_ips=["10.0.0.0/8"],
        ports=[23],
        protocol="tcp",
        action=PolicyAction.DENY,
        logged=True,
        order=100,
    ))

    return repo


# ── Device read tests ────────────────────────────────────────────────────


class TestGetDevice:
    def test_get_device(self, seeded_repo):
        device = seeded_repo.get_device("dev-1")
        assert device is not None
        assert isinstance(device, Device)
        assert device.id == "dev-1"
        assert device.hostname == "core-rtr-01"
        assert device.vendor == "Cisco"
        assert device.device_type == "router"
        assert device.model == "ISR4451"
        assert device.serial == "FTX1234ABCD"
        assert device.site_id == "site-east"
        assert device.confidence == 0.9
        assert "topology_store" in device.sources
        assert isinstance(device.first_seen, datetime)
        assert isinstance(device.last_seen, datetime)

    def test_get_device_not_found(self, repo):
        assert repo.get_device("nonexistent") is None

    def test_get_devices_all(self, seeded_repo):
        devices = seeded_repo.get_devices()
        assert len(devices) == 2
        assert all(isinstance(d, Device) for d in devices)
        ids = {d.id for d in devices}
        assert ids == {"dev-1", "dev-2"}

    def test_get_devices_by_type(self, seeded_repo):
        routers = seeded_repo.get_devices(device_type="router")
        assert len(routers) == 1
        assert routers[0].hostname == "core-rtr-01"

        firewalls = seeded_repo.get_devices(device_type="firewall")
        assert len(firewalls) == 1
        assert firewalls[0].hostname == "edge-fw-01"

    def test_get_devices_by_site(self, seeded_repo):
        east = seeded_repo.get_devices(site_id="site-east")
        assert len(east) == 2

        west = seeded_repo.get_devices(site_id="site-west")
        assert len(west) == 0


# ── Interface read tests ─────────────────────────────────────────────────


class TestGetInterfaces:
    def test_get_interfaces(self, seeded_repo):
        interfaces = seeded_repo.get_interfaces("dev-1")
        assert len(interfaces) == 2
        assert all(isinstance(i, Interface) for i in interfaces)
        names = {i.name for i in interfaces}
        assert names == {"Gi0/0", "Gi0/1"}
        # Verify field mapping
        gi0 = next(i for i in interfaces if i.name == "Gi0/0")
        assert gi0.device_id == "dev-1"
        assert gi0.mac == "00:1A:2B:3C:4D:5E"
        assert gi0.speed == "1G"

    def test_get_interfaces_empty(self, seeded_repo):
        interfaces = seeded_repo.get_interfaces("nonexistent-device")
        assert interfaces == []


# ── IP address lookup tests ──────────────────────────────────────────────


class TestFindDeviceByIP:
    def test_find_device_by_management_ip(self, seeded_repo):
        device = seeded_repo.find_device_by_ip("10.0.0.1")
        assert device is not None
        assert device.id == "dev-1"

    def test_find_device_by_interface_ip(self, seeded_repo):
        device = seeded_repo.find_device_by_ip("10.1.1.1")
        assert device is not None
        assert device.id == "dev-1"

    def test_find_device_by_ip_not_found(self, seeded_repo):
        assert seeded_repo.find_device_by_ip("192.168.99.99") is None


# ── Serial / hostname lookup tests ───────────────────────────────────────


class TestFindDeviceBySerial:
    def test_find_device_by_serial(self, seeded_repo):
        device = seeded_repo.find_device_by_serial("FTX1234ABCD")
        assert device is not None
        assert device.id == "dev-1"

    def test_find_device_by_serial_not_found(self, seeded_repo):
        assert seeded_repo.find_device_by_serial("DOESNOTEXIST") is None


class TestFindDeviceByHostname:
    def test_find_device_by_hostname(self, seeded_repo):
        device = seeded_repo.find_device_by_hostname("edge-fw-01")
        assert device is not None
        assert device.id == "dev-2"

    def test_find_device_by_hostname_not_found(self, seeded_repo):
        assert seeded_repo.find_device_by_hostname("ghost") is None


# ── Route read tests ─────────────────────────────────────────────────────


class TestGetRoutes:
    def test_get_routes(self, seeded_repo):
        routes = seeded_repo.get_routes("dev-1")
        assert len(routes) == 1
        r = routes[0]
        assert isinstance(r, Route)
        assert r.device_id == "dev-1"
        assert r.destination_cidr == "192.168.0.0/16"
        assert r.protocol == "ospf"

    def test_get_routes_empty(self, seeded_repo):
        routes = seeded_repo.get_routes("dev-2")
        assert routes == []


# ── Security policy read tests ───────────────────────────────────────────


class TestGetSecurityPolicies:
    def test_get_security_policies(self, seeded_repo):
        policies = seeded_repo.get_security_policies("dev-2")
        assert len(policies) == 1
        p = policies[0]
        assert isinstance(p, SecurityPolicy)
        assert p.device_id == "dev-2"
        assert p.name == "deny-telnet"
        assert p.action == "deny"
        assert p.src_zone == "outside"
        assert p.dst_zone == "inside"
        assert p.rule_order == 100

    def test_get_security_policies_empty(self, seeded_repo):
        policies = seeded_repo.get_security_policies("dev-1")
        assert policies == []


# ── Neighbor stubs ───────────────────────────────────────────────────────


class TestGetNeighbors:
    def test_get_neighbors_returns_empty(self, seeded_repo):
        assert seeded_repo.get_neighbors("dev-1") == []


# ── IP address from interface ────────────────────────────────────────────


class TestGetIPAddresses:
    def test_get_ip_addresses(self, seeded_repo):
        ips = seeded_repo.get_ip_addresses("dev-1:Gi0/0")
        assert len(ips) == 1
        ip = ips[0]
        assert isinstance(ip, IPAddress)
        assert ip.ip == "10.1.1.1"
        assert ip.assigned_to == "dev-1:Gi0/0"

    def test_get_ip_addresses_no_interface(self, repo):
        assert repo.get_ip_addresses("nonexistent") == []


# ── Graph query stubs ────────────────────────────────────────────────────


class TestGraphQueryStubs:
    def test_find_paths_returns_empty(self, repo):
        assert repo.find_paths("10.0.0.1", "10.0.0.2") == []

    def test_blast_radius_returns_empty(self, repo):
        assert repo.blast_radius("dev-1") == {}

    def test_get_topology_export_returns_empty(self, repo):
        assert repo.get_topology_export() == {}


# ── Write operations ─────────────────────────────────────────────────────


class TestWriteOperations:
    def test_upsert_device(self, repo):
        now = datetime.now(timezone.utc)
        device = Device(
            id="dev-new",
            hostname="new-switch-01",
            vendor="Arista",
            model="7050X",
            serial="AR1234",
            device_type="switch",
            site_id="site-west",
            sources=["topology_store"],
            first_seen=now,
            last_seen=now,
            confidence=0.9,
        )
        result = repo.upsert_device(device)
        assert result.id == "dev-new"

        # Verify it persisted
        fetched = repo.get_device("dev-new")
        assert fetched is not None
        assert fetched.hostname == "new-switch-01"
        assert fetched.vendor == "Arista"

    def test_upsert_interface(self, repo):
        # Need a device first
        now = datetime.now(timezone.utc)
        repo.upsert_device(Device(
            id="dev-x", hostname="x", vendor="", model="", serial="",
            device_type="host", site_id="", sources=["topology_store"],
            first_seen=now, last_seen=now, confidence=0.9,
        ))
        iface = Interface(
            id="dev-x:eth0", device_id="dev-x", name="eth0",
            sources=["topology_store"], first_seen=now, last_seen=now,
            confidence=0.9, mac="AA:BB:CC:DD:EE:FF",
        )
        result = repo.upsert_interface(iface)
        assert result.id == "dev-x:eth0"

        fetched = repo.get_interfaces("dev-x")
        assert len(fetched) == 1
        assert fetched[0].name == "eth0"

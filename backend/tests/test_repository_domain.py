"""Tests for canonical domain models in src.network.repository.domain."""

from datetime import datetime, timezone

from src.network.repository.domain import (
    Device,
    Interface,
    IPAddress,
    NeighborLink,
    NATRule,
    Route,
    SecurityPolicy,
    Site,
    Subnet,
    VLAN,
    VRFInstance,
    Zone,
)

NOW = datetime.now(timezone.utc)


# ── Device ──────────────────────────────────────────────────────────────────


class TestDevice:
    def test_create_device(self):
        d = Device(
            id="dev-001",
            hostname="spine-01.dc1",
            vendor="Arista",
            model="7050X",
            serial="ABC123",
            device_type="switch",
            site_id="site-dc1",
            sources=["snmp", "lldp"],
            first_seen=NOW,
            last_seen=NOW,
            confidence=0.95,
        )
        assert d.id == "dev-001"
        assert d.hostname == "spine-01.dc1"
        assert d.vendor == "Arista"
        assert d.model == "7050X"
        assert d.serial == "ABC123"
        assert d.device_type == "switch"
        assert d.site_id == "site-dc1"
        assert d.sources == ["snmp", "lldp"]
        assert d.confidence == 0.95

    def test_device_defaults(self):
        d = Device(
            id="dev-002",
            hostname="leaf-01",
            vendor="Cisco",
            model="N9K",
            serial="XYZ",
            device_type="switch",
            site_id="site-1",
            sources=["snmp"],
            first_seen=NOW,
            last_seen=NOW,
            confidence=0.8,
        )
        assert d.managed_by is None
        assert d.mode is None
        assert d.ha_mode is None
        assert d.state_sync is False


# ── Interface ───────────────────────────────────────────────────────────────


class TestInterface:
    def test_stable_id_format(self):
        iface = Interface(
            id="dev-001:Ethernet1",
            device_id="dev-001",
            name="Ethernet1",
            sources=["snmp"],
            first_seen=NOW,
            last_seen=NOW,
            confidence=0.9,
        )
        assert iface.id == "dev-001:Ethernet1"
        assert ":" in iface.id
        parts = iface.id.split(":", 1)
        assert parts[0] == iface.device_id
        assert parts[1] == iface.name

    def test_interface_defaults(self):
        iface = Interface(
            id="dev-001:Ethernet2",
            device_id="dev-001",
            name="Ethernet2",
            sources=["snmp"],
            first_seen=NOW,
            last_seen=NOW,
            confidence=0.9,
        )
        assert iface.mac is None
        assert iface.admin_state == "up"
        assert iface.oper_state == "up"
        assert iface.speed is None
        assert iface.mtu is None
        assert iface.duplex is None
        assert iface.port_channel_id is None
        assert iface.description is None
        assert iface.vrf_instance_id is None
        assert iface.vlan_membership == []


# ── IPAddress ───────────────────────────────────────────────────────────────


class TestIPAddress:
    def test_create_ip(self):
        ip = IPAddress(
            id="10.0.0.1",
            ip="10.0.0.1",
            assigned_to="dev-001:Ethernet1",
            sources=["ipam"],
            first_seen=NOW,
            last_seen=NOW,
            confidence=1.0,
        )
        assert ip.ip == "10.0.0.1"
        assert ip.assigned_to == "dev-001:Ethernet1"
        assert ip.prefix_len is None
        assert ip.assigned_from is None
        assert ip.lease_ts is None


# ── NeighborLink ────────────────────────────────────────────────────────────


class TestNeighborLink:
    def test_create_neighbor(self):
        link = NeighborLink(
            id="link-001",
            device_id="dev-001",
            local_interface="dev-001:Ethernet1",
            remote_device="dev-002",
            remote_interface="dev-002:Ethernet1",
            protocol="lldp",
            sources=["lldp"],
            first_seen=NOW,
            last_seen=NOW,
            confidence=0.99,
        )
        assert link.protocol == "lldp"
        assert link.local_interface == "dev-001:Ethernet1"
        assert link.remote_device == "dev-002"
        assert link.remote_interface == "dev-002:Ethernet1"
        assert link.confidence == 0.99


# ── VRFInstance ─────────────────────────────────────────────────────────────


class TestVRFInstance:
    def test_create_vrf_instance(self):
        vrf = VRFInstance(
            id="dev-001:PROD",
            vrf_id="vrf-prod",
            device_id="dev-001",
            sources=["config"],
            first_seen=NOW,
            last_seen=NOW,
        )
        assert vrf.id == "dev-001:PROD"
        assert vrf.vrf_id == "vrf-prod"
        assert vrf.device_id == "dev-001"
        assert vrf.table_id is None


# ── Route ───────────────────────────────────────────────────────────────────


class TestRoute:
    def test_create_route_with_ecmp(self):
        ecmp_hops = [
            {"type": "interface", "ref": "dev-001:Ethernet1", "weight": 1},
            {"type": "interface", "ref": "dev-001:Ethernet2", "weight": 1},
        ]
        route = Route(
            id="route-001",
            device_id="dev-001",
            vrf_instance_id="dev-001:PROD",
            destination_cidr="10.0.0.0/24",
            prefix_len=24,
            protocol="bgp",
            sources=["config"],
            first_seen=NOW,
            last_seen=NOW,
            next_hop_refs=ecmp_hops,
        )
        assert route.destination_cidr == "10.0.0.0/24"
        assert route.prefix_len == 24
        assert route.protocol == "bgp"
        assert len(route.next_hop_refs) == 2
        assert route.next_hop_refs[0]["ref"] == "dev-001:Ethernet1"
        assert route.admin_distance is None
        assert route.metric is None
        assert route.next_hop_type is None

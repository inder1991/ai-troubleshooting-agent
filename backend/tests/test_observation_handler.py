"""Tests for ObservationHandler — routes observations to repo upserts."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.network.repository.domain import Device, Interface, NeighborLink, Route
from src.network.discovery.observation import DiscoveryObservation, ObservationType
from src.network.discovery.entity_resolver import EntityResolver
from src.network.discovery.observation_handler import ObservationHandler


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_repo() -> MagicMock:
    """Return a mock TopologyRepository with sensible defaults."""
    repo = MagicMock()
    repo.find_device_by_serial.return_value = None
    repo.find_device_by_ip.return_value = None
    repo.find_device_by_hostname.return_value = None
    repo.get_device.return_value = None
    # upsert methods return whatever is passed in
    repo.upsert_device.side_effect = lambda d: d
    repo.upsert_interface.side_effect = lambda i: i
    repo.upsert_neighbor_link.side_effect = lambda l: l
    repo.upsert_route.side_effect = lambda r: r
    return repo


def _make_device(device_id: str = "dev-1", hostname: str = "sw-core-1") -> Device:
    now = datetime.now(timezone.utc)
    return Device(
        id=device_id, hostname=hostname, vendor="Cisco", model="Nexus9000",
        serial="SN001", device_type="switch", site_id="dc-east",
        sources=["lldp"], first_seen=now, last_seen=now, confidence=0.95,
    )


# ── Tests ────────────────────────────────────────────────────────────────────

def test_handle_device_observation():
    """DEVICE observation creates/updates a device in the repo."""
    repo = _make_repo()
    resolver = EntityResolver(repo)
    handler = ObservationHandler(repo, resolver)

    obs = DiscoveryObservation(
        observation_type=ObservationType.DEVICE,
        source="lldp",
        device_id="sw-core-1",
        data={
            "hostname": "sw-core-1",
            "vendor": "Cisco",
            "model": "Nexus9000",
            "serial": "SN-TEST-001",
            "device_type": "switch",
            "site_id": "dc-east",
        },
        confidence=0.95,
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
    handler.handle(obs)

    repo.upsert_device.assert_called_once()
    device_arg = repo.upsert_device.call_args[0][0]
    assert isinstance(device_arg, Device)
    assert device_arg.hostname == "sw-core-1"
    assert device_arg.vendor == "Cisco"


def test_handle_interface_observation():
    """INTERFACE observation creates an interface after resolving device."""
    repo = _make_repo()
    existing = _make_device(device_id="dev-1")
    repo.get_device.return_value = existing

    resolver = EntityResolver(repo)
    handler = ObservationHandler(repo, resolver)

    obs = DiscoveryObservation(
        observation_type=ObservationType.INTERFACE,
        source="snmp",
        device_id="dev-1",
        data={
            "name": "GigabitEthernet0/1",
            "admin_state": "up",
            "oper_state": "up",
            "speed": "1G",
            "mtu": 9000,
        },
        confidence=0.90,
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
    handler.handle(obs)

    repo.upsert_interface.assert_called_once()
    iface_arg = repo.upsert_interface.call_args[0][0]
    assert isinstance(iface_arg, Interface)
    assert iface_arg.name == "GigabitEthernet0/1"
    assert iface_arg.device_id == "dev-1"
    assert iface_arg.id == "dev-1:GigabitEthernet0/1"


def test_handle_neighbor_observation():
    """NEIGHBOR observation creates a neighbor link between two devices."""
    repo = _make_repo()
    dev_a = _make_device(device_id="dev-a", hostname="sw-a")
    dev_b = _make_device(device_id="dev-b", hostname="sw-b")

    def mock_get_device(did):
        return {"dev-a": dev_a, "dev-b": dev_b}.get(did)

    repo.get_device.side_effect = mock_get_device

    resolver = EntityResolver(repo)
    handler = ObservationHandler(repo, resolver)

    obs = DiscoveryObservation(
        observation_type=ObservationType.NEIGHBOR,
        source="lldp",
        device_id="dev-a",
        data={
            "local_interface": "Ethernet1/1",
            "remote_device": "dev-b",
            "remote_interface": "Ethernet1/2",
            "protocol": "lldp",
        },
        confidence=0.95,
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
    handler.handle(obs)

    repo.upsert_neighbor_link.assert_called_once()
    link_arg = repo.upsert_neighbor_link.call_args[0][0]
    assert isinstance(link_arg, NeighborLink)
    assert link_arg.device_id == "dev-a"
    assert link_arg.remote_device == "dev-b"


def test_handle_unknown_type_no_crash():
    """ARP_ENTRY observation (not yet handled) logs but doesn't crash."""
    repo = _make_repo()
    resolver = EntityResolver(repo)
    handler = ObservationHandler(repo, resolver)

    obs = DiscoveryObservation(
        observation_type=ObservationType.ARP_ENTRY,
        source="snmp",
        device_id="dev-1",
        data={"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:ff"},
        confidence=0.80,
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
    # Should not raise
    handler.handle(obs)

    # No upsert calls for unhandled types
    repo.upsert_device.assert_not_called()
    repo.upsert_interface.assert_not_called()
    repo.upsert_neighbor_link.assert_not_called()
    repo.upsert_route.assert_not_called()

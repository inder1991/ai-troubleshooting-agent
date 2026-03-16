"""Tests for EntityResolver — canonical identity resolution for network entities."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.network.repository.domain import Device
from src.network.discovery.entity_resolver import EntityResolver, SOURCE_CONFIDENCE


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_repo() -> MagicMock:
    """Return a mock TopologyRepository."""
    repo = MagicMock()
    repo.find_device_by_serial.return_value = None
    repo.find_device_by_ip.return_value = None
    repo.find_device_by_hostname.return_value = None
    repo.get_device.return_value = None
    return repo


def _make_device(device_id: str = "dev-1", hostname: str = "sw-core-1",
                 serial: str = "SN123") -> Device:
    now = datetime.now(timezone.utc)
    return Device(
        id=device_id,
        hostname=hostname,
        vendor="Cisco",
        model="Nexus9000",
        serial=serial,
        device_type="switch",
        site_id="dc-east",
        sources=["lldp"],
        first_seen=now,
        last_seen=now,
        confidence=0.95,
    )


# ── Tests ────────────────────────────────────────────────────────────────────

def test_resolve_by_serial():
    """Device with matching serial returns existing device ID."""
    repo = _make_repo()
    existing = _make_device(device_id="dev-serial-match", serial="ABC123")
    repo.find_device_by_serial.return_value = existing

    resolver = EntityResolver(repo)
    obs = {"serial": "ABC123", "hostname": "unknown"}
    result = resolver.resolve_device(obs)

    assert result == "dev-serial-match"
    repo.find_device_by_serial.assert_called_once_with("ABC123")


def test_resolve_by_management_ip():
    """Device with matching management_ip returns existing device ID."""
    repo = _make_repo()
    existing = _make_device(device_id="dev-ip-match")
    repo.find_device_by_ip.return_value = existing

    resolver = EntityResolver(repo)
    obs = {"management_ip": "10.0.0.1"}
    result = resolver.resolve_device(obs)

    assert result == "dev-ip-match"
    repo.find_device_by_ip.assert_called_once_with("10.0.0.1")


def test_resolve_by_hostname():
    """Device with matching hostname returns existing device ID."""
    repo = _make_repo()
    existing = _make_device(device_id="dev-host-match", hostname="spine-1")
    repo.find_device_by_hostname.return_value = existing

    resolver = EntityResolver(repo)
    obs = {"hostname": "spine-1"}
    result = resolver.resolve_device(obs)

    assert result == "dev-host-match"
    repo.find_device_by_hostname.assert_called_once_with("spine-1")


def test_resolve_unknown_creates_new():
    """Observation with no matching identifiers returns a new UUID-based ID."""
    repo = _make_repo()
    resolver = EntityResolver(repo)
    obs = {"hostname": "mystery-box"}
    result = resolver.resolve_device(obs)

    # Should return a string (new ID), not None, and not match any seeded device
    assert isinstance(result, str)
    assert len(result) > 0
    # Should not match our fixture IDs
    assert result not in ("dev-serial-match", "dev-ip-match", "dev-host-match")


def test_resolve_interface_id():
    """resolve_interface returns 'device_id:iface_name' format."""
    repo = _make_repo()
    resolver = EntityResolver(repo)
    result = resolver.resolve_interface("sw-core-1", "GigabitEthernet0/1")
    assert result == "sw-core-1:GigabitEthernet0/1"


def test_source_confidence_values():
    """SOURCE_CONFIDENCE dict has expected values."""
    assert SOURCE_CONFIDENCE["manual"] == 1.0
    assert SOURCE_CONFIDENCE["lldp"] == 0.95
    assert SOURCE_CONFIDENCE["snmp"] == 0.90
    assert SOURCE_CONFIDENCE["netflow"] == 0.70


def test_get_confidence_known_source():
    """get_confidence returns mapped value for known source."""
    repo = _make_repo()
    resolver = EntityResolver(repo)
    assert resolver.get_confidence("lldp") == 0.95
    assert resolver.get_confidence("manual") == 1.0


def test_get_confidence_unknown_source():
    """get_confidence returns a default for unknown sources."""
    repo = _make_repo()
    resolver = EntityResolver(repo)
    result = resolver.get_confidence("unknown_source_xyz")
    assert isinstance(result, float)
    assert 0.0 < result < 1.0

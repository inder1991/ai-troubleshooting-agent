"""Tests for TopologyValidator — duplicate IPs, orphan interfaces, subnet overlaps."""

from datetime import datetime, timezone

import pytest

from src.network.repository.domain import Device, Interface, IPAddress, Route, Subnet
from src.network.repository.validation import TopologyValidator

NOW = datetime.now(timezone.utc)


def _make_device(id: str = "dev-1") -> Device:
    return Device(
        id=id,
        hostname=f"{id}.example.com",
        vendor="Cisco",
        model="Catalyst 9300",
        serial="SN001",
        device_type="switch",
        site_id="site-1",
        sources=["snmp"],
        first_seen=NOW,
        last_seen=NOW,
        confidence=1.0,
    )


def _make_interface(id: str = "dev-1:eth0", device_id: str = "dev-1") -> Interface:
    return Interface(
        id=id,
        device_id=device_id,
        name=id.split(":")[-1] if ":" in id else "eth0",
        sources=["snmp"],
        first_seen=NOW,
        last_seen=NOW,
        confidence=1.0,
    )


def _make_ip(id: str = "ip-1", ip: str = "10.0.0.1", assigned_to: str = "dev-1:eth0") -> IPAddress:
    return IPAddress(
        id=id,
        ip=ip,
        assigned_to=assigned_to,
        sources=["snmp"],
        first_seen=NOW,
        last_seen=NOW,
        confidence=1.0,
    )


def _make_subnet(id: str = "sub-1", cidr: str = "10.0.0.0/24") -> Subnet:
    return Subnet(
        id=id,
        cidr=cidr,
        sources=["ipam"],
        first_seen=NOW,
        last_seen=NOW,
    )


@pytest.fixture
def validator() -> TopologyValidator:
    return TopologyValidator()


# ── Duplicate IP tests ─────────────────────────────────────────────────


def test_detect_duplicate_ips(validator: TopologyValidator) -> None:
    ips = [
        _make_ip("ip-1", "10.0.0.1", "dev-1:eth0"),
        _make_ip("ip-2", "10.0.0.1", "dev-2:eth0"),
    ]
    issues = validator.check_duplicate_ips(ips)
    assert len(issues) == 1
    assert issues[0]["type"] == "duplicate_ip"
    assert issues[0]["severity"] == "critical"
    assert issues[0]["ip"] == "10.0.0.1"
    assert set(issues[0]["assigned_to"]) == {"dev-1:eth0", "dev-2:eth0"}
    assert "message" in issues[0]


def test_no_duplicate_ips(validator: TopologyValidator) -> None:
    ips = [
        _make_ip("ip-1", "10.0.0.1", "dev-1:eth0"),
        _make_ip("ip-2", "10.0.0.2", "dev-2:eth0"),
    ]
    issues = validator.check_duplicate_ips(ips)
    assert len(issues) == 0


# ── Orphan interface tests ─────────────────────────────────────────────


def test_detect_orphan_interfaces(validator: TopologyValidator) -> None:
    devices = [_make_device("dev-1")]
    interfaces = [_make_interface("ghost-dev:eth0", device_id="ghost-dev")]
    issues = validator.check_orphan_interfaces(devices, interfaces)
    assert len(issues) == 1
    assert issues[0]["type"] == "orphan_interface"
    assert issues[0]["severity"] == "high"
    assert issues[0]["interface_id"] == "ghost-dev:eth0"
    assert issues[0]["device_id"] == "ghost-dev"
    assert "message" in issues[0]


# ── Subnet overlap tests ──────────────────────────────────────────────


def test_detect_subnet_overlap(validator: TopologyValidator) -> None:
    subnets = [
        _make_subnet("sub-1", "10.0.0.0/24"),
        _make_subnet("sub-2", "10.0.0.0/25"),
    ]
    issues = validator.check_subnet_overlaps(subnets)
    assert len(issues) == 1
    assert issues[0]["type"] == "subnet_overlap"
    assert issues[0]["severity"] == "high"
    assert issues[0]["subnet_a"] == "sub-1"
    assert issues[0]["subnet_b"] == "sub-2"
    assert issues[0]["cidr_a"] == "10.0.0.0/24"
    assert issues[0]["cidr_b"] == "10.0.0.0/25"
    assert "message" in issues[0]


def test_no_subnet_overlap(validator: TopologyValidator) -> None:
    subnets = [
        _make_subnet("sub-1", "10.0.0.0/24"),
        _make_subnet("sub-2", "10.0.1.0/24"),
    ]
    issues = validator.check_subnet_overlaps(subnets)
    assert len(issues) == 0


# ── Full validation test ──────────────────────────────────────────────


def test_full_validation(validator: TopologyValidator) -> None:
    result = validator.validate(
        devices=[],
        interfaces=[],
        ip_addresses=[],
        subnets=[],
        routes=[],
    )
    assert result["issues"] == []
    assert result["issue_count"] == 0
    assert result["critical"] == 0
    assert result["high"] == 0
    assert result["medium"] == 0

"""Tests for multi-interface validation rules 29, 30, 31."""
import pytest
from src.network.interface_validation import validate_device_interfaces
from src.network.models import Interface, Subnet, Zone


@pytest.fixture
def subnet_10():
    return Subnet(id="s1", cidr="10.0.1.0/24")


@pytest.fixture
def subnet_192():
    return Subnet(id="s2", cidr="192.168.1.0/24")


@pytest.fixture
def mgmt_zone():
    return Zone(id="z-mgmt", name="management", zone_type="management")


@pytest.fixture
def data_zone():
    return Zone(id="z-data", name="production", zone_type="data")


@pytest.fixture
def dmz_zone():
    return Zone(id="z-dmz", name="dmz", zone_type="dmz")


class TestRule29_IPInSubnet:
    def test_ip_within_subnet_passes(self, subnet_10):
        ifaces = [Interface(id="i1", device_id="d1", name="eth0",
                            ip="10.0.1.5", subnet_id="s1", role="inside")]
        errors = validate_device_interfaces("d1", ifaces, [subnet_10], [])
        assert not any(e["rule"] == 29 for e in errors)

    def test_ip_outside_subnet_fails(self, subnet_10):
        ifaces = [Interface(id="i1", device_id="d1", name="eth0",
                            ip="10.0.2.5", subnet_id="s1", role="inside")]
        errors = validate_device_interfaces("d1", ifaces, [subnet_10], [])
        rule29 = [e for e in errors if e["rule"] == 29]
        assert len(rule29) == 1
        assert "10.0.2.5" in rule29[0]["message"]

    def test_no_subnet_id_skips_check(self):
        ifaces = [Interface(id="i1", device_id="d1", name="eth0",
                            ip="10.0.1.5", role="inside")]
        errors = validate_device_interfaces("d1", ifaces, [], [])
        assert not any(e["rule"] == 29 for e in errors)

    def test_empty_ip_skips_check(self, subnet_10):
        ifaces = [Interface(id="i1", device_id="d1", name="eth0",
                            subnet_id="s1", role="inside")]
        errors = validate_device_interfaces("d1", ifaces, [subnet_10], [])
        assert not any(e["rule"] == 29 for e in errors)


class TestRule30_NoZoneOverlap:
    def test_different_zones_passes(self):
        ifaces = [
            Interface(id="i1", device_id="d1", name="eth0",
                      ip="10.0.1.1", zone_id="z-inside", role="inside"),
            Interface(id="i2", device_id="d1", name="eth1",
                      ip="10.0.2.1", zone_id="z-outside", role="outside"),
        ]
        errors = validate_device_interfaces("d1", ifaces, [], [])
        assert not any(e["rule"] == 30 for e in errors)

    def test_same_zone_fails(self):
        ifaces = [
            Interface(id="i1", device_id="d1", name="eth0",
                      ip="10.0.1.1", zone_id="z-inside", role="inside"),
            Interface(id="i2", device_id="d1", name="eth1",
                      ip="10.0.1.2", zone_id="z-inside", role="outside"),
        ]
        errors = validate_device_interfaces("d1", ifaces, [], [])
        rule30 = [e for e in errors if e["rule"] == 30]
        assert len(rule30) == 1

    def test_sync_role_exempt_from_zone_overlap(self):
        ifaces = [
            Interface(id="i1", device_id="d1", name="eth0",
                      ip="10.0.1.1", zone_id="z-inside", role="inside"),
            Interface(id="i2", device_id="d1", name="sync0",
                      ip="10.0.1.2", zone_id="z-inside", role="sync"),
        ]
        errors = validate_device_interfaces("d1", ifaces, [], [])
        assert not any(e["rule"] == 30 for e in errors)

    def test_empty_zone_skipped(self):
        ifaces = [
            Interface(id="i1", device_id="d1", name="eth0",
                      ip="10.0.1.1", zone_id="", role="inside"),
            Interface(id="i2", device_id="d1", name="eth1",
                      ip="10.0.2.1", zone_id="", role="outside"),
        ]
        errors = validate_device_interfaces("d1", ifaces, [], [])
        assert not any(e["rule"] == 30 for e in errors)


class TestRule31_MgmtNotInDataPlane:
    def test_mgmt_in_mgmt_zone_passes(self, mgmt_zone):
        ifaces = [Interface(id="i1", device_id="d1", name="mgmt0",
                            ip="10.0.1.1", zone_id="z-mgmt", role="management")]
        errors = validate_device_interfaces("d1", ifaces, [], [mgmt_zone])
        assert not any(e["rule"] == 31 for e in errors)

    def test_mgmt_in_data_zone_warns(self, data_zone):
        ifaces = [Interface(id="i1", device_id="d1", name="mgmt0",
                            ip="10.0.1.1", zone_id="z-data", role="management")]
        errors = validate_device_interfaces("d1", ifaces, [], [data_zone])
        rule31 = [e for e in errors if e["rule"] == 31]
        assert len(rule31) == 1
        assert rule31[0]["severity"] == "warning"

    def test_mgmt_in_dmz_zone_warns(self, dmz_zone):
        ifaces = [Interface(id="i1", device_id="d1", name="mgmt0",
                            ip="10.0.1.1", zone_id="z-dmz", role="management")]
        errors = validate_device_interfaces("d1", ifaces, [], [dmz_zone])
        rule31 = [e for e in errors if e["rule"] == 31]
        assert len(rule31) == 1

    def test_non_mgmt_role_in_data_zone_ok(self, data_zone):
        ifaces = [Interface(id="i1", device_id="d1", name="eth0",
                            ip="10.0.1.1", zone_id="z-data", role="inside")]
        errors = validate_device_interfaces("d1", ifaces, [], [data_zone])
        assert not any(e["rule"] == 31 for e in errors)

    def test_mgmt_in_unclassified_zone_ok(self):
        unclassified = Zone(id="z-x", name="legacy", zone_type="")
        ifaces = [Interface(id="i1", device_id="d1", name="mgmt0",
                            ip="10.0.1.1", zone_id="z-x", role="management")]
        errors = validate_device_interfaces("d1", ifaces, [], [unclassified])
        assert not any(e["rule"] == 31 for e in errors)

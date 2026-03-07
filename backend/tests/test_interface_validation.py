"""Unit tests for interface validation rules in interface_validation.py.

Rules tested:
  29 - IP must be within assigned subnet CIDR
  30 - No two non-sync interfaces may share a zone
  31 - Management interface should not be in a data/dmz zone
  32 - Device VLAN should match subnet VLAN
"""
from src.network.models import Interface, Subnet, Zone
from src.network.interface_validation import validate_device_interfaces


# ── helpers ──

def _iface(iface_id: str, *, ip: str = "", subnet_id: str = "",
           zone_id: str = "", role: str = "", name: str = "") -> Interface:
    return Interface(
        id=iface_id, device_id="dev1",
        name=name or f"eth-{iface_id}",
        ip=ip, subnet_id=subnet_id, zone_id=zone_id, role=role,
    )


def _subnet(subnet_id: str, cidr: str, vlan_id: int = 0) -> Subnet:
    return Subnet(id=subnet_id, cidr=cidr, vlan_id=vlan_id)


def _zone(zone_id: str, name: str, zone_type: str = "") -> Zone:
    return Zone(id=zone_id, name=name, zone_type=zone_type)


class TestRule29IPInSubnet:
    """Rule 29: Interface IP must be within its assigned subnet CIDR."""

    def test_ip_outside_subnet_produces_error(self):
        ifaces = [_iface("i1", ip="192.168.1.50", subnet_id="s1")]
        subnets = [_subnet("s1", "10.0.0.0/24")]

        errors = validate_device_interfaces("dev1", ifaces, subnets, [])
        rule29 = [e for e in errors if e["rule"] == 29]
        assert len(rule29) == 1
        assert rule29[0]["severity"] == "error"
        assert rule29[0]["interface_id"] == "i1"

    def test_ip_inside_subnet_no_error(self):
        ifaces = [_iface("i1", ip="10.0.0.5", subnet_id="s1")]
        subnets = [_subnet("s1", "10.0.0.0/24")]

        errors = validate_device_interfaces("dev1", ifaces, subnets, [])
        rule29 = [e for e in errors if e["rule"] == 29]
        assert len(rule29) == 0

    def test_interface_without_ip_skipped(self):
        """An interface with no IP should not trigger rule 29."""
        ifaces = [_iface("i1", ip="", subnet_id="s1")]
        subnets = [_subnet("s1", "10.0.0.0/24")]

        errors = validate_device_interfaces("dev1", ifaces, subnets, [])
        rule29 = [e for e in errors if e["rule"] == 29]
        assert len(rule29) == 0

    def test_interface_without_subnet_skipped(self):
        """An interface with no subnet_id should not trigger rule 29."""
        ifaces = [_iface("i1", ip="10.0.0.5", subnet_id="")]
        subnets = [_subnet("s1", "10.0.0.0/24")]

        errors = validate_device_interfaces("dev1", ifaces, subnets, [])
        rule29 = [e for e in errors if e["rule"] == 29]
        assert len(rule29) == 0

    def test_missing_subnet_reference_no_crash(self):
        """If subnet_id points to a subnet not in the list, no crash occurs."""
        ifaces = [_iface("i1", ip="10.0.0.5", subnet_id="s_missing")]
        subnets = [_subnet("s1", "10.0.0.0/24")]

        errors = validate_device_interfaces("dev1", ifaces, subnets, [])
        rule29 = [e for e in errors if e["rule"] == 29]
        assert len(rule29) == 0  # silently skipped, no crash


class TestRule30DuplicateZone:
    """Rule 30: No two non-sync interfaces may share a zone on same device."""

    def test_duplicate_zone_non_sync_produces_error(self):
        ifaces = [
            _iface("i1", zone_id="z1", role="inside"),
            _iface("i2", zone_id="z1", role="outside"),
        ]
        errors = validate_device_interfaces("dev1", ifaces, [], [])
        rule30 = [e for e in errors if e["rule"] == 30]
        assert len(rule30) == 1
        assert rule30[0]["severity"] == "error"

    def test_sync_interfaces_exempt_from_zone_check(self):
        ifaces = [
            _iface("i1", zone_id="z1", role="inside"),
            _iface("i2", zone_id="z1", role="sync"),
        ]
        errors = validate_device_interfaces("dev1", ifaces, [], [])
        rule30 = [e for e in errors if e["rule"] == 30]
        assert len(rule30) == 0

    def test_different_zones_no_error(self):
        ifaces = [
            _iface("i1", zone_id="z1", role="inside"),
            _iface("i2", zone_id="z2", role="outside"),
        ]
        errors = validate_device_interfaces("dev1", ifaces, [], [])
        rule30 = [e for e in errors if e["rule"] == 30]
        assert len(rule30) == 0


class TestRule31ManagementZone:
    """Rule 31: Management interface should not be in a data or dmz zone."""

    def test_management_in_data_zone_warning(self):
        ifaces = [_iface("i1", zone_id="z1", role="management")]
        zones = [_zone("z1", "DataNet", zone_type="data")]

        errors = validate_device_interfaces("dev1", ifaces, [], zones)
        rule31 = [e for e in errors if e["rule"] == 31]
        assert len(rule31) == 1
        assert rule31[0]["severity"] == "warning"

    def test_management_in_dmz_zone_warning(self):
        ifaces = [_iface("i1", zone_id="z1", role="management")]
        zones = [_zone("z1", "DMZ", zone_type="dmz")]

        errors = validate_device_interfaces("dev1", ifaces, [], zones)
        rule31 = [e for e in errors if e["rule"] == 31]
        assert len(rule31) == 1
        assert rule31[0]["severity"] == "warning"

    def test_management_in_management_zone_ok(self):
        ifaces = [_iface("i1", zone_id="z1", role="management")]
        zones = [_zone("z1", "Mgmt", zone_type="management")]

        errors = validate_device_interfaces("dev1", ifaces, [], zones)
        rule31 = [e for e in errors if e["rule"] == 31]
        assert len(rule31) == 0

    def test_non_management_role_in_data_zone_ok(self):
        """Rule 31 only applies to management interfaces."""
        ifaces = [_iface("i1", zone_id="z1", role="inside")]
        zones = [_zone("z1", "DataNet", zone_type="data")]

        errors = validate_device_interfaces("dev1", ifaces, [], zones)
        rule31 = [e for e in errors if e["rule"] == 31]
        assert len(rule31) == 0


class TestRule32VLANMismatch:
    """Rule 32: Device VLAN should match subnet VLAN."""

    def test_vlan_mismatch_produces_warning(self):
        ifaces = [_iface("i1", ip="10.0.0.5", subnet_id="s1")]
        subnets = [_subnet("s1", "10.0.0.0/24", vlan_id=100)]

        errors = validate_device_interfaces("dev1", ifaces, subnets, [],
                                            device_vlan_id=200)
        rule32 = [e for e in errors if e["rule"] == 32]
        assert len(rule32) == 1
        assert rule32[0]["severity"] == "warning"

    def test_vlan_match_no_warning(self):
        ifaces = [_iface("i1", ip="10.0.0.5", subnet_id="s1")]
        subnets = [_subnet("s1", "10.0.0.0/24", vlan_id=100)]

        errors = validate_device_interfaces("dev1", ifaces, subnets, [],
                                            device_vlan_id=100)
        rule32 = [e for e in errors if e["rule"] == 32]
        assert len(rule32) == 0

    def test_no_device_vlan_skips_rule(self):
        """When device_vlan_id is 0 (default), rule 32 is skipped entirely."""
        ifaces = [_iface("i1", ip="10.0.0.5", subnet_id="s1")]
        subnets = [_subnet("s1", "10.0.0.0/24", vlan_id=100)]

        errors = validate_device_interfaces("dev1", ifaces, subnets, [],
                                            device_vlan_id=0)
        rule32 = [e for e in errors if e["rule"] == 32]
        assert len(rule32) == 0


class TestFullyValidConfig:
    """A well-formed device config should produce no errors at all."""

    def test_valid_config_no_errors(self):
        subnets = [_subnet("s1", "10.0.0.0/24", vlan_id=100)]
        zones = [
            _zone("z1", "Inside", zone_type="data"),
            _zone("z2", "Outside", zone_type="data"),
            _zone("z3", "Mgmt", zone_type="management"),
        ]
        ifaces = [
            _iface("i1", ip="10.0.0.10", subnet_id="s1", zone_id="z1", role="inside"),
            _iface("i2", ip="10.0.0.11", subnet_id="s1", zone_id="z2", role="outside"),
            _iface("i3", ip="10.0.0.12", subnet_id="s1", zone_id="z3", role="management"),
        ]

        errors = validate_device_interfaces("dev1", ifaces, subnets, zones,
                                            device_vlan_id=100)
        assert errors == []

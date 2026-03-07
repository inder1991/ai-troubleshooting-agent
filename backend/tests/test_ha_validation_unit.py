"""Unit tests for HA group validation rules in ha_validation.py."""
import os
import pytest
from src.network.models import (
    HAGroup, HAMode, Device, DeviceType, Subnet,
)
from src.network.ha_validation import validate_ha_group
from src.network.topology_store import TopologyStore


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "ha_val.db"))


# ── helpers ──

def _fw(device_id: str, ip: str) -> Device:
    """Create a firewall device with a management IP."""
    return Device(
        id=device_id, name=f"fw-{device_id}",
        device_type=DeviceType.FIREWALL, management_ip=ip,
    )


def _ha(member_ids: list[str], *, mode=HAMode.ACTIVE_PASSIVE,
        vips: list[str] | None = None, active: str = "") -> HAGroup:
    return HAGroup(
        id="ha1", name="test-ha", ha_mode=mode,
        member_ids=member_ids, virtual_ips=vips or [],
        active_member_id=active,
    )


class TestHAValidationUnit:
    """Tests that exercise every rule in validate_ha_group."""

    # ── 1. Valid HA group produces zero errors ──
    def test_valid_ha_group_no_errors(self, store):
        store.add_device(_fw("d1", "10.0.0.1"))
        store.add_device(_fw("d2", "10.0.0.2"))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))

        errors = validate_ha_group(
            store, _ha(["d1", "d2"], vips=["10.0.0.100"], active="d1"),
        )
        assert errors == []

    # ── 2. Mixed device types → Rule 20 error ──
    def test_mixed_device_types_error(self, store):
        store.add_device(_fw("d1", "10.0.0.1"))
        store.add_device(Device(
            id="d2", name="rtr-01",
            device_type=DeviceType.ROUTER, management_ip="10.0.0.2",
        ))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))

        errors = validate_ha_group(
            store, _ha(["d1", "d2"], active="d1"),
        )
        assert any("same device type" in e for e in errors)

    # ── 3. Member device not found → early exit ──
    def test_missing_member_device(self, store):
        store.add_device(_fw("d1", "10.0.0.1"))
        # d2 never added → not found

        errors = validate_ha_group(
            store, _ha(["d1", "d2"]),
        )
        assert any("not found" in e for e in errors)
        # With only one resolved member, further rules are skipped
        assert not any("same device type" in e for e in errors)

    # ── 4. Members in different subnets → Rule 21 error ──
    def test_members_different_subnets(self, store):
        store.add_device(_fw("d1", "10.0.0.1"))
        store.add_device(_fw("d2", "192.168.1.1"))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))
        store.add_subnet(Subnet(id="s2", cidr="192.168.1.0/24"))

        errors = validate_ha_group(
            store, _ha(["d1", "d2"], active="d1"),
        )
        assert any("same subnet" in e.lower() for e in errors)

    # ── 5. VIP outside member subnet → Rule 22 error ──
    def test_vip_outside_member_subnet(self, store):
        store.add_device(_fw("d1", "10.0.0.1"))
        store.add_device(_fw("d2", "10.0.0.2"))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))

        errors = validate_ha_group(
            store, _ha(["d1", "d2"], vips=["172.16.5.99"], active="d1"),
        )
        assert any("VIP" in e and "not within" in e for e in errors)

    # ── 6. Active-passive without active member → Rule 24 error ──
    def test_active_passive_no_active_member(self, store):
        store.add_device(_fw("d1", "10.0.0.1"))
        store.add_device(_fw("d2", "10.0.0.2"))

        errors = validate_ha_group(
            store, _ha(["d1", "d2"], mode=HAMode.ACTIVE_PASSIVE, active=""),
        )
        assert any("active member" in e.lower() for e in errors)

    # ── 7. Active member not in member list → Rule 24 variant ──
    def test_active_member_not_in_member_list(self, store):
        store.add_device(_fw("d1", "10.0.0.1"))
        store.add_device(_fw("d2", "10.0.0.2"))

        errors = validate_ha_group(
            store, _ha(["d1", "d2"], mode=HAMode.ACTIVE_PASSIVE, active="d99"),
        )
        assert any("not in member list" in e for e in errors)

    # ── 8. Active-active mode does NOT require active_member_id ──
    def test_active_active_no_active_member_ok(self, store):
        store.add_device(_fw("d1", "10.0.0.1"))
        store.add_device(_fw("d2", "10.0.0.2"))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))

        errors = validate_ha_group(
            store, _ha(["d1", "d2"], mode=HAMode.ACTIVE_ACTIVE, vips=["10.0.0.100"]),
        )
        # No rule-24 error for active-active
        assert not any("active member" in e.lower() for e in errors)

    # ── 9. Members with no matching subnets fall back to /24 comparison ──
    def test_no_subnets_defined_fallback_different_slash24(self, store):
        store.add_device(_fw("d1", "10.0.0.1"))
        store.add_device(_fw("d2", "10.1.0.1"))
        # No subnets added → fallback /24 comparison kicks in

        errors = validate_ha_group(
            store, _ha(["d1", "d2"], active="d1"),
        )
        assert any("same subnet" in e.lower() for e in errors)

    # ── 10. Members in same /24 with no subnets defined → no error ──
    def test_no_subnets_defined_same_slash24_ok(self, store):
        store.add_device(_fw("d1", "10.0.0.1"))
        store.add_device(_fw("d2", "10.0.0.2"))
        # No subnets → fallback /24 comparison, same /24 → OK

        errors = validate_ha_group(
            store, _ha(["d1", "d2"], mode=HAMode.ACTIVE_PASSIVE, active="d1"),
        )
        assert not any("same subnet" in e.lower() for e in errors)

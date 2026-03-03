"""Tests for topology promotion validation."""
import os
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph


@pytest.fixture
def kg(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    store = TopologyStore(db_path=db_path)
    return NetworkKnowledgeGraph(store)


def test_promote_device_with_invalid_ip_rejected(kg):
    nodes = [{"id": "d1", "type": "device", "data": {"label": "fw-01", "ip": "999.999.999.999", "deviceType": "firewall"}}]
    result = kg.promote_from_canvas(nodes, [])
    assert len(result["errors"]) >= 1
    assert result["devices_promoted"] == 0


def test_promote_device_with_valid_ip_accepted(kg):
    nodes = [{"id": "d1", "type": "device", "data": {"label": "fw-01", "ip": "10.0.0.1", "deviceType": "firewall"}}]
    result = kg.promote_from_canvas(nodes, [])
    assert result["devices_promoted"] == 1
    assert len(result["errors"]) == 0


def test_promote_subnet_with_invalid_cidr_rejected(kg):
    nodes = [{"id": "s1", "type": "subnet", "data": {"cidr": "not-valid"}}]
    result = kg.promote_from_canvas(nodes, [])
    assert len(result["errors"]) >= 1


def test_promote_duplicate_ips_warned(kg):
    nodes = [
        {"id": "d1", "type": "device", "data": {"label": "fw-01", "ip": "10.0.0.1", "deviceType": "firewall"}},
        {"id": "d2", "type": "device", "data": {"label": "fw-02", "ip": "10.0.0.1", "deviceType": "firewall"}},
    ]
    result = kg.promote_from_canvas(nodes, [])
    assert any("Duplicate IP" in e for e in result["errors"])


def test_promote_vip_not_flagged_as_duplicate(kg):
    """VIPs shared by HA group members should not trigger duplicate IP errors."""
    from src.network.models import HAGroup, HAMode
    kg.store.add_ha_group(HAGroup(
        id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
        member_ids=["d1", "d2"], virtual_ips=["10.0.0.1"],
        active_member_id="d1",
    ))
    nodes = [
        {"id": "d1", "type": "device", "data": {"label": "fw-01", "ip": "10.0.0.2", "deviceType": "firewall"}},
        {"id": "d2", "type": "device", "data": {"label": "fw-02", "ip": "10.0.0.3", "deviceType": "firewall"}},
    ]
    result = kg.promote_from_canvas(nodes, [])
    assert not any("Duplicate IP" in e for e in result["errors"])
    assert result["devices_promoted"] == 2


def test_promote_shared_vip_not_flagged(kg):
    """When two HA members share a VIP address, it should NOT be flagged as duplicate."""
    from src.network.models import HAGroup, HAMode
    kg.store.add_ha_group(HAGroup(
        id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
        member_ids=["d1", "d2"], virtual_ips=["10.0.0.100"],
        active_member_id="d1",
    ))
    # Both devices have unique management IPs but the VIP 10.0.0.100 exists in the HA group
    # This tests that the VIP doesn't cause issues, and the unique IPs don't get flagged
    nodes = [
        {"id": "d1", "type": "device", "data": {"label": "fw-01", "ip": "10.0.0.1", "deviceType": "firewall"}},
        {"id": "d2", "type": "device", "data": {"label": "fw-02", "ip": "10.0.0.100", "deviceType": "firewall"}},
        {"id": "d3", "type": "device", "data": {"label": "fw-vip", "ip": "10.0.0.100", "deviceType": "firewall"}},
    ]
    result = kg.promote_from_canvas(nodes, [])
    # 10.0.0.100 appears twice but is a known VIP, so should NOT be flagged
    assert not any("Duplicate IP" in e for e in result["errors"])

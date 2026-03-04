"""Tests for drift detection engine."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.network.topology_store import TopologyStore
from src.network.models import (
    Device, DeviceType, Route, FirewallRule, PolicyAction, FirewallVendor,
)
from src.network.drift_engine import DriftEngine


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def engine(store):
    return DriftEngine(store)


def _make_adapter():
    adapter = AsyncMock()
    adapter.get_routes = AsyncMock(return_value=[])
    adapter.get_rules = AsyncMock(return_value=[])
    adapter.get_interfaces = AsyncMock(return_value=[])
    adapter.get_nat_rules = AsyncMock(return_value=[])
    adapter.get_zones = AsyncMock(return_value=[])
    return adapter


class TestRouteDrift:
    @pytest.mark.asyncio
    async def test_missing_route_detected(self, store, engine):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER))
        store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.0.0/8", next_hop="10.0.0.1"))
        adapter = _make_adapter()
        adapter.get_routes.return_value = []  # route missing from device
        events = await engine.check_device("r1", adapter)
        assert any(e["drift_type"] == "missing" and e["entity_type"] == "route" for e in events)

    @pytest.mark.asyncio
    async def test_added_route_detected(self, store, engine):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER))
        # No routes in KG
        adapter = _make_adapter()
        live_route = MagicMock()
        live_route.destination_cidr = "172.16.0.0/12"
        live_route.next_hop = "10.0.0.1"
        live_route.metric = 100
        live_route.protocol = "static"
        adapter.get_routes.return_value = [live_route]
        events = await engine.check_device("r1", adapter)
        assert any(e["drift_type"] == "added" and e["entity_type"] == "route" for e in events)

    @pytest.mark.asyncio
    async def test_changed_route_next_hop(self, store, engine):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER))
        store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.0.0/8", next_hop="10.0.0.1"))
        adapter = _make_adapter()
        live_route = MagicMock()
        live_route.destination_cidr = "10.0.0.0/8"
        live_route.next_hop = "10.0.0.99"  # changed
        adapter.get_routes.return_value = [live_route]
        events = await engine.check_device("r1", adapter)
        assert any(e["drift_type"] == "changed" and e["field"] == "next_hop" for e in events)

    @pytest.mark.asyncio
    async def test_no_drift_when_matching(self, store, engine):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER))
        store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.0.0/8", next_hop="10.0.0.1"))
        adapter = _make_adapter()
        live_route = MagicMock()
        live_route.destination_cidr = "10.0.0.0/8"
        live_route.next_hop = "10.0.0.1"
        adapter.get_routes.return_value = [live_route]
        events = await engine.check_device("r1", adapter)
        route_events = [e for e in events if e["entity_type"] == "route"]
        assert len(route_events) == 0


class TestFirewallRuleDrift:
    @pytest.mark.asyncio
    async def test_action_change_is_critical(self, store, engine):
        store.add_device(Device(id="fw1", name="FW1", device_type=DeviceType.FIREWALL))
        store.add_firewall_rule(FirewallRule(
            id="rule1", device_id="fw1", rule_name="block-ssh",
            action=PolicyAction.DENY, src_ips=["any"], dst_ips=["10.0.0.0/8"],
            ports=[22], protocol="tcp",
        ))
        adapter = _make_adapter()
        live_rule = MagicMock()
        live_rule.rule_name = "block-ssh"
        live_rule.action = PolicyAction.ALLOW  # changed!
        live_rule.src_ips = ["any"]
        live_rule.dst_ips = ["10.0.0.0/8"]
        live_rule.ports = [22]
        adapter.get_rules.return_value = [live_rule]
        events = await engine.check_device("fw1", adapter)
        action_events = [e for e in events if e.get("field") == "action"]
        assert len(action_events) == 1
        assert action_events[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_adapter_failure_returns_empty(self, store, engine):
        store.add_device(Device(id="fw1", name="FW1", device_type=DeviceType.FIREWALL))
        adapter = _make_adapter()
        adapter.get_routes.side_effect = Exception("connection refused")
        adapter.get_rules.side_effect = Exception("connection refused")
        adapter.get_interfaces.side_effect = Exception("connection refused")
        adapter.get_nat_rules.side_effect = Exception("connection refused")
        adapter.get_zones.side_effect = Exception("connection refused")
        events = await engine.check_device("fw1", adapter)
        assert events == []

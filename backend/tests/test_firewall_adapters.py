"""Tests for firewall adapter base and mock adapter."""
import pytest
import time
from src.network.adapters.base import FirewallAdapter, DeviceInterface
from src.network.adapters.mock_adapter import MockFirewallAdapter
from src.network.models import (
    FirewallRule, PolicyAction, FirewallVendor, Zone,
    VerdictMatchType, AdapterHealthStatus,
)


@pytest.fixture
def allow_web_rule():
    return FirewallRule(
        id="r1", device_id="fw1", rule_name="allow-web",
        src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[80, 443],
        action=PolicyAction.ALLOW, order=10,
    )

@pytest.fixture
def deny_all_rule():
    return FirewallRule(
        id="r2", device_id="fw1", rule_name="deny-all",
        src_ips=[], dst_ips=[], ports=[],
        action=PolicyAction.DENY, order=9999,
    )

@pytest.fixture
def adapter(allow_web_rule, deny_all_rule):
    return MockFirewallAdapter(
        rules=[allow_web_rule, deny_all_rule],
        zones=[Zone(id="z1", name="trust"), Zone(id="z2", name="untrust")],
    )


class TestMockAdapter:
    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.match_type == VerdictMatchType.EXACT
        assert verdict.confidence == 0.95
        assert verdict.rule_name == "allow-web"

    @pytest.mark.asyncio
    async def test_simulate_deny_no_match(self):
        adapter = MockFirewallAdapter(rules=[])
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY
        assert verdict.confidence == 0.75

    @pytest.mark.asyncio
    async def test_rule_priority_order(self):
        # Lower order number = higher priority
        high_priority = FirewallRule(
            id="r-high", device_id="fw1", rule_name="deny-specific",
            src_ips=["10.0.0.5"], dst_ips=["any"], ports=[443],
            action=PolicyAction.DENY, order=5,
        )
        low_priority = FirewallRule(
            id="r-low", device_id="fw1", rule_name="allow-all",
            src_ips=["any"], dst_ips=["any"], ports=[],
            action=PolicyAction.ALLOW, order=100,
        )
        adapter = MockFirewallAdapter(rules=[low_priority, high_priority])
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY
        assert verdict.rule_name == "deny-specific"

    @pytest.mark.asyncio
    async def test_cidr_matching(self, adapter):
        # 10.0.0.5 matches 10.0.0.0/8
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 80)
        assert verdict.action == PolicyAction.ALLOW

    @pytest.mark.asyncio
    async def test_port_matching_specific(self):
        rule = FirewallRule(
            id="r1", device_id="fw1", rule_name="allow-ssh",
            src_ips=["any"], dst_ips=["any"], ports=[22],
            action=PolicyAction.ALLOW, order=10,
        )
        adapter = MockFirewallAdapter(rules=[rule])
        # Port 22 should match
        verdict = await adapter.simulate_flow("10.0.0.1", "10.0.1.1", 22)
        assert verdict.action == PolicyAction.ALLOW
        # Port 80 should NOT match
        verdict = await adapter.simulate_flow("10.0.0.1", "10.0.1.1", 80)
        assert verdict.action == PolicyAction.DENY

    @pytest.mark.asyncio
    async def test_port_matching_empty_means_any(self):
        rule = FirewallRule(
            id="r1", device_id="fw1", rule_name="allow-all-ports",
            src_ips=["any"], dst_ips=["any"], ports=[],
            action=PolicyAction.ALLOW, order=10,
        )
        adapter = MockFirewallAdapter(rules=[rule])
        verdict = await adapter.simulate_flow("10.0.0.1", "10.0.1.1", 9999)
        assert verdict.action == PolicyAction.ALLOW


class TestAdapterBase:
    @pytest.mark.asyncio
    async def test_health_check_not_configured(self):
        adapter = MockFirewallAdapter()
        health = await adapter.health_check()
        assert health.status == AdapterHealthStatus.NOT_CONFIGURED

    @pytest.mark.asyncio
    async def test_snapshot_age_infinite_before_load(self):
        adapter = MockFirewallAdapter()
        assert adapter.snapshot_age_seconds() == float("inf")

    @pytest.mark.asyncio
    async def test_snapshot_refreshes_on_ttl(self):
        adapter = MockFirewallAdapter(
            rules=[FirewallRule(id="r1", device_id="fw1", rule_name="test",
                               action=PolicyAction.ALLOW, order=1)]
        )
        # First call triggers snapshot
        await adapter.get_rules()
        assert adapter.snapshot_age_seconds() < 5

    @pytest.mark.asyncio
    async def test_get_rules_zone_filter(self):
        rules = [
            FirewallRule(id="r1", device_id="fw1", rule_name="trust-to-untrust",
                        src_zone="trust", dst_zone="untrust", action=PolicyAction.ALLOW, order=1),
            FirewallRule(id="r2", device_id="fw1", rule_name="untrust-to-trust",
                        src_zone="untrust", dst_zone="trust", action=PolicyAction.DENY, order=2),
        ]
        adapter = MockFirewallAdapter(rules=rules)
        filtered = await adapter.get_rules(zone_src="trust")
        assert len(filtered) == 1
        assert filtered[0].rule_name == "trust-to-untrust"

    @pytest.mark.asyncio
    async def test_get_zones(self):
        adapter = MockFirewallAdapter(zones=[Zone(id="z1", name="trust")])
        zones = await adapter.get_zones()
        assert len(zones) == 1

    @pytest.mark.asyncio
    async def test_ip_match_exact(self):
        adapter = MockFirewallAdapter()
        assert adapter._match_ip("10.0.0.1", ["10.0.0.1"]) is True
        assert adapter._match_ip("10.0.0.1", ["10.0.0.2"]) is False

    @pytest.mark.asyncio
    async def test_ip_match_cidr(self):
        adapter = MockFirewallAdapter()
        assert adapter._match_ip("10.0.0.5", ["10.0.0.0/24"]) is True
        assert adapter._match_ip("10.0.1.5", ["10.0.0.0/24"]) is False

    @pytest.mark.asyncio
    async def test_ip_match_any(self):
        adapter = MockFirewallAdapter()
        assert adapter._match_ip("192.168.1.1", ["any"]) is True
        assert adapter._match_ip("192.168.1.1", []) is True

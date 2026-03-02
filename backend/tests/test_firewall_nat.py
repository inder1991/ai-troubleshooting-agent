"""Tests for firewall evaluator and NAT resolver."""
import pytest
from src.agents.network.firewall_evaluator import firewall_evaluator
from src.agents.network.nat_resolver import nat_resolver
from src.network.adapters.mock_adapter import MockFirewallAdapter
from src.network.models import (
    FirewallRule, PolicyAction, NATRule, NATDirection, FirewallVendor, Zone,
    VerdictMatchType,
)


@pytest.fixture
def allow_adapter():
    return MockFirewallAdapter(
        rules=[FirewallRule(id="r1", device_id="fw1", rule_name="allow-all",
                           src_ips=["any"], dst_ips=["any"], ports=[],
                           action=PolicyAction.ALLOW, order=1)],
    )

@pytest.fixture
def deny_adapter():
    return MockFirewallAdapter(rules=[])

@pytest.fixture
def nat_adapter():
    return MockFirewallAdapter(
        nat_rules=[
            NATRule(id="nat1", device_id="fw1", original_src="10.0.0.0/8",
                    translated_src="203.0.113.1", direction=NATDirection.SNAT),
            NATRule(id="nat2", device_id="fw1", original_dst="203.0.113.100",
                    translated_dst="10.0.1.50", translated_port=8080,
                    direction=NATDirection.DNAT),
        ],
    )


class TestFirewallEvaluator:
    @pytest.mark.asyncio
    async def test_allow_verdict(self, allow_adapter):
        state = {
            "firewalls_in_path": [{"device_id": "fw1", "device_name": "Firewall1"}],
            "src_ip": "10.0.0.5", "dst_ip": "172.16.0.1", "port": 443, "protocol": "tcp",
        }
        result = await firewall_evaluator(state, adapters={"fw1": allow_adapter})
        assert len(result["firewall_verdicts"]) == 1
        assert result["firewall_verdicts"][0]["action"] == "allow"
        assert result["firewall_verdicts"][0]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_deny_verdict(self, deny_adapter):
        state = {
            "firewalls_in_path": [{"device_id": "fw1", "device_name": "Firewall1"}],
            "src_ip": "10.0.0.5", "dst_ip": "172.16.0.1", "port": 443, "protocol": "tcp",
        }
        result = await firewall_evaluator(state, adapters={"fw1": deny_adapter})
        assert result["firewall_verdicts"][0]["action"] == "deny"

    @pytest.mark.asyncio
    async def test_no_adapter(self):
        state = {
            "firewalls_in_path": [{"device_id": "fw-unknown", "device_name": "Unknown"}],
            "src_ip": "10.0.0.5", "dst_ip": "172.16.0.1", "port": 443, "protocol": "tcp",
        }
        result = await firewall_evaluator(state, adapters={})
        assert result["firewall_verdicts"][0]["match_type"] == VerdictMatchType.ADAPTER_UNAVAILABLE.value

    @pytest.mark.asyncio
    async def test_no_firewalls(self):
        state = {"firewalls_in_path": [], "src_ip": "10.0.0.5", "dst_ip": "172.16.0.1", "port": 443}
        result = await firewall_evaluator(state, adapters={})
        assert result["firewall_verdicts"] == []

    @pytest.mark.asyncio
    async def test_multiple_firewalls(self, allow_adapter, deny_adapter):
        state = {
            "firewalls_in_path": [
                {"device_id": "fw1", "device_name": "FW1"},
                {"device_id": "fw2", "device_name": "FW2"},
            ],
            "src_ip": "10.0.0.5", "dst_ip": "172.16.0.1", "port": 443, "protocol": "tcp",
        }
        result = await firewall_evaluator(state, adapters={"fw1": allow_adapter, "fw2": deny_adapter})
        actions = [v["action"] for v in result["firewall_verdicts"]]
        assert "allow" in actions
        assert "deny" in actions


class TestNATResolver:
    @pytest.mark.asyncio
    async def test_snat(self, nat_adapter):
        state = {
            "firewalls_in_path": [{"device_id": "fw1"}],
            "src_ip": "10.0.0.5", "dst_ip": "172.16.0.1", "port": 443,
        }
        result = await nat_resolver(state, adapters={"fw1": nat_adapter})
        assert len(result["nat_translations"]) >= 1
        snat = [t for t in result["nat_translations"] if t["direction"] == "snat"]
        assert len(snat) == 1
        assert snat[0]["translated_src"] == "203.0.113.1"

    @pytest.mark.asyncio
    async def test_dnat(self, nat_adapter):
        state = {
            "firewalls_in_path": [{"device_id": "fw1"}],
            "src_ip": "10.0.0.5", "dst_ip": "203.0.113.100", "port": 443,
        }
        result = await nat_resolver(state, adapters={"fw1": nat_adapter})
        dnat = [t for t in result["nat_translations"] if t["direction"] == "dnat"]
        assert len(dnat) == 1
        assert dnat[0]["translated_dst"] == "10.0.1.50"
        assert dnat[0]["translated_port"] == 8080

    @pytest.mark.asyncio
    async def test_identity_chain(self, nat_adapter):
        state = {
            "firewalls_in_path": [{"device_id": "fw1"}],
            "src_ip": "10.0.0.5", "dst_ip": "172.16.0.1", "port": 443,
        }
        result = await nat_resolver(state, adapters={"fw1": nat_adapter})
        assert result["identity_chain"][0]["stage"] == "original"
        assert result["identity_chain"][0]["ip"] == "10.0.0.5"
        assert len(result["identity_chain"]) >= 2

    @pytest.mark.asyncio
    async def test_no_firewalls(self):
        state = {"firewalls_in_path": [], "src_ip": "10.0.0.5", "dst_ip": "172.16.0.1", "port": 443}
        result = await nat_resolver(state, adapters={})
        assert result["nat_translations"] == []
        assert len(result["identity_chain"]) == 1
        assert result["identity_chain"][0]["stage"] == "original"

    @pytest.mark.asyncio
    async def test_no_adapter(self):
        state = {
            "firewalls_in_path": [{"device_id": "fw-unknown"}],
            "src_ip": "10.0.0.5", "dst_ip": "172.16.0.1", "port": 443,
        }
        result = await nat_resolver(state, adapters={})
        assert result["nat_translations"] == []

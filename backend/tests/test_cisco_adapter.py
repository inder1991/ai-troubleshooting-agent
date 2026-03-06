"""Tests for Cisco IOS-XE RESTCONF adapter."""
import pytest
import time
from src.network.adapters.cisco_adapter import CiscoAdapter, _stable_id
from src.network.models import (
    FirewallRule, PolicyAction, VerdictMatchType, FirewallVendor,
)


@pytest.fixture
def adapter():
    return CiscoAdapter(
        hostname="csr1000v.lab.local",
        username="admin",
        password="cisco123",
        verify_ssl=False,
    )


class TestCiscoAdapter:
    def test_init(self, adapter):
        assert adapter.vendor == FirewallVendor.CISCO
        assert adapter.api_endpoint == "https://csr1000v.lab.local"
        assert adapter._hostname == "csr1000v.lab.local"
        assert adapter._username == "admin"
        assert adapter._verify_ssl is False

    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        """Injected permit ACE should produce ALLOW verdict."""
        adapter._rules_cache = [
            FirewallRule(
                id="r1", device_id="csr1000v", rule_name="OUTSIDE_IN:seq-10",
                src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                protocol="tcp", action=PolicyAction.ALLOW, order=10,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.confidence == 0.90
        assert verdict.match_type == VerdictMatchType.EXACT
        assert verdict.rule_name == "OUTSIDE_IN:seq-10"

    @pytest.mark.asyncio
    async def test_simulate_deny(self, adapter):
        """Explicit deny ACE should produce DENY verdict."""
        adapter._rules_cache = [
            FirewallRule(
                id="r1", device_id="csr1000v", rule_name="BLOCK_SSH:seq-10",
                src_ips=["any"], dst_ips=["any"], ports=[22],
                protocol="tcp", action=PolicyAction.DENY, order=10,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 22)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.EXACT

    @pytest.mark.asyncio
    async def test_simulate_implicit_deny(self, adapter):
        """Empty rules cache should produce implicit deny."""
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY
        assert verdict.confidence == 0.90
        assert "implicit deny" in verdict.details.lower()

    @pytest.mark.asyncio
    async def test_health_not_configured(self):
        """Empty hostname should yield NOT_CONFIGURED health status."""
        adapter = CiscoAdapter(hostname="", username="", password="")
        health = await adapter.health_check()
        assert health.status.value == "not_configured"

    def test_normalize_acl_permit(self, adapter):
        """Raw permit ACE dict should normalize to ALLOW FirewallRule."""
        ace = {
            "grant": "permit",
            "protocol": "tcp",
            "source-address": "10.0.0.0",
            "source-wildcard": "0.0.0.255",
            "destination-any": True,
            "destination-port": 443,
        }
        rule = adapter._normalize_ace(ace, "OUTSIDE_IN", 10, "csr1000v")
        assert rule is not None
        assert rule.action == PolicyAction.ALLOW
        assert rule.protocol == "tcp"
        assert rule.src_ips == ["10.0.0.0/24"]
        assert rule.dst_ips == ["any"]
        assert rule.ports == [443]
        assert rule.order == 10
        assert rule.rule_name == "OUTSIDE_IN:seq-10"

    def test_normalize_acl_deny(self, adapter):
        """Raw deny ACE dict should normalize to DENY FirewallRule."""
        ace = {
            "grant": "deny",
            "protocol": "ip",
            "source-any": True,
            "destination-host": "192.168.1.100",
        }
        rule = adapter._normalize_ace(ace, "BLOCK_LIST", 20, "csr1000v")
        assert rule is not None
        assert rule.action == PolicyAction.DENY
        assert rule.protocol == "any"  # ip maps to any
        assert rule.src_ips == ["any"]
        assert rule.dst_ips == ["192.168.1.100/32"]
        assert rule.ports == []

    def test_normalize_ace_empty(self, adapter):
        """Empty ACE dict should return None."""
        rule = adapter._normalize_ace({}, "ACL1", 10, "csr1000v")
        assert rule is None

    def test_wildcard_to_cidr_standard(self):
        """Standard wildcard mask conversion."""
        assert CiscoAdapter._wildcard_to_cidr("10.0.0.0 0.0.0.255") == "10.0.0.0/24"

    def test_wildcard_to_cidr_16(self):
        """/16 wildcard mask conversion."""
        assert CiscoAdapter._wildcard_to_cidr("172.16.0.0 0.0.255.255") == "172.16.0.0/16"

    def test_wildcard_to_cidr_host(self):
        """'host' keyword conversion."""
        assert CiscoAdapter._wildcard_to_cidr("host 10.0.0.1") == "10.0.0.1/32"

    def test_wildcard_to_cidr_any(self):
        """'any' keyword passes through."""
        assert CiscoAdapter._wildcard_to_cidr("any") == "any"

    def test_wildcard_to_cidr_32(self):
        """/32 (all zeros) wildcard mask."""
        assert CiscoAdapter._wildcard_to_cidr("10.0.0.1 0.0.0.0") == "10.0.0.1/32"

    def test_stable_id_deterministic(self):
        """_stable_id should be deterministic and 12 chars."""
        id1 = _stable_id("csr1000v", "OUTSIDE_IN", "10")
        id2 = _stable_id("csr1000v", "OUTSIDE_IN", "10")
        assert id1 == id2
        assert len(id1) == 12

    def test_stable_id_different_inputs(self):
        """Different inputs should produce different IDs."""
        id1 = _stable_id("csr1000v", "OUTSIDE_IN", "10")
        id2 = _stable_id("csr1000v", "OUTSIDE_IN", "20")
        assert id1 != id2

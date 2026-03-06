"""Tests for F5 BIG-IP iControl REST adapter."""
import pytest
import time
from src.network.adapters.f5_adapter import F5Adapter
from src.network.models import FirewallRule, PolicyAction, VerdictMatchType, FirewallVendor


@pytest.fixture
def adapter():
    return F5Adapter(
        hostname="bigip01.example.com",
        username="admin",
        password="admin-secret",
        partition="Common",
    )


class TestF5Adapter:
    def test_init(self, adapter):
        """Verify vendor is F5 and api_endpoint is derived from hostname."""
        assert adapter.vendor == FirewallVendor.F5
        assert adapter.api_endpoint == "https://bigip01.example.com"

    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        """Inject a rule cache with an ALLOW rule and verify flow matches."""
        adapter._rules_cache = [
            FirewallRule(
                id="r1", device_id="f5-bigip01", rule_name="allow-web",
                src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                action=PolicyAction.ALLOW, order=1, protocol="tcp",
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.confidence == 0.90
        assert verdict.match_type == VerdictMatchType.EXACT

    @pytest.mark.asyncio
    async def test_simulate_implicit_deny(self, adapter):
        """Empty rules cache should produce an implicit deny."""
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY
        assert verdict.confidence == 0.75

    @pytest.mark.asyncio
    async def test_simulate_order_matters(self, adapter):
        """Lower-order rule should win even if a later rule also matches."""
        adapter._rules_cache = [
            FirewallRule(
                id="r-deny", device_id="f5-bigip01", rule_name="deny-all",
                src_ips=["any"], dst_ips=["any"], ports=[],
                action=PolicyAction.DENY, order=10, protocol="tcp",
            ),
            FirewallRule(
                id="r-allow", device_id="f5-bigip01", rule_name="allow-ssh",
                src_ips=["any"], dst_ips=["any"], ports=[22],
                action=PolicyAction.ALLOW, order=1, protocol="tcp",
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.1", "10.0.0.2", 22)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.rule_name == "allow-ssh"
        assert verdict.rule_id == "r-allow"

    @pytest.mark.asyncio
    async def test_health_not_configured(self):
        """Empty hostname should return NOT_CONFIGURED status."""
        adapter = F5Adapter(hostname="", username="", password="")
        health = await adapter.health_check()
        assert health.status == AdapterHealthStatus.NOT_CONFIGURED
        assert health.status.value == "not_configured"

    def test_normalize_afm_rule(self, adapter):
        """Raw AFM accept rule should normalize to ALLOW with correct ports."""
        raw = {
            "name": "allow_http",
            "action": "accept",
            "ipProtocol": "tcp",
            "log": "yes",
            "source": {
                "addresses": [{"name": "10.0.0.0/8"}]
            },
            "destination": {
                "addresses": [{"name": "172.16.0.0/12"}],
                "ports": [{"name": "80"}, {"name": "443"}],
            },
        }
        rule = adapter._normalize_afm_rule(raw, index=0, policy_name="web-policy")
        assert rule.action == PolicyAction.ALLOW
        assert rule.src_ips == ["10.0.0.0/8"]
        assert rule.dst_ips == ["172.16.0.0/12"]
        assert 80 in rule.ports
        assert 443 in rule.ports
        assert rule.protocol == "tcp"
        assert rule.logged is True
        assert rule.rule_name == "allow_http"
        assert rule.device_id == "f5-bigip01.example.com"

    def test_normalize_afm_drop(self, adapter):
        """Raw AFM drop rule should normalize to DROP."""
        raw = {
            "name": "drop_malicious",
            "action": "drop",
            "ipProtocol": "any",
            "log": "no",
            "source": {
                "addresses": [{"name": "192.168.1.0/24"}]
            },
            "destination": {
                "addresses": [],
            },
        }
        rule = adapter._normalize_afm_rule(raw, index=5, policy_name="sec-policy")
        assert rule.action == PolicyAction.DROP
        assert rule.src_ips == ["192.168.1.0/24"]
        assert rule.dst_ips == ["any"]
        assert rule.ports == []
        assert rule.protocol == "any"
        assert rule.logged is False

    def test_normalize_afm_accept_decisively(self, adapter):
        """accept-decisively action should map to ALLOW."""
        raw = {
            "name": "accept_decisive",
            "action": "accept-decisively",
            "ipProtocol": "tcp",
            "log": "no",
            "source": {"addresses": []},
            "destination": {"addresses": [], "ports": [{"name": "8443"}]},
        }
        rule = adapter._normalize_afm_rule(raw, index=2)
        assert rule.action == PolicyAction.ALLOW
        assert rule.src_ips == ["any"]
        assert 8443 in rule.ports

    def test_normalize_afm_reject(self, adapter):
        """reject action should map to DENY (not DROP)."""
        raw = {
            "name": "reject_rule",
            "action": "reject",
            "ipProtocol": "tcp",
            "log": "no",
        }
        rule = adapter._normalize_afm_rule(raw, index=3)
        assert rule.action == PolicyAction.DENY

    def test_stable_id_deterministic(self):
        """_stable_id should return the same 12-char hex for the same input."""
        id1 = F5Adapter._stable_id("test-input")
        id2 = F5Adapter._stable_id("test-input")
        assert id1 == id2
        assert len(id1) == 12

    def test_normalize_port_range(self, adapter):
        """Port ranges like '8080-8090' should expand to individual ports."""
        raw = {
            "name": "range_rule",
            "action": "accept",
            "ipProtocol": "tcp",
            "log": "no",
            "destination": {
                "ports": [{"name": "8080-8082"}],
            },
        }
        rule = adapter._normalize_afm_rule(raw, index=0)
        assert 8080 in rule.ports
        assert 8081 in rule.ports
        assert 8082 in rule.ports
        assert len(rule.ports) == 3


# Import for the health test assertion
from src.network.models import AdapterHealthStatus

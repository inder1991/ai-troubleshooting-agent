"""Tests for Check Point Management API adapter."""
import pytest
import time
from src.network.adapters.checkpoint_adapter import CheckpointAdapter
from src.network.models import FirewallRule, PolicyAction, VerdictMatchType, FirewallVendor


@pytest.fixture
def adapter():
    return CheckpointAdapter(
        hostname="cp-mgmt.example.com",
        username="admin",
        password="test-password",
        domain="",
        port=443,
        verify_ssl=False,
    )


class TestCheckpointAdapter:
    def test_init(self, adapter):
        assert adapter.vendor == FirewallVendor.CHECKPOINT
        assert adapter.api_endpoint == "https://cp-mgmt.example.com:443"

    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(
                id="r1", device_id="checkpoint", rule_name="allow-web",
                src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                action=PolicyAction.ALLOW, order=1, protocol="any",
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.confidence == 0.90
        assert verdict.match_type == VerdictMatchType.EXACT
        assert "allow-web" in verdict.details

    @pytest.mark.asyncio
    async def test_simulate_drop(self, adapter):
        adapter._rules_cache = [
            FirewallRule(
                id="r2", device_id="checkpoint", rule_name="drop-ssh",
                src_ips=["any"], dst_ips=["192.168.1.0/24"], ports=[22],
                action=PolicyAction.DROP, order=1, protocol="tcp",
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "192.168.1.10", 22)
        assert verdict.action == PolicyAction.DROP
        assert verdict.match_type == VerdictMatchType.EXACT
        assert verdict.confidence == 0.90

    @pytest.mark.asyncio
    async def test_simulate_implicit_deny(self, adapter):
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY
        assert verdict.rule_name == "cleanup-rule"
        assert verdict.confidence == 0.75

    @pytest.mark.asyncio
    async def test_health_not_configured(self):
        adapter = CheckpointAdapter(
            hostname="", username="", password="",
        )
        health = await adapter.health_check()
        assert health.status.value == "not_configured"
        assert "No Check Point hostname" in health.message

    def test_normalize_access_rule(self, adapter):
        raw = {
            "uid": "abc-123",
            "name": "Allow HTTPS",
            "action": {"name": "Accept"},
            "source": [
                {"type": "host", "ipv4-address": "10.0.0.1"},
            ],
            "destination": [
                {"type": "network", "subnet4": "172.16.0.0", "mask-length4": 16},
            ],
            "service": [
                {"type": "service-tcp", "port": "443"},
                {"type": "service-tcp", "port": 8443},
            ],
            "track": {"type": {"name": "Log"}},
            "enabled": True,
        }
        rule = adapter._normalize_access_rule(raw, order=0)
        assert rule.action == PolicyAction.ALLOW
        assert rule.rule_name == "Allow HTTPS"
        assert "10.0.0.1/32" in rule.src_ips
        assert "172.16.0.0/16" in rule.dst_ips
        assert 443 in rule.ports
        assert 8443 in rule.ports
        assert rule.logged is True
        assert rule.device_id == "checkpoint-cp-mgmt.example.com"

    def test_normalize_drop_rule(self, adapter):
        raw = {
            "uid": "def-456",
            "name": "Block Telnet",
            "action": {"name": "Drop"},
            "source": [{"type": "CpmiAnyObject"}],
            "destination": [{"type": "CpmiAnyObject"}],
            "service": [{"type": "service-tcp", "port": "23"}],
            "track": {"type": {"name": "None"}},
            "enabled": True,
        }
        rule = adapter._normalize_access_rule(raw, order=5)
        assert rule.action == PolicyAction.DROP
        assert rule.logged is False
        assert "any" in rule.src_ips
        assert "any" in rule.dst_ips
        assert 23 in rule.ports

    def test_extract_ip_from_object(self):
        # host -> /32
        host = {"type": "host", "ipv4-address": "10.0.0.1"}
        assert CheckpointAdapter._extract_ip(host) == "10.0.0.1/32"

        # network -> CIDR
        network = {"type": "network", "subnet4": "10.0.0.0", "mask-length4": 24}
        assert CheckpointAdapter._extract_ip(network) == "10.0.0.0/24"

        # CpmiAnyObject -> "any"
        any_obj = {"type": "CpmiAnyObject"}
        assert CheckpointAdapter._extract_ip(any_obj) == "any"

        # unknown type -> "any"
        unknown = {"type": "group", "name": "some-group"}
        assert CheckpointAdapter._extract_ip(unknown) == "any"

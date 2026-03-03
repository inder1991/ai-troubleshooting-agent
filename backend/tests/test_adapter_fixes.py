"""Tests for adapter bug fixes — port range tuples, protocol matching,
Oracle NSG action, Zscaler key obfuscation, mock forwarding, factory logging."""
import pytest
import time
from unittest.mock import patch
from src.network.adapters.base import FirewallAdapter
from src.network.adapters.mock_adapter import MockFirewallAdapter
from src.network.adapters.aws_sg_adapter import AWSSGAdapter
from src.network.adapters.azure_nsg_adapter import AzureNSGAdapter
from src.network.adapters.oracle_nsg_adapter import OracleNSGAdapter
from src.network.adapters.panorama_adapter import (
    PanoramaAdapter,
    _protocol_from_services,
)
from src.network.adapters.zscaler_adapter import ZscalerAdapter, _obfuscate_api_key
from src.network.adapters.factory import create_adapter
from src.network.models import (
    FirewallRule, PolicyAction, VerdictMatchType, FirewallVendor,
    AdapterHealthStatus,
)


# ── Port range tuple support in base._match_port ──


class TestMatchPortTuples:
    def test_single_port_match(self):
        assert FirewallAdapter._match_port(443, [443]) is True

    def test_single_port_no_match(self):
        assert FirewallAdapter._match_port(80, [443]) is False

    def test_tuple_range_match(self):
        assert FirewallAdapter._match_port(8080, [(8000, 9000)]) is True

    def test_tuple_range_boundary_low(self):
        assert FirewallAdapter._match_port(80, [(80, 443)]) is True

    def test_tuple_range_boundary_high(self):
        assert FirewallAdapter._match_port(443, [(80, 443)]) is True

    def test_tuple_range_no_match(self):
        assert FirewallAdapter._match_port(22, [(80, 443)]) is False

    def test_mixed_ports_and_tuples(self):
        ports = [22, (80, 443), 8080]
        assert FirewallAdapter._match_port(22, ports) is True
        assert FirewallAdapter._match_port(100, ports) is True
        assert FirewallAdapter._match_port(8080, ports) is True
        assert FirewallAdapter._match_port(9999, ports) is False

    def test_empty_ports_means_any(self):
        assert FirewallAdapter._match_port(12345, []) is True

    def test_full_range_tuple(self):
        """Verify (0, 65535) tuple works without materializing 65K elements."""
        assert FirewallAdapter._match_port(0, [(0, 65535)]) is True
        assert FirewallAdapter._match_port(65535, [(0, 65535)]) is True
        assert FirewallAdapter._match_port(32768, [(0, 65535)]) is True


# ── Protocol matching in simulate_flow ──


class TestPanoramaProtocolMatching:
    @pytest.fixture
    def adapter(self):
        return PanoramaAdapter(
            hostname="panorama.example.com", api_key="test-key",
            device_group="DC",
        )

    @pytest.mark.asyncio
    async def test_tcp_rule_matches_tcp_flow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="fw1", rule_name="allow-https",
                        src_ips=["any"], dst_ips=["any"], ports=[443],
                        protocol="tcp", action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.1", "10.0.1.1", 443, "tcp")
        assert verdict.action == PolicyAction.ALLOW

    @pytest.mark.asyncio
    async def test_tcp_rule_rejects_udp_flow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="fw1", rule_name="allow-https",
                        src_ips=["any"], dst_ips=["any"], ports=[443],
                        protocol="tcp", action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.1", "10.0.1.1", 443, "udp")
        assert verdict.action == PolicyAction.DENY

    @pytest.mark.asyncio
    async def test_any_protocol_rule_matches_all(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="fw1", rule_name="allow-all",
                        src_ips=["any"], dst_ips=["any"], ports=[443],
                        protocol="any", action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.1", "10.0.1.1", 443, "udp")
        assert verdict.action == PolicyAction.ALLOW


class TestZscalerProtocolMatching:
    @pytest.fixture
    def adapter(self):
        return ZscalerAdapter(
            cloud_name="zscloud.net", api_key="test-api-key-long-enough",
            username="admin@example.com", password="pass",
        )

    @pytest.mark.asyncio
    async def test_tcp_rule_rejects_udp(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="zs", rule_name="allow-https",
                        src_ips=["any"], dst_ips=["any"], ports=[443],
                        protocol="tcp", action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.1", "10.0.1.1", 443, "udp")
        assert verdict.action == PolicyAction.DENY

    @pytest.mark.asyncio
    async def test_any_protocol_matches(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="zs", rule_name="allow-all",
                        src_ips=["any"], dst_ips=["any"], ports=[],
                        protocol="any", action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.1", "10.0.1.1", 80, "icmp")
        assert verdict.action == PolicyAction.ALLOW


# ── Panorama _protocol_from_services helper ──


class TestProtocolFromServices:
    def test_tcp_only(self):
        assert _protocol_from_services(["tcp/443", "tcp/80"]) == "tcp"

    def test_udp_only(self):
        assert _protocol_from_services(["udp/53"]) == "udp"

    def test_mixed_returns_any(self):
        assert _protocol_from_services(["tcp/443", "udp/53"]) == "any"

    def test_empty_returns_any(self):
        assert _protocol_from_services([]) == "any"

    def test_application_default_only_returns_any(self):
        assert _protocol_from_services(["application-default"]) == "any"

    def test_any_service_returns_any(self):
        assert _protocol_from_services(["any"]) == "any"


# ── Zscaler _obfuscate_api_key guard ──


class TestObfuscateApiKey:
    def test_short_key_raises(self):
        with pytest.raises(ValueError, match="too short"):
            _obfuscate_api_key("short", "1234567890123")

    def test_valid_key_succeeds(self):
        # Key must be at least 10 chars, timestamp at least 13 digits
        result = _obfuscate_api_key("abcdefghijklmnop", "1709547890123")
        assert isinstance(result, str)
        assert len(result) > 0


# ── Oracle NSG — action is always ALLOW ──


class TestOracleNSGAction:
    @pytest.fixture
    def adapter(self):
        return OracleNSGAdapter(
            compartment_id="ocid1.compartment.oc1..abc",
            nsg_id="ocid1.nsg.oc1..xyz",
        )

    @pytest.mark.asyncio
    async def test_allow_rule_is_allow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="nsg", rule_name="allow-https",
                        src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                        action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW


# ── Mock adapter forwarding ──


class TestMockAdapterForwarding:
    def test_api_endpoint_forwarded(self):
        adapter = MockFirewallAdapter(
            api_endpoint="https://fw.example.com", api_key="secret",
        )
        assert adapter.api_endpoint == "https://fw.example.com"
        assert adapter.api_key == "secret"

    def test_extra_config_public(self):
        adapter = MockFirewallAdapter(extra_config={"sg_id": "sg-123"})
        assert adapter.extra_config == {"sg_id": "sg-123"}

    @pytest.mark.asyncio
    async def test_health_check_configured_with_endpoint(self):
        adapter = MockFirewallAdapter(
            api_endpoint="https://fw.example.com", api_key="key",
        )
        # With api_endpoint set, health_check should NOT return NOT_CONFIGURED
        health = await adapter.health_check()
        assert health.status != AdapterHealthStatus.NOT_CONFIGURED


# ── Factory fallback messaging ──


class TestFactoryFallback:
    def test_mock_fallback_for_missing_sdk(self):
        adapter = create_adapter(
            FirewallVendor.PALO_ALTO,
            api_endpoint="https://panorama.example.com",
            api_key="key",
        )
        assert isinstance(adapter, MockFirewallAdapter)

    def test_mock_fallback_for_empty_config(self):
        adapter = create_adapter(FirewallVendor.AWS_SG, api_endpoint="", api_key="")
        assert isinstance(adapter, MockFirewallAdapter)

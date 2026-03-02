"""Tests for cloud NSG/SG adapters."""
import pytest
import time
from src.network.adapters.azure_nsg_adapter import AzureNSGAdapter
from src.network.adapters.aws_sg_adapter import AWSSGAdapter
from src.network.adapters.oracle_nsg_adapter import OracleNSGAdapter
from src.network.models import FirewallRule, PolicyAction, VerdictMatchType, FirewallVendor


class TestAzureNSGAdapter:
    @pytest.fixture
    def adapter(self):
        return AzureNSGAdapter(
            subscription_id="sub-123", resource_group="rg-prod", nsg_name="nsg-web",
        )

    def test_init(self, adapter):
        assert adapter.vendor == FirewallVendor.AZURE_NSG

    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="nsg-web", rule_name="AllowHTTPS",
                        src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                        action=PolicyAction.ALLOW, order=100),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW

    @pytest.mark.asyncio
    async def test_simulate_implicit_deny(self, adapter):
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY

    @pytest.mark.asyncio
    async def test_priority_ordering(self, adapter):
        """Lower priority number (higher priority) should be evaluated first."""
        adapter._rules_cache = [
            FirewallRule(id="r2", device_id="nsg-web", rule_name="DenyAll",
                        src_ips=["any"], dst_ips=["any"], ports=[],
                        action=PolicyAction.DENY, order=200),
            FirewallRule(id="r1", device_id="nsg-web", rule_name="AllowHTTPS",
                        src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                        action=PolicyAction.ALLOW, order=100),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.rule_name == "AllowHTTPS"

    @pytest.mark.asyncio
    async def test_port_mismatch(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="nsg-web", rule_name="AllowHTTPS",
                        src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                        action=PolicyAction.ALLOW, order=100),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 80)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY


class TestAWSSGAdapter:
    @pytest.fixture
    def adapter(self):
        return AWSSGAdapter(region="us-east-1", security_group_id="sg-12345")

    def test_init(self, adapter):
        assert adapter.vendor == FirewallVendor.AWS_SG

    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="sg-12345", rule_name="allow-https",
                        src_ips=["0.0.0.0/0"], dst_ips=["any"], ports=[443],
                        action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW

    @pytest.mark.asyncio
    async def test_simulate_deny(self, adapter):
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY

    @pytest.mark.asyncio
    async def test_stateful_allow_details(self, adapter):
        """Verify the verdict mentions stateful behaviour."""
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="sg-12345", rule_name="allow-https",
                        src_ips=["0.0.0.0/0"], dst_ips=["any"], ports=[443],
                        action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert "stateful" in verdict.details.lower()

    @pytest.mark.asyncio
    async def test_src_ip_no_match(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="sg-12345", rule_name="allow-internal",
                        src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                        action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("192.168.1.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY


class TestOracleNSGAdapter:
    @pytest.fixture
    def adapter(self):
        return OracleNSGAdapter(compartment_id="ocid1.compartment.oc1..abc", nsg_id="ocid1.nsg.oc1..xyz")

    def test_init(self, adapter):
        assert adapter.vendor == FirewallVendor.ORACLE_NSG

    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="nsg-1", rule_name="allow-https",
                        src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                        action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW

    @pytest.mark.asyncio
    async def test_simulate_implicit_deny(self, adapter):
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY

    @pytest.mark.asyncio
    async def test_multiple_rules_order(self, adapter):
        """Rules should be evaluated in order (ascending)."""
        adapter._rules_cache = [
            FirewallRule(id="r2", device_id="nsg-1", rule_name="deny-all",
                        src_ips=["any"], dst_ips=["any"], ports=[],
                        action=PolicyAction.DENY, order=10),
            FirewallRule(id="r1", device_id="nsg-1", rule_name="allow-https",
                        src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                        action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.rule_name == "allow-https"

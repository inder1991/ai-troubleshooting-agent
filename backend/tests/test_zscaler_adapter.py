"""Tests for Zscaler adapter."""
import pytest
import time
from src.network.adapters.zscaler_adapter import ZscalerAdapter
from src.network.models import FirewallRule, PolicyAction, VerdictMatchType, FirewallVendor


@pytest.fixture
def adapter():
    return ZscalerAdapter(
        cloud_name="zscloud.net",
        api_key="test-api-key",
        username="admin@example.com",
        password="test-password",
    )


class TestZscalerAdapter:
    def test_init(self, adapter):
        assert adapter.vendor == FirewallVendor.ZSCALER

    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(id="r1", device_id="zscaler", rule_name="allow-web",
                        src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                        action=PolicyAction.ALLOW, order=1),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.confidence == 0.95

    @pytest.mark.asyncio
    async def test_simulate_deny(self, adapter):
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY

    @pytest.mark.asyncio
    async def test_health_not_configured(self):
        adapter = ZscalerAdapter(cloud_name="", api_key="", username="", password="")
        health = await adapter.health_check()
        assert health.status.value == "not_configured"

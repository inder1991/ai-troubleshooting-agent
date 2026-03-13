"""Tests for CloudProviderDriver ABC."""
import pytest
from src.cloud.drivers.base import CloudProviderDriver
from src.cloud.models import CloudAccount, DiscoveryBatch, DriverHealth


class DummyDriver(CloudProviderDriver):
    async def discover(self, account, region, resource_types):
        yield DiscoveryBatch(
            account_id=account.account_id,
            region=region,
            resource_type="vpc",
            source="test",
            items=[],
            relations=[],
        )

    async def health_check(self, account):
        return DriverHealth(connected=True, latency_ms=10.0)

    def supported_resource_types(self):
        return {"vpc": 1, "subnet": 1}


class TestCloudProviderDriver:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            CloudProviderDriver()

    def test_dummy_driver_instantiates(self):
        driver = DummyDriver()
        types = driver.supported_resource_types()
        assert "vpc" in types
        assert types["vpc"] == 1

    @pytest.mark.asyncio
    async def test_discover_yields_batches(self):
        driver = DummyDriver()
        account = CloudAccount(
            account_id="acc-001", provider="aws",
            display_name="Test", credential_handle="ref",
            auth_method="iam_role", regions=["us-east-1"],
        )
        batches = []
        async for batch in driver.discover(account, "us-east-1", ["vpc"]):
            batches.append(batch)
        assert len(batches) == 1
        assert batches[0].resource_type == "vpc"

    @pytest.mark.asyncio
    async def test_health_check_returns_driver_health(self):
        driver = DummyDriver()
        account = CloudAccount(
            account_id="acc-001", provider="aws",
            display_name="Test", credential_handle="ref",
            auth_method="iam_role", regions=["us-east-1"],
        )
        health = await driver.health_check(account)
        assert health.connected is True

    def test_resource_types_for_tier(self):
        driver = DummyDriver()
        types = driver.resource_types_for_tier(1)
        assert "vpc" in types
        assert "subnet" in types

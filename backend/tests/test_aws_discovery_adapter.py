"""Tests for the AWS cloud discovery adapter."""

import asyncio

import pytest

from src.network.discovery.aws_adapter import AWSDiscoveryAdapter
from src.network.discovery.observation import ObservationType


@pytest.fixture
def aws_adapter():
    mock_data = {
        "vpcs": [
            {
                "VpcId": "vpc-abc123",
                "CidrBlock": "10.0.0.0/16",
                "Tags": [{"Key": "Name", "Value": "prod-vpc"}],
            }
        ],
        "subnets": [],
        "enis": [],
        "security_groups": [],
    }
    return AWSDiscoveryAdapter(mock_data=mock_data)


@pytest.fixture
def empty_adapter():
    return AWSDiscoveryAdapter(mock_data={
        "vpcs": [],
        "subnets": [],
        "enis": [],
        "security_groups": [],
    })


def _collect(async_gen):
    """Run an async generator to completion and return a list of results."""
    loop = asyncio.new_event_loop()
    try:
        results = []

        async def _drain():
            async for item in async_gen:
                results.append(item)

        loop.run_until_complete(_drain())
        return results
    finally:
        loop.close()


class TestAWSDiscoveryAdapter:
    def test_supports_aws_target(self, aws_adapter):
        target = {"type": "cloud_account", "provider": "aws"}
        assert aws_adapter.supports(target) is True

    def test_does_not_support_azure(self, aws_adapter):
        target = {"type": "cloud_account", "provider": "azure"}
        assert aws_adapter.supports(target) is False

    def test_does_not_support_device(self, aws_adapter):
        target = {"type": "device", "host": "10.0.0.1"}
        assert aws_adapter.supports(target) is False

    def test_discover_mock_yields_vpcs(self, aws_adapter):
        target = {"type": "cloud_account", "provider": "aws", "account_id": "123456789012"}
        observations = _collect(aws_adapter.discover(target))

        assert len(observations) == 1
        obs = observations[0]
        assert obs.observation_type == ObservationType.VPC
        assert obs.confidence == 0.95
        assert obs.source == "aws_api"
        assert obs.device_id == "vpc-abc123"
        assert obs.data["cidr"] == "10.0.0.0/16"
        assert obs.data["name"] == "prod-vpc"

    def test_discover_empty(self, empty_adapter):
        target = {"type": "cloud_account", "provider": "aws", "account_id": "123456789012"}
        observations = _collect(empty_adapter.discover(target))

        assert len(observations) == 0

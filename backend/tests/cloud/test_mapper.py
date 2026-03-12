"""Tests for CloudResourceMapper."""
import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.cloud.mapper import CloudResourceMapper


@pytest.fixture
def mapper():
    topology_store = AsyncMock()
    policy_store = AsyncMock()
    return CloudResourceMapper(
        topology_store=topology_store,
        policy_store=policy_store,
    )


class TestVPCMapping:
    @pytest.mark.asyncio
    async def test_maps_aws_vpc(self, mapper):
        resource = MagicMock()
        resource.resource_id = "res-001"
        resource.provider = "aws"
        resource.account_id = "acc-001"
        resource.region = "us-east-1"
        resource.resource_type = "vpc"
        resource.name = "prod-vpc"
        resource.raw_compressed = None
        resource.raw_json = json.dumps({
            "VpcId": "vpc-abc",
            "CidrBlock": "10.0.0.0/16",
            "CidrBlockAssociationSet": [
                {"CidrBlock": "10.1.0.0/16"},
            ],
        })
        await mapper.map_resource(resource)
        mapper._topology_store.upsert_network_segment.assert_called_once()


class TestSecurityGroupMapping:
    @pytest.mark.asyncio
    async def test_maps_sg_to_policy_group(self, mapper):
        resource = MagicMock()
        resource.resource_id = "res-sg-001"
        resource.provider = "aws"
        resource.account_id = "acc-001"
        resource.region = "us-east-1"
        resource.resource_type = "security_group"
        resource.name = "web-sg"
        resource.raw_json = json.dumps({
            "GroupId": "sg-001",
            "GroupName": "web-sg",
            "IpPermissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
            ],
            "IpPermissionsEgress": [],
        })
        await mapper.map_resource(resource)
        mapper._policy_store.upsert_policy_group.assert_called_once()
        mapper._policy_store.replace_rules.assert_called_once()


class TestUnknownResourceType:
    @pytest.mark.asyncio
    async def test_skips_unmapped_type(self, mapper):
        resource = MagicMock()
        resource.resource_type = "unknown_type"
        await mapper.map_resource(resource)
        mapper._topology_store.upsert_network_segment.assert_not_called()
        mapper._policy_store.upsert_policy_group.assert_not_called()

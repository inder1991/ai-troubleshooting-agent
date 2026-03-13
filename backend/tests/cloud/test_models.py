"""Tests for cloud integration data models."""
import json
import pytest
from datetime import datetime

from src.cloud.models import (
    CloudAccount,
    CloudResource,
    CloudResourceRelation,
    CloudSyncJob,
    DiscoveryBatch,
    DiscoveredItem,
    DiscoveredRelation,
    RateLimitInfo,
    DriverHealth,
    SyncTier,
)


class TestCloudAccount:
    def test_create_aws_account(self):
        account = CloudAccount(
            account_id="acc-001",
            provider="aws",
            display_name="Production AWS",
            native_account_id="123456789012",
            credential_handle="encrypted-ref-001",
            auth_method="iam_role",
            regions=["us-east-1", "eu-west-1"],
        )
        assert account.provider == "aws"
        assert account.sync_enabled is True
        assert account.consecutive_failures == 0
        assert account.last_sync_status == "never"

    def test_regions_serialization(self):
        account = CloudAccount(
            account_id="acc-002",
            provider="azure",
            display_name="Azure Dev",
            credential_handle="ref-002",
            auth_method="azure_sp",
            regions=["eastus", "westeurope"],
        )
        assert len(account.regions) == 2

    def test_sync_config_defaults(self):
        account = CloudAccount(
            account_id="acc-003",
            provider="aws",
            display_name="Test",
            credential_handle="ref-003",
            auth_method="access_key",
            regions=["us-east-1"],
        )
        assert account.sync_config is None


class TestCloudResource:
    def test_create_resource(self):
        resource = CloudResource(
            resource_id="res-001",
            provider="aws",
            account_id="acc-001",
            region="us-east-1",
            resource_type="vpc",
            native_id="vpc-abc123",
            name="prod-vpc",
            raw_compressed=b"compressed-data",
            raw_preview='{"VpcId": "vpc-abc123"}',
            tags={"env": "prod"},
            resource_hash="abc123hash",
            source="aws-describe-vpcs",
        )
        assert resource.is_deleted is False
        assert resource.sync_tier == 1

    def test_soft_delete_fields(self):
        resource = CloudResource(
            resource_id="res-002",
            provider="aws",
            account_id="acc-001",
            region="us-east-1",
            resource_type="subnet",
            native_id="subnet-123",
            raw_compressed=b"data",
            is_deleted=True,
            deleted_at="2026-03-12T00:00:00Z",
        )
        assert resource.is_deleted is True
        assert resource.deleted_at is not None


class TestDiscoveryBatch:
    def test_create_batch(self):
        batch = DiscoveryBatch(
            account_id="acc-001",
            region="us-east-1",
            resource_type="vpc",
            source="aws-describe-vpcs",
            items=[
                DiscoveredItem(
                    native_id="vpc-abc",
                    name="prod",
                    raw={"VpcId": "vpc-abc", "CidrBlock": "10.0.0.0/16"},
                    tags={"env": "prod"},
                ),
            ],
            relations=[
                DiscoveredRelation(
                    source_native_id="subnet-123",
                    target_native_id="vpc-abc",
                    relation_type="member_of",
                ),
            ],
        )
        assert len(batch.items) == 1
        assert len(batch.relations) == 1
        assert batch.rate_limit_info is None

    def test_batch_with_rate_limit(self):
        batch = DiscoveryBatch(
            account_id="acc-001",
            region="us-east-1",
            resource_type="vpc",
            source="aws-describe-vpcs",
            items=[],
            relations=[],
            rate_limit_info=RateLimitInfo(
                calls_made=5, remaining=95, reset_at=1710000000.0
            ),
        )
        assert batch.rate_limit_info.remaining == 95


class TestDriverHealth:
    def test_healthy_driver(self):
        health = DriverHealth(
            connected=True,
            latency_ms=45.0,
            identity="arn:aws:iam::123456:role/TestRole",
            permissions_ok=True,
            missing_permissions=[],
            message="All permissions verified",
        )
        assert health.connected is True
        assert health.permissions_ok is True

    def test_unhealthy_driver(self):
        health = DriverHealth(
            connected=True,
            latency_ms=120.0,
            identity="arn:aws:iam::123456:role/TestRole",
            permissions_ok=False,
            missing_permissions=["ec2:DescribeNetworkInterfaces"],
            message="Missing 1 permissions",
        )
        assert not health.permissions_ok
        assert len(health.missing_permissions) == 1


class TestCloudSyncJob:
    def test_create_sync_job(self):
        job = CloudSyncJob(
            sync_job_id="job-001",
            account_id="acc-001",
            tier=1,
            started_at="2026-03-12T10:00:00Z",
        )
        assert job.status == "queued"
        assert job.items_seen == 0
        assert job.api_calls == 0

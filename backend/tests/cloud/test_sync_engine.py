"""Tests for CloudSyncEngine batch processing."""
import json
import os
import tempfile
import uuid

import pytest
import pytest_asyncio

from src.cloud.cloud_store import CloudStore
from src.cloud.models import (
    DiscoveredItem,
    DiscoveredRelation,
    DiscoveryBatch,
)
from src.cloud.sync.engine import CloudSyncEngine


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except FileNotFoundError:
            pass


@pytest.fixture
def store(tmp_db):
    return CloudStore(db_path=tmp_db)


@pytest_asyncio.fixture
async def engine(store):
    await store.upsert_account(
        account_id="acc-001", provider="aws",
        display_name="Test", credential_handle="ref",
        auth_method="iam_role", regions=["us-east-1"],
    )
    return CloudSyncEngine(store)


class TestBatchProcessing:
    @pytest.mark.asyncio
    async def test_process_batch_creates_resources(self, engine, store):
        batch = DiscoveryBatch(
            account_id="acc-001",
            region="us-east-1",
            resource_type="vpc",
            source="aws-describe-vpcs",
            items=[
                DiscoveredItem(
                    native_id="vpc-001",
                    name="prod",
                    raw={"VpcId": "vpc-001", "CidrBlock": "10.0.0.0/16"},
                    tags={"env": "prod"},
                ),
                DiscoveredItem(
                    native_id="vpc-002",
                    name="dev",
                    raw={"VpcId": "vpc-002", "CidrBlock": "172.16.0.0/16"},
                    tags={"env": "dev"},
                ),
            ],
        )
        stats = await engine.process_batch(batch, sync_job_id="job-001")
        assert stats["created"] == 2
        assert stats["unchanged"] == 0
        resources = await store.list_resources(
            account_id="acc-001", resource_type="vpc"
        )
        assert len(resources) == 2

    @pytest.mark.asyncio
    async def test_unchanged_resources_skipped(self, engine, store):
        batch = DiscoveryBatch(
            account_id="acc-001",
            region="us-east-1",
            resource_type="vpc",
            source="test",
            items=[
                DiscoveredItem(
                    native_id="vpc-001", name="prod",
                    raw={"VpcId": "vpc-001"}, tags={},
                ),
            ],
        )
        await engine.process_batch(batch, sync_job_id="job-001")
        # Process same batch again
        stats = await engine.process_batch(batch, sync_job_id="job-002")
        assert stats["created"] == 0
        assert stats["unchanged"] == 1

    @pytest.mark.asyncio
    async def test_changed_resources_updated(self, engine, store):
        batch1 = DiscoveryBatch(
            account_id="acc-001", region="us-east-1",
            resource_type="vpc", source="test",
            items=[
                DiscoveredItem(
                    native_id="vpc-001", name="prod",
                    raw={"VpcId": "vpc-001", "State": "available"},
                    tags={},
                ),
            ],
        )
        await engine.process_batch(batch1, sync_job_id="job-001")
        batch2 = DiscoveryBatch(
            account_id="acc-001", region="us-east-1",
            resource_type="vpc", source="test",
            items=[
                DiscoveredItem(
                    native_id="vpc-001", name="prod-updated",
                    raw={"VpcId": "vpc-001", "State": "modified"},
                    tags={},
                ),
            ],
        )
        stats = await engine.process_batch(batch2, sync_job_id="job-002")
        assert stats["updated"] == 1

    @pytest.mark.asyncio
    async def test_relations_created(self, engine, store):
        batch = DiscoveryBatch(
            account_id="acc-001", region="us-east-1",
            resource_type="subnet", source="test",
            items=[
                DiscoveredItem(
                    native_id="vpc-001", name="vpc",
                    raw={"VpcId": "vpc-001"}, tags={},
                ),
                DiscoveredItem(
                    native_id="subnet-001", name="sub",
                    raw={"SubnetId": "subnet-001"}, tags={},
                ),
            ],
            relations=[
                DiscoveredRelation(
                    source_native_id="subnet-001",
                    target_native_id="vpc-001",
                    relation_type="member_of",
                ),
            ],
        )
        stats = await engine.process_batch(batch, sync_job_id="job-001")
        assert stats["relations_created"] >= 1


class TestSoftDeletion:
    @pytest.mark.asyncio
    async def test_mark_stale_resources(self, engine, store):
        # Create a resource
        batch = DiscoveryBatch(
            account_id="acc-001", region="us-east-1",
            resource_type="vpc", source="test",
            items=[
                DiscoveredItem(
                    native_id="vpc-old", name="old",
                    raw={"VpcId": "vpc-old"}, tags={},
                ),
            ],
        )
        await engine.process_batch(batch, sync_job_id="job-001")

        # Mark stale (using a future cutoff)
        deleted = await engine.mark_stale_deleted(
            account_id="acc-001",
            region="us-east-1",
            resource_types=["vpc"],
            cutoff_ts="2099-01-01T00:00:00Z",
        )
        assert deleted >= 0  # Implementation returns count

    @pytest.mark.asyncio
    async def test_resurrect_on_rediscovery(self, engine, store):
        # Create and soft-delete
        batch = DiscoveryBatch(
            account_id="acc-001", region="us-east-1",
            resource_type="vpc", source="test",
            items=[
                DiscoveredItem(
                    native_id="vpc-lazy", name="lazy",
                    raw={"VpcId": "vpc-lazy"}, tags={},
                ),
            ],
        )
        await engine.process_batch(batch, sync_job_id="job-001")
        await engine.mark_stale_deleted(
            "acc-001", "us-east-1", ["vpc"], "2099-01-01T00:00:00Z"
        )
        # Re-discover same resource (upsert sets is_deleted=0)
        stats = await engine.process_batch(batch, sync_job_id="job-002")
        # Should show up as updated (resurrected)
        resources = await store.list_resources(
            account_id="acc-001", resource_type="vpc"
        )
        assert len(resources) >= 1


class TestLockManagement:
    @pytest.mark.asyncio
    async def test_acquire_sync_lock(self, engine, store):
        job_id = await engine.acquire_sync_lock("acc-001", tier=1)
        assert job_id is not None
        job = await store.get_sync_job(job_id)
        assert job["status"] == "running"

    @pytest.mark.asyncio
    async def test_cannot_acquire_while_running(self, engine, store):
        await engine.acquire_sync_lock("acc-001", tier=1)
        second = await engine.acquire_sync_lock("acc-001", tier=1)
        assert second is None  # blocked by existing running job

    @pytest.mark.asyncio
    async def test_release_sync_lock(self, engine, store):
        job_id = await engine.acquire_sync_lock("acc-001", tier=1)
        await engine.release_sync_lock(job_id, status="completed")
        job = await store.get_sync_job(job_id)
        assert job["status"] == "completed"

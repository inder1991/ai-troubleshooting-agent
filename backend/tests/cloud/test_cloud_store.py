"""Tests for CloudStore — thread-safe SQLite store."""
import asyncio
import json
import os
import tempfile
import uuid

import pytest

from src.cloud.cloud_store import CloudStore


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


class TestCloudStoreInit:
    def test_creates_tables(self, store, tmp_db):
        """All 7 tables should exist after init."""
        import sqlite3
        conn = sqlite3.connect(tmp_db)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        expected = {
            "cloud_accounts",
            "cloud_resources",
            "cloud_resource_relations",
            "cloud_sync_jobs",
            "policy_groups",
            "policy_rules",
            "policy_attachments",
        }
        assert expected.issubset(tables)

    def test_wal_mode_enabled(self, store, tmp_db):
        import sqlite3
        conn = sqlite3.connect(tmp_db)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"


class TestCloudAccountCRUD:
    @pytest.mark.asyncio
    async def test_upsert_and_get_account(self, store):
        await store.upsert_account(
            account_id="acc-001",
            provider="aws",
            display_name="Prod AWS",
            credential_handle="ref-001",
            auth_method="iam_role",
            regions=["us-east-1"],
        )
        account = await store.get_account("acc-001")
        assert account is not None
        assert account["provider"] == "aws"
        assert account["display_name"] == "Prod AWS"
        assert json.loads(account["regions"]) == ["us-east-1"]

    @pytest.mark.asyncio
    async def test_list_accounts(self, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="AWS 1", credential_handle="r1",
            auth_method="iam_role", regions=["us-east-1"],
        )
        await store.upsert_account(
            account_id="acc-002", provider="azure",
            display_name="Azure 1", credential_handle="r2",
            auth_method="azure_sp", regions=["eastus"],
        )
        accounts = await store.list_accounts()
        assert len(accounts) == 2

    @pytest.mark.asyncio
    async def test_delete_account(self, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="AWS", credential_handle="r1",
            auth_method="iam_role", regions=["us-east-1"],
        )
        await store.delete_account("acc-001")
        assert await store.get_account("acc-001") is None


class TestCloudResourceCRUD:
    @pytest.mark.asyncio
    async def test_upsert_resource(self, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="AWS", credential_handle="r",
            auth_method="iam_role", regions=["us-east-1"],
        )
        await store.upsert_resource(
            resource_id="res-001",
            provider="aws",
            account_id="acc-001",
            region="us-east-1",
            resource_type="vpc",
            native_id="vpc-abc",
            name="prod-vpc",
            raw_compressed=b"compressed",
            raw_preview='{"VpcId":"vpc-abc"}',
            tags=json.dumps({"env": "prod"}),
            resource_hash="hash123",
            source="aws-describe-vpcs",
            sync_job_id="job-001",
            sync_tier=1,
        )
        res = await store.get_resource("res-001")
        assert res is not None
        assert res["native_id"] == "vpc-abc"
        assert res["resource_hash"] == "hash123"

    @pytest.mark.asyncio
    async def test_list_resources_by_type(self, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="AWS", credential_handle="r",
            auth_method="iam_role", regions=["us-east-1"],
        )
        for i in range(3):
            await store.upsert_resource(
                resource_id=f"res-{i}",
                provider="aws", account_id="acc-001",
                region="us-east-1", resource_type="vpc",
                native_id=f"vpc-{i}", raw_compressed=b"data",
                resource_hash=f"h{i}", source="test", sync_tier=1,
            )
        results = await store.list_resources(
            account_id="acc-001", region="us-east-1", resource_type="vpc"
        )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_hash_check_skips_unchanged(self, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="AWS", credential_handle="r",
            auth_method="iam_role", regions=["us-east-1"],
        )
        await store.upsert_resource(
            resource_id="res-001", provider="aws",
            account_id="acc-001", region="us-east-1",
            resource_type="vpc", native_id="vpc-abc",
            raw_compressed=b"data", resource_hash="same_hash",
            source="test", sync_tier=1,
        )
        existing = await store.get_resource_hash(
            provider="aws", account_id="acc-001",
            region="us-east-1", native_id="vpc-abc",
        )
        assert existing == "same_hash"


class TestCloudSyncJobCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get_job(self, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="AWS", credential_handle="r",
            auth_method="iam_role", regions=["us-east-1"],
        )
        await store.create_sync_job(
            sync_job_id="job-001",
            account_id="acc-001",
            tier=1,
        )
        job = await store.get_sync_job("job-001")
        assert job is not None
        assert job["status"] == "running"

    @pytest.mark.asyncio
    async def test_complete_job(self, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="AWS", credential_handle="r",
            auth_method="iam_role", regions=["us-east-1"],
        )
        await store.create_sync_job(
            sync_job_id="job-001", account_id="acc-001", tier=1,
        )
        await store.complete_sync_job(
            sync_job_id="job-001",
            status="completed",
            items_seen=100, items_created=10,
            items_updated=5, items_deleted=2,
            api_calls=15,
        )
        job = await store.get_sync_job("job-001")
        assert job["status"] == "completed"
        assert job["items_seen"] == 100

    @pytest.mark.asyncio
    async def test_find_running_job(self, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="AWS", credential_handle="r",
            auth_method="iam_role", regions=["us-east-1"],
        )
        await store.create_sync_job(
            sync_job_id="job-001", account_id="acc-001", tier=1,
        )
        running = await store.find_running_job("acc-001", tier=1)
        assert running is not None
        assert running["sync_job_id"] == "job-001"

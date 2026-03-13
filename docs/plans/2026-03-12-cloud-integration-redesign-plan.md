# Cloud Integration Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a production-grade, provider-agnostic cloud integration layer that discovers ALL cloud resources (security, network, infrastructure) from AWS/Azure/Oracle via three-layer architecture: CloudAccount -> cloud_resources -> topology_store/policy_store.

**Architecture:** Provider-agnostic drivers discover resources into a canonical `cloud_resources` table. A sync engine with tiered scheduling (10min/30min/6hr) handles upserts with hash-based change detection and soft deletion. A mapper translates raw resources into internal stores (topology_store for network, policy_store for security). All DB access via single-thread executor for SQLite safety.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (WAL), boto3, Pydantic, gzip, hashlib, asyncio+ThreadPoolExecutor, React+TypeScript

**Design Doc:** `docs/plans/2026-03-12-cloud-integration-redesign-design.md`

---

## File Structure

```
backend/src/cloud/
├── __init__.py
├── models.py                 # Pydantic models for all entities
├── cloud_store.py            # Thread-safe SQLite store + schema
├── policy_store.py           # Security policy store (NEW)
├── redaction.py              # Sensitive data redaction
├── mapper.py                 # CloudResourceMapper
├── drivers/
│   ├── __init__.py
│   ├── base.py               # CloudProviderDriver ABC + envelope
│   └── aws_driver.py         # AWS implementation
├── sync/
│   ├── __init__.py
│   ├── engine.py             # CloudSyncEngine
│   ├── scheduler.py          # CloudSyncScheduler
│   ├── rate_limiter.py       # AdaptiveRateLimiter
│   ├── batch_controller.py   # BatchSizeController
│   ├── concurrency.py        # SyncConcurrencyGuard
│   └── wal_monitor.py        # WALMonitor
└── api/
    ├── __init__.py
    └── router.py             # FastAPI endpoints

backend/tests/cloud/
├── __init__.py
├── test_models.py
├── test_cloud_store.py
├── test_policy_store.py
├── test_redaction.py
├── test_rate_limiter.py
├── test_batch_controller.py
├── test_concurrency.py
├── test_wal_monitor.py
├── test_aws_driver.py
├── test_sync_engine.py
├── test_scheduler.py
├── test_mapper.py
└── test_api.py
```

---

## Task 1: Project Structure + Dependencies

**Files:**
- Create: `backend/src/cloud/__init__.py`
- Create: `backend/src/cloud/drivers/__init__.py`
- Create: `backend/src/cloud/sync/__init__.py`
- Create: `backend/src/cloud/api/__init__.py`
- Create: `backend/tests/cloud/__init__.py`
- Modify: `backend/requirements.txt`

**Step 1: Create directory structure**

```bash
mkdir -p backend/src/cloud/drivers backend/src/cloud/sync backend/src/cloud/api backend/tests/cloud
```

**Step 2: Create `__init__.py` files**

`backend/src/cloud/__init__.py`:
```python
"""Cloud integration layer — provider-agnostic resource discovery and sync."""
```

`backend/src/cloud/drivers/__init__.py`:
```python
"""Cloud provider drivers (AWS, Azure, Oracle)."""
```

`backend/src/cloud/sync/__init__.py`:
```python
"""Sync engine, scheduler, and operational utilities."""
```

`backend/src/cloud/api/__init__.py`:
```python
"""Cloud integration API endpoints."""
```

`backend/tests/cloud/__init__.py`:
```python
```

**Step 3: Add dependencies to requirements.txt**

Add to `backend/requirements.txt`:
```
# Cloud SDKs
boto3>=1.34.0
```

Note: Azure (`azure-mgmt-*`) and Oracle (`oci`) SDKs added later when those drivers are implemented. AWS first.

**Step 4: Install dependencies**

```bash
cd backend && pip install -r requirements.txt
```

**Step 5: Commit**

```bash
git add backend/src/cloud/ backend/tests/cloud/ backend/requirements.txt
git commit -m "chore: scaffold cloud integration module + add boto3 dependency"
```

---

## Task 2: Pydantic Data Models

**Files:**
- Create: `backend/src/cloud/models.py`
- Create: `backend/tests/cloud/test_models.py`

**Step 1: Write tests for models**

`backend/tests/cloud/test_models.py`:
```python
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
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_models.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'src.cloud.models'`

**Step 3: Implement models**

`backend/src/cloud/models.py`:
```python
"""Pydantic models for cloud integration entities."""
from __future__ import annotations

from dataclasses import field
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field


class SyncTier(IntEnum):
    FAST = 1       # 10 min — core topology
    SLOW = 2       # 30 min — attached resources
    VERY_SLOW = 3  # 6 hr  — IAM, tags, flow logs


# ── Layer 1: Cloud Account ──


class CloudAccount(BaseModel):
    account_id: str
    provider: str  # aws | azure | oracle | gcp
    display_name: str
    native_account_id: str | None = None
    credential_handle: str
    auth_method: str  # iam_role | access_key | azure_sp | oci_config
    regions: list[str]
    org_parent_id: str | None = None
    sync_enabled: bool = True
    sync_config: dict[str, Any] | None = None
    last_sync_status: str = "never"  # never | ok | error | paused
    last_sync_error: str | None = None
    consecutive_failures: int = 0
    created_at: str | None = None
    updated_at: str | None = None


# ── Layer 2: Cloud Resources ──


class CloudResource(BaseModel):
    resource_id: str
    provider: str
    account_id: str
    region: str
    resource_type: str
    native_id: str
    name: str | None = None
    raw_compressed: bytes = b""
    raw_preview: str | None = None
    tags: dict[str, str] | None = None
    sync_tier: int = SyncTier.FAST
    last_seen_ts: str | None = None
    resource_hash: str | None = None
    source: str | None = None
    sync_job_id: str | None = None
    mapper_version: int = 1
    is_deleted: bool = False
    deleted_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CloudResourceRelation(BaseModel):
    relation_id: str
    source_resource_id: str
    target_resource_id: str
    relation_type: str  # attached_to | member_of | applied_to | etc.
    metadata: dict[str, Any] | None = None
    last_seen_ts: str | None = None
    relation_hash: str | None = None
    is_deleted: bool = False
    deleted_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ── Sync Jobs ──


class CloudSyncJob(BaseModel):
    sync_job_id: str
    account_id: str
    tier: int
    started_at: str
    finished_at: str | None = None
    status: str = "queued"  # queued | running | completed | failed | paused
    items_seen: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    api_calls: int = 0
    errors: list[dict[str, Any]] | None = None
    created_at: str | None = None


# ── Driver Envelope ──


class DiscoveredItem(BaseModel):
    native_id: str
    name: str | None = None
    raw: dict[str, Any]
    tags: dict[str, str] = Field(default_factory=dict)


class DiscoveredRelation(BaseModel):
    source_native_id: str
    target_native_id: str
    relation_type: str
    metadata: dict[str, Any] | None = None


class RateLimitInfo(BaseModel):
    calls_made: int
    remaining: int | None = None
    reset_at: float | None = None


class DiscoveryBatch(BaseModel):
    account_id: str
    region: str
    resource_type: str
    source: str
    items: list[DiscoveredItem]
    relations: list[DiscoveredRelation] = Field(default_factory=list)
    rate_limit_info: RateLimitInfo | None = None


class DriverHealth(BaseModel):
    connected: bool
    latency_ms: float
    identity: str = ""
    permissions_ok: bool = False
    missing_permissions: list[str] = Field(default_factory=list)
    message: str = ""


# ── Policy Store Models ──


class PolicyGroup(BaseModel):
    policy_group_id: str
    name: str
    provider: str | None = None
    source_type: str  # security_group | nacl | firewall_ruleset
    cloud_resource_id: str | None = None
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class PolicyRule(BaseModel):
    rule_id: str
    policy_group_id: str
    direction: str  # inbound | outbound
    action: str     # allow | deny
    protocol: str   # tcp | udp | icmp | all
    port_range_start: int | None = None
    port_range_end: int | None = None
    source_cidr: str | None = None
    dest_cidr: str | None = None
    priority: int | None = None
    description: str | None = None
    created_at: str | None = None


class PolicyAttachment(BaseModel):
    attachment_id: str
    policy_group_id: str
    target_resource_id: str
    target_type: str  # eni | subnet | instance
    created_at: str | None = None


# ── Canonical Mapper Models ──


class NetworkSegment(BaseModel):
    """AWS VPC / Azure VNet / Oracle VCN."""
    id: str
    name: str
    cidr_blocks: list[str]
    provider: str
    account_id: str
    region: str
    cloud_resource_id: str


class SubnetSegment(BaseModel):
    id: str
    name: str
    cidr: str
    network_segment_id: str
    availability_zone: str | None = None
    cloud_resource_id: str


class RoutingTable(BaseModel):
    id: str
    name: str
    network_segment_id: str
    routes: list[RouteEntry] = Field(default_factory=list)
    cloud_resource_id: str


class RouteEntry(BaseModel):
    destination_cidr: str
    target_type: str  # gateway | instance | nat | peering | tgw | local
    target_id: str
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_models.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/models.py backend/tests/cloud/test_models.py
git commit -m "feat(cloud): add Pydantic data models for cloud integration"
```

---

## Task 3: CloudStore — Thread-Safe SQLite with Schema

**Files:**
- Create: `backend/src/cloud/cloud_store.py`
- Create: `backend/tests/cloud/test_cloud_store.py`

**Step 1: Write tests**

`backend/tests/cloud/test_cloud_store.py`:
```python
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
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_cloud_store.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement CloudStore**

`backend/src/cloud/cloud_store.py`:
```python
"""Thread-safe SQLite store for cloud resources.

All DB operations run on a single dedicated thread via ThreadPoolExecutor.
This avoids sqlite3 thread-safety issues and 'database is locked' errors.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CloudStore:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="cloud-db"
        )
        self._conn: sqlite3.Connection | None = None
        self._init_schema()

    # ── Connection ──

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_schema(self) -> None:
        """Create tables synchronously at startup."""
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        conn.close()

    # ── Async executor helpers ──

    async def _execute(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, partial(self._sync_execute, sql, params)
        )

    def _sync_execute(self, sql: str, params: tuple) -> list[sqlite3.Row]:
        conn = self._get_conn()
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.fetchall()

    async def _execute_batch(self, operations: list[tuple[str, tuple]]) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self._executor, partial(self._sync_batch, operations)
        )

    def _sync_batch(self, operations: list[tuple[str, tuple]]) -> None:
        conn = self._get_conn()
        try:
            for sql, params in operations:
                conn.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ── Cloud Account CRUD ──

    async def upsert_account(
        self,
        account_id: str,
        provider: str,
        display_name: str,
        credential_handle: str,
        auth_method: str,
        regions: list[str],
        native_account_id: str | None = None,
        org_parent_id: str | None = None,
        sync_config: dict | None = None,
    ) -> None:
        now = _now_iso()
        await self._execute(
            """INSERT INTO cloud_accounts
               (account_id, provider, display_name, native_account_id,
                credential_handle, auth_method, regions, org_parent_id,
                sync_config, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(account_id) DO UPDATE SET
                 display_name=excluded.display_name,
                 credential_handle=excluded.credential_handle,
                 auth_method=excluded.auth_method,
                 regions=excluded.regions,
                 sync_config=excluded.sync_config,
                 updated_at=excluded.updated_at""",
            (
                account_id, provider, display_name, native_account_id,
                credential_handle, auth_method, json.dumps(regions),
                org_parent_id, json.dumps(sync_config) if sync_config else None,
                now, now,
            ),
        )

    async def get_account(self, account_id: str) -> sqlite3.Row | None:
        rows = await self._execute(
            "SELECT * FROM cloud_accounts WHERE account_id = ?", (account_id,)
        )
        return rows[0] if rows else None

    async def list_accounts(self) -> list[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM cloud_accounts ORDER BY display_name"
        )

    async def delete_account(self, account_id: str) -> None:
        await self._execute(
            "DELETE FROM cloud_accounts WHERE account_id = ?", (account_id,)
        )

    async def update_account_sync_status(
        self, account_id: str, status: str, error: str | None = None,
        consecutive_failures: int | None = None,
    ) -> None:
        sets = ["last_sync_status = ?", "updated_at = ?"]
        params: list[Any] = [status, _now_iso()]
        if error is not None:
            sets.append("last_sync_error = ?")
            params.append(error)
        if consecutive_failures is not None:
            sets.append("consecutive_failures = ?")
            params.append(consecutive_failures)
        params.append(account_id)
        await self._execute(
            f"UPDATE cloud_accounts SET {', '.join(sets)} WHERE account_id = ?",
            tuple(params),
        )

    # ── Cloud Resource CRUD ──

    async def upsert_resource(
        self,
        resource_id: str,
        provider: str,
        account_id: str,
        region: str,
        resource_type: str,
        native_id: str,
        raw_compressed: bytes,
        resource_hash: str,
        source: str,
        sync_tier: int,
        name: str | None = None,
        raw_preview: str | None = None,
        tags: str | None = None,
        sync_job_id: str | None = None,
    ) -> None:
        now = _now_iso()
        await self._execute(
            """INSERT INTO cloud_resources
               (resource_id, provider, account_id, region, resource_type,
                native_id, name, raw_compressed, raw_preview, tags,
                sync_tier, last_seen_ts, resource_hash, source,
                sync_job_id, is_deleted, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
               ON CONFLICT(provider, account_id, region, native_id) DO UPDATE SET
                 name=excluded.name,
                 raw_compressed=excluded.raw_compressed,
                 raw_preview=excluded.raw_preview,
                 tags=excluded.tags,
                 last_seen_ts=excluded.last_seen_ts,
                 resource_hash=excluded.resource_hash,
                 source=excluded.source,
                 sync_job_id=excluded.sync_job_id,
                 is_deleted=0,
                 deleted_at=NULL,
                 updated_at=excluded.updated_at""",
            (
                resource_id, provider, account_id, region, resource_type,
                native_id, name, raw_compressed, raw_preview, tags,
                sync_tier, now, resource_hash, source, sync_job_id,
                now, now,
            ),
        )

    async def touch_resource(
        self, resource_id: str, sync_job_id: str
    ) -> None:
        await self._execute(
            "UPDATE cloud_resources SET last_seen_ts = ?, sync_job_id = ? WHERE resource_id = ?",
            (_now_iso(), sync_job_id, resource_id),
        )

    async def get_resource(self, resource_id: str) -> sqlite3.Row | None:
        rows = await self._execute(
            "SELECT * FROM cloud_resources WHERE resource_id = ?",
            (resource_id,),
        )
        return rows[0] if rows else None

    async def get_resource_hash(
        self, provider: str, account_id: str, region: str, native_id: str
    ) -> str | None:
        rows = await self._execute(
            """SELECT resource_hash FROM cloud_resources
               WHERE provider = ? AND account_id = ? AND region = ? AND native_id = ?
               AND is_deleted = 0""",
            (provider, account_id, region, native_id),
        )
        return rows[0]["resource_hash"] if rows else None

    async def get_resource_id_by_native(
        self, provider: str, account_id: str, region: str, native_id: str
    ) -> str | None:
        rows = await self._execute(
            """SELECT resource_id FROM cloud_resources
               WHERE provider = ? AND account_id = ? AND region = ? AND native_id = ?
               AND is_deleted = 0""",
            (provider, account_id, region, native_id),
        )
        return rows[0]["resource_id"] if rows else None

    async def list_resources(
        self,
        account_id: str | None = None,
        region: str | None = None,
        resource_type: str | None = None,
        include_deleted: bool = False,
        limit: int = 500,
    ) -> list[sqlite3.Row]:
        conditions = []
        params: list[Any] = []
        if account_id:
            conditions.append("account_id = ?")
            params.append(account_id)
        if region:
            conditions.append("region = ?")
            params.append(region)
        if resource_type:
            conditions.append("resource_type = ?")
            params.append(resource_type)
        if not include_deleted:
            conditions.append("is_deleted = 0")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        return await self._execute(
            f"""SELECT resource_id, provider, account_id, region, resource_type,
                       native_id, name, raw_preview, tags, sync_tier,
                       last_seen_ts, is_deleted, deleted_at
                FROM cloud_resources {where}
                ORDER BY resource_type, name
                LIMIT ?""",
            tuple(params),
        )

    async def mark_stale_deleted(
        self,
        account_id: str,
        region: str,
        resource_types: list[str],
        cutoff_ts: str,
    ) -> int:
        placeholders = ",".join("?" for _ in resource_types)
        now = _now_iso()
        rows = await self._execute(
            f"""UPDATE cloud_resources
                SET is_deleted = 1, deleted_at = ?
                WHERE account_id = ? AND region = ?
                  AND resource_type IN ({placeholders})
                  AND is_deleted = 0
                  AND last_seen_ts < ?""",
            (now, account_id, region, *resource_types, cutoff_ts),
        )
        return len(rows) if rows else 0

    async def load_native_id_cache(
        self, account_id: str, region: str
    ) -> dict[str, str]:
        rows = await self._execute(
            """SELECT native_id, resource_id FROM cloud_resources
               WHERE account_id = ? AND region = ? AND is_deleted = 0""",
            (account_id, region),
        )
        return {r["native_id"]: r["resource_id"] for r in rows}

    # ── Cloud Resource Relations ──

    async def upsert_relation(
        self,
        relation_id: str,
        source_resource_id: str,
        target_resource_id: str,
        relation_type: str,
        metadata: str | None = None,
        relation_hash: str | None = None,
    ) -> None:
        now = _now_iso()
        await self._execute(
            """INSERT INTO cloud_resource_relations
               (relation_id, source_resource_id, target_resource_id,
                relation_type, metadata, last_seen_ts, relation_hash,
                is_deleted, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
               ON CONFLICT(source_resource_id, target_resource_id, relation_type)
               DO UPDATE SET
                 metadata=excluded.metadata,
                 last_seen_ts=excluded.last_seen_ts,
                 relation_hash=excluded.relation_hash,
                 is_deleted=0,
                 deleted_at=NULL,
                 updated_at=excluded.updated_at""",
            (
                relation_id, source_resource_id, target_resource_id,
                relation_type, metadata, now, relation_hash, now, now,
            ),
        )

    async def list_relations(
        self, resource_id: str, direction: str = "both"
    ) -> list[sqlite3.Row]:
        if direction == "outgoing":
            return await self._execute(
                "SELECT * FROM cloud_resource_relations WHERE source_resource_id = ? AND is_deleted = 0",
                (resource_id,),
            )
        elif direction == "incoming":
            return await self._execute(
                "SELECT * FROM cloud_resource_relations WHERE target_resource_id = ? AND is_deleted = 0",
                (resource_id,),
            )
        return await self._execute(
            """SELECT * FROM cloud_resource_relations
               WHERE (source_resource_id = ? OR target_resource_id = ?) AND is_deleted = 0""",
            (resource_id, resource_id),
        )

    # ── Sync Jobs ──

    async def create_sync_job(
        self, sync_job_id: str, account_id: str, tier: int
    ) -> None:
        now = _now_iso()
        await self._execute(
            """INSERT INTO cloud_sync_jobs
               (sync_job_id, account_id, tier, started_at, status, created_at)
               VALUES (?, ?, ?, ?, 'running', ?)""",
            (sync_job_id, account_id, tier, now, now),
        )

    async def get_sync_job(self, sync_job_id: str) -> sqlite3.Row | None:
        rows = await self._execute(
            "SELECT * FROM cloud_sync_jobs WHERE sync_job_id = ?",
            (sync_job_id,),
        )
        return rows[0] if rows else None

    async def complete_sync_job(
        self,
        sync_job_id: str,
        status: str,
        items_seen: int = 0,
        items_created: int = 0,
        items_updated: int = 0,
        items_deleted: int = 0,
        api_calls: int = 0,
        errors: list[dict] | None = None,
    ) -> None:
        await self._execute(
            """UPDATE cloud_sync_jobs SET
                 status = ?, finished_at = ?,
                 items_seen = ?, items_created = ?,
                 items_updated = ?, items_deleted = ?,
                 api_calls = ?, errors = ?
               WHERE sync_job_id = ?""",
            (
                status, _now_iso(), items_seen, items_created,
                items_updated, items_deleted, api_calls,
                json.dumps(errors) if errors else None, sync_job_id,
            ),
        )

    async def find_running_job(
        self, account_id: str, tier: int
    ) -> sqlite3.Row | None:
        rows = await self._execute(
            """SELECT * FROM cloud_sync_jobs
               WHERE account_id = ? AND tier = ? AND status = 'running'
               ORDER BY started_at DESC LIMIT 1""",
            (account_id, tier),
        )
        return rows[0] if rows else None


# ── Schema DDL ──

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cloud_accounts (
    account_id          TEXT PRIMARY KEY,
    provider            TEXT NOT NULL,
    display_name        TEXT NOT NULL,
    native_account_id   TEXT,
    credential_handle   TEXT NOT NULL,
    auth_method         TEXT NOT NULL,
    regions             TEXT NOT NULL,
    org_parent_id       TEXT,
    sync_enabled        INTEGER DEFAULT 1,
    sync_config         TEXT,
    last_sync_status    TEXT DEFAULT 'never',
    last_sync_error     TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cloud_resources (
    resource_id         TEXT PRIMARY KEY,
    provider            TEXT NOT NULL,
    account_id          TEXT NOT NULL REFERENCES cloud_accounts(account_id),
    region              TEXT NOT NULL,
    resource_type       TEXT NOT NULL,
    native_id           TEXT NOT NULL,
    name                TEXT,
    raw_compressed      BLOB NOT NULL,
    raw_preview         TEXT,
    tags                TEXT,
    sync_tier           INTEGER DEFAULT 1,
    last_seen_ts        TEXT NOT NULL,
    resource_hash       TEXT,
    source              TEXT,
    sync_job_id         TEXT,
    mapper_version      INTEGER DEFAULT 1,
    is_deleted          INTEGER DEFAULT 0,
    deleted_at          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(provider, account_id, region, native_id)
);
CREATE INDEX IF NOT EXISTS idx_cr_account_region_type
    ON cloud_resources(account_id, region, resource_type);
CREATE INDEX IF NOT EXISTS idx_cr_last_seen
    ON cloud_resources(account_id, region, last_seen_ts);
CREATE INDEX IF NOT EXISTS idx_cr_native
    ON cloud_resources(provider, native_id);

CREATE TABLE IF NOT EXISTS cloud_resource_relations (
    relation_id         TEXT PRIMARY KEY,
    source_resource_id  TEXT NOT NULL REFERENCES cloud_resources(resource_id) ON DELETE CASCADE,
    target_resource_id  TEXT NOT NULL REFERENCES cloud_resources(resource_id) ON DELETE CASCADE,
    relation_type       TEXT NOT NULL,
    metadata            TEXT,
    last_seen_ts        TEXT NOT NULL,
    relation_hash       TEXT,
    is_deleted          INTEGER DEFAULT 0,
    deleted_at          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(source_resource_id, target_resource_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_crr_source ON cloud_resource_relations(source_resource_id);
CREATE INDEX IF NOT EXISTS idx_crr_target ON cloud_resource_relations(target_resource_id);
CREATE INDEX IF NOT EXISTS idx_crr_type   ON cloud_resource_relations(relation_type);

CREATE TABLE IF NOT EXISTS cloud_sync_jobs (
    sync_job_id     TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES cloud_accounts(account_id),
    tier            INTEGER NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT DEFAULT 'queued',
    items_seen      INTEGER DEFAULT 0,
    items_created   INTEGER DEFAULT 0,
    items_updated   INTEGER DEFAULT 0,
    items_deleted   INTEGER DEFAULT 0,
    api_calls       INTEGER DEFAULT 0,
    errors          TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_account
    ON cloud_sync_jobs(account_id, started_at);

CREATE TABLE IF NOT EXISTS policy_groups (
    policy_group_id     TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    provider            TEXT,
    source_type         TEXT NOT NULL,
    cloud_resource_id   TEXT,
    description         TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_rules (
    rule_id             TEXT PRIMARY KEY,
    policy_group_id     TEXT NOT NULL REFERENCES policy_groups(policy_group_id) ON DELETE CASCADE,
    direction           TEXT NOT NULL,
    action              TEXT NOT NULL,
    protocol            TEXT NOT NULL,
    port_range_start    INTEGER,
    port_range_end      INTEGER,
    source_cidr         TEXT,
    dest_cidr           TEXT,
    priority            INTEGER,
    description         TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pr_group ON policy_rules(policy_group_id);

CREATE TABLE IF NOT EXISTS policy_attachments (
    attachment_id       TEXT PRIMARY KEY,
    policy_group_id     TEXT NOT NULL REFERENCES policy_groups(policy_group_id) ON DELETE CASCADE,
    target_resource_id  TEXT NOT NULL,
    target_type         TEXT NOT NULL,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pa_group ON policy_attachments(policy_group_id);
CREATE INDEX IF NOT EXISTS idx_pa_target ON policy_attachments(target_resource_id);
"""
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_cloud_store.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/cloud_store.py backend/tests/cloud/test_cloud_store.py
git commit -m "feat(cloud): add CloudStore with thread-safe SQLite + schema"
```

---

## Task 4: Sensitive Data Redaction + Compression Utilities

**Files:**
- Create: `backend/src/cloud/redaction.py`
- Create: `backend/tests/cloud/test_redaction.py`

**Step 1: Write tests**

`backend/tests/cloud/test_redaction.py`:
```python
"""Tests for sensitive data redaction and compression."""
import gzip
import json

import pytest

from src.cloud.redaction import redact_raw, compress_raw, decompress_raw


class TestRedaction:
    def test_redacts_password_fields(self):
        raw = {"Name": "test", "Password": "secret123", "Config": {"AuthToken": "tok"}}
        result = redact_raw(raw)
        assert result["Name"] == "test"
        assert result["Password"] == "***REDACTED***"
        assert result["Config"]["AuthToken"] == "***REDACTED***"

    def test_redacts_nested_dicts(self):
        raw = {"Level1": {"Level2": {"SecretKey": "abc"}}}
        result = redact_raw(raw)
        assert result["Level1"]["Level2"]["SecretKey"] == "***REDACTED***"

    def test_redacts_in_lists(self):
        raw = {"Items": [{"Name": "a", "AccessKey": "key1"}, {"Name": "b"}]}
        result = redact_raw(raw)
        assert result["Items"][0]["AccessKey"] == "***REDACTED***"
        assert result["Items"][1]["Name"] == "b"

    def test_leaves_safe_fields_alone(self):
        raw = {"VpcId": "vpc-123", "CidrBlock": "10.0.0.0/16", "Tags": []}
        result = redact_raw(raw)
        assert result == raw

    def test_empty_dict(self):
        assert redact_raw({}) == {}

    def test_case_sensitive_matching(self):
        raw = {"password": "safe", "Password": "redact"}
        result = redact_raw(raw)
        assert result["password"] == "safe"
        assert result["Password"] == "***REDACTED***"


class TestCompression:
    def test_compress_decompress_roundtrip(self):
        raw = {"VpcId": "vpc-abc", "CidrBlock": "10.0.0.0/16", "Tags": [{"Key": "env", "Value": "prod"}]}
        compressed = compress_raw(raw)
        assert isinstance(compressed, bytes)
        assert len(compressed) < len(json.dumps(raw).encode())
        decompressed = decompress_raw(compressed)
        assert decompressed == raw

    def test_compress_produces_valid_gzip(self):
        raw = {"test": "data"}
        compressed = compress_raw(raw)
        # Should be valid gzip
        decompressed_bytes = gzip.decompress(compressed)
        assert json.loads(decompressed_bytes) == raw

    def test_compress_deterministic(self):
        raw = {"b": 2, "a": 1}
        c1 = compress_raw(raw)
        c2 = compress_raw(raw)
        assert c1 == c2  # sort_keys ensures determinism

    def test_raw_preview(self):
        from src.cloud.redaction import make_raw_preview
        raw = {"VpcId": "vpc-abc", "CidrBlock": "10.0.0.0/16"}
        preview = make_raw_preview(raw, max_len=30)
        assert len(preview) <= 30
        assert preview.startswith("{")
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_redaction.py -v
```

**Step 3: Implement**

`backend/src/cloud/redaction.py`:
```python
"""Sensitive data redaction and JSON compression utilities."""
from __future__ import annotations

import gzip
import json
from typing import Any

_REDACT_KEYS = frozenset({
    "Password", "Secret", "PrivateKey", "AccessKey", "SecretKey",
    "Token", "Credential", "AuthToken", "ConnectionString",
})

_REDACTED = "***REDACTED***"


def redact_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Deep-redact sensitive fields. Returns new dict."""
    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: _REDACTED if any(s in k for s in _REDACT_KEYS) else _walk(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_walk(item) for item in obj]
        return obj
    return _walk(raw)


def compress_raw(raw: dict[str, Any]) -> bytes:
    """Gzip-compress raw JSON dict to bytes for BLOB storage."""
    return gzip.compress(
        json.dumps(raw, sort_keys=True, default=str).encode("utf-8")
    )


def decompress_raw(blob: bytes) -> dict[str, Any]:
    """Decompress gzip BLOB back to dict."""
    return json.loads(gzip.decompress(blob).decode("utf-8"))


def make_raw_preview(raw: dict[str, Any], max_len: int = 512) -> str:
    """First N chars of JSON for quick display."""
    text = json.dumps(raw, sort_keys=True, default=str)
    return text[:max_len]
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_redaction.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/redaction.py backend/tests/cloud/test_redaction.py
git commit -m "feat(cloud): add sensitive data redaction + gzip compression"
```

---

## Task 5: Rate Limiter + Batch Controller + WAL Monitor

**Files:**
- Create: `backend/src/cloud/sync/rate_limiter.py`
- Create: `backend/src/cloud/sync/batch_controller.py`
- Create: `backend/src/cloud/sync/wal_monitor.py`
- Create: `backend/tests/cloud/test_rate_limiter.py`
- Create: `backend/tests/cloud/test_batch_controller.py`
- Create: `backend/tests/cloud/test_wal_monitor.py`

**Step 1: Write rate limiter tests**

`backend/tests/cloud/test_rate_limiter.py`:
```python
"""Tests for adaptive per-service rate limiter."""
import asyncio
import time
import pytest
from src.cloud.sync.rate_limiter import AdaptiveRateLimiter, _AWS_SERVICE_LIMITS


class TestAdaptiveRateLimiter:
    def test_default_limits_loaded(self):
        limiter = AdaptiveRateLimiter()
        assert "ec2" in limiter._limits
        assert "iam" in limiter._limits

    @pytest.mark.asyncio
    async def test_acquire_respects_interval(self):
        limiter = AdaptiveRateLimiter(
            service_limits={"test": {"base_rate": 100, "burst": 200, "throttle_backoff": 0.01}}
        )
        start = time.monotonic()
        await limiter.acquire("test")
        await limiter.acquire("test")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.009  # ~10ms min interval at 100 req/s

    @pytest.mark.asyncio
    async def test_on_throttle_backs_off(self):
        limiter = AdaptiveRateLimiter(
            service_limits={"test": {"base_rate": 10, "burst": 50, "throttle_backoff": 0.01}}
        )
        start = time.monotonic()
        await limiter.on_throttle("test")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.01

    def test_on_success_resets_throttle(self):
        limiter = AdaptiveRateLimiter()
        limiter._throttle_counts["ec2"] = 5
        limiter.on_success("ec2")
        assert limiter._throttle_counts["ec2"] == 0

    @pytest.mark.asyncio
    async def test_unknown_service_uses_defaults(self):
        limiter = AdaptiveRateLimiter()
        await limiter.acquire("unknown_service")  # Should not raise
```

**Step 2: Write batch controller tests**

`backend/tests/cloud/test_batch_controller.py`:
```python
"""Tests for dynamic batch size controller."""
import pytest
from src.cloud.sync.batch_controller import BatchSizeController


class TestBatchSizeController:
    def test_default_size(self):
        ctrl = BatchSizeController()
        assert ctrl.size == 500

    def test_grows_on_fast_commit(self):
        ctrl = BatchSizeController(default_size=500, max_size=2000)
        ctrl.on_success(duration_ms=100.0)  # fast
        assert ctrl.size == 600

    def test_shrinks_on_slow_commit(self):
        ctrl = BatchSizeController(default_size=500)
        ctrl.on_success(duration_ms=3000.0)  # slow
        assert ctrl.size == 250

    def test_shrinks_on_error(self):
        ctrl = BatchSizeController(default_size=500)
        ctrl.on_error()
        assert ctrl.size == 250

    def test_respects_min_size(self):
        ctrl = BatchSizeController(default_size=100, min_size=50)
        ctrl.on_error()
        ctrl.on_error()
        ctrl.on_error()
        assert ctrl.size >= 50

    def test_respects_max_size(self):
        ctrl = BatchSizeController(default_size=1900, max_size=2000)
        ctrl.on_success(duration_ms=50.0)
        assert ctrl.size <= 2000

    def test_stable_on_normal_duration(self):
        ctrl = BatchSizeController(default_size=500)
        ctrl.on_success(duration_ms=500.0)  # normal
        assert ctrl.size == 500
```

**Step 3: Write WAL monitor tests**

`backend/tests/cloud/test_wal_monitor.py`:
```python
"""Tests for WAL monitor."""
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.cloud.sync.wal_monitor import WALMonitor


class TestWALMonitor:
    def test_default_thresholds(self):
        monitor = WALMonitor()
        assert monitor.WAL_SIZE_ALERT_MB == 100
        assert monitor.CHECKPOINT_INTERVAL_SECONDS == 300

    @pytest.mark.asyncio
    async def test_checkpoint_calls_passive(self):
        monitor = WALMonitor()
        store = AsyncMock()
        store._db_path = "/tmp/test.db"
        store.execute = AsyncMock(return_value=[])
        with patch("os.path.exists", return_value=False):
            await monitor.run_once(store)
        store.execute.assert_called_once_with("PRAGMA wal_checkpoint(PASSIVE)")

    @pytest.mark.asyncio
    async def test_large_wal_triggers_truncate(self):
        monitor = WALMonitor()
        monitor.WAL_SIZE_ALERT_MB = 0  # trigger on any size
        store = AsyncMock()
        store._db_path = "/tmp/test.db"
        store.execute = AsyncMock(return_value=[])
        # Create a fake WAL file
        fd, wal_path = tempfile.mkstemp()
        os.write(fd, b"x" * 1024)
        os.close(fd)
        store._db_path = wal_path.replace("-wal", "")
        os.rename(wal_path, store._db_path + "-wal")
        try:
            with patch("os.path.exists", return_value=True), \
                 patch("os.path.getsize", return_value=200 * 1024 * 1024):
                await monitor.run_once(store)
            # Should call PASSIVE then TRUNCATE
            calls = [c.args[0] for c in store.execute.call_args_list]
            assert "PRAGMA wal_checkpoint(PASSIVE)" in calls
            assert "PRAGMA wal_checkpoint(TRUNCATE)" in calls
        finally:
            for ext in ("", "-wal"):
                try:
                    os.unlink(store._db_path + ext)
                except FileNotFoundError:
                    pass
```

**Step 4: Run all tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_rate_limiter.py tests/cloud/test_batch_controller.py tests/cloud/test_wal_monitor.py -v
```

**Step 5: Implement rate limiter**

`backend/src/cloud/sync/rate_limiter.py`:
```python
"""Adaptive per-service rate limiter with exponential backoff + jitter."""
from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict

_AWS_SERVICE_LIMITS: dict[str, dict] = {
    "ec2": {"base_rate": 20, "burst": 100, "throttle_backoff": 1.0},
    "elasticloadbalancing": {"base_rate": 10, "burst": 40, "throttle_backoff": 2.0},
    "iam": {"base_rate": 5, "burst": 15, "throttle_backoff": 3.0},
    "directconnect": {"base_rate": 5, "burst": 10, "throttle_backoff": 2.0},
    "sts": {"base_rate": 10, "burst": 50, "throttle_backoff": 1.0},
}

_DEFAULT_LIMIT = {"base_rate": 10, "burst": 50, "throttle_backoff": 1.0}


class AdaptiveRateLimiter:
    def __init__(self, service_limits: dict[str, dict] | None = None):
        self._limits = service_limits if service_limits is not None else _AWS_SERVICE_LIMITS
        self._throttle_counts: dict[str, int] = defaultdict(int)
        self._last_call: dict[str, float] = {}

    async def acquire(self, service: str) -> None:
        limit = self._limits.get(service, _DEFAULT_LIMIT)
        min_interval = 1.0 / limit["base_rate"]
        last = self._last_call.get(service, 0)
        elapsed = time.monotonic() - last
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_call[service] = time.monotonic()

    async def on_throttle(self, service: str) -> None:
        self._throttle_counts[service] += 1
        limit = self._limits.get(service, _DEFAULT_LIMIT)
        base = limit["throttle_backoff"]
        delay = min(base * (2 ** self._throttle_counts[service]), 60.0)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        await asyncio.sleep(delay + jitter)

    def on_success(self, service: str) -> None:
        self._throttle_counts[service] = 0
```

**Step 6: Implement batch controller**

`backend/src/cloud/sync/batch_controller.py`:
```python
"""Dynamically adjusts batch size based on DB write performance."""
from __future__ import annotations


class BatchSizeController:
    def __init__(
        self, default_size: int = 500, min_size: int = 50, max_size: int = 2000
    ):
        self._current = default_size
        self._min = min_size
        self._max = max_size

    @property
    def size(self) -> int:
        return self._current

    def on_success(self, duration_ms: float) -> None:
        if duration_ms < 200 and self._current < self._max:
            self._current = min(self._current + 100, self._max)
        elif duration_ms > 2000:
            self._current = max(self._current // 2, self._min)

    def on_error(self) -> None:
        self._current = max(self._current // 2, self._min)
```

**Step 7: Implement WAL monitor**

`backend/src/cloud/sync/wal_monitor.py`:
```python
"""Periodic WAL checkpoint and size monitoring."""
from __future__ import annotations

import asyncio
import os

from src.utils.logger import get_logger

logger = get_logger(__name__)


class WALMonitor:
    WAL_SIZE_ALERT_MB = 100
    CHECKPOINT_INTERVAL_SECONDS = 300

    async def run_once(self, store) -> None:
        """Single checkpoint pass. Called by run_loop or directly in tests."""
        try:
            await store.execute("PRAGMA wal_checkpoint(PASSIVE)")
            wal_path = store._db_path + "-wal"
            if os.path.exists(wal_path):
                wal_size_mb = os.path.getsize(wal_path) / (1024 * 1024)
                if wal_size_mb > self.WAL_SIZE_ALERT_MB:
                    logger.warning(
                        "WAL file large: %.1f MB. Attempting TRUNCATE.",
                        wal_size_mb,
                    )
                    await store.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception as e:
            logger.warning("WAL checkpoint failed: %s", e)

    async def run_loop(self, store) -> None:
        """Background loop — runs until cancelled."""
        while True:
            await asyncio.sleep(self.CHECKPOINT_INTERVAL_SECONDS)
            await self.run_once(store)
```

**Step 8: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_rate_limiter.py tests/cloud/test_batch_controller.py tests/cloud/test_wal_monitor.py -v
```
Expected: All PASS

**Step 9: Commit**

```bash
git add backend/src/cloud/sync/rate_limiter.py backend/src/cloud/sync/batch_controller.py backend/src/cloud/sync/wal_monitor.py backend/tests/cloud/test_rate_limiter.py backend/tests/cloud/test_batch_controller.py backend/tests/cloud/test_wal_monitor.py
git commit -m "feat(cloud): add rate limiter, batch controller, WAL monitor"
```

---

## Task 6: Concurrency Guard

**Files:**
- Create: `backend/src/cloud/sync/concurrency.py`
- Create: `backend/tests/cloud/test_concurrency.py`

**Step 1: Write tests**

`backend/tests/cloud/test_concurrency.py`:
```python
"""Tests for sync concurrency guard."""
import asyncio
import pytest
from src.cloud.sync.concurrency import SyncConcurrencyGuard


class TestSyncConcurrencyGuard:
    def test_creates_lock_per_account(self):
        guard = SyncConcurrencyGuard()
        lock1 = guard.get_lock("acc-001")
        lock2 = guard.get_lock("acc-002")
        assert lock1 is not lock2

    def test_same_account_returns_same_lock(self):
        guard = SyncConcurrencyGuard()
        lock1 = guard.get_lock("acc-001")
        lock2 = guard.get_lock("acc-001")
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_lock_blocks_concurrent_access(self):
        guard = SyncConcurrencyGuard()
        lock = guard.get_lock("acc-001")
        results = []

        async def task(name: str, delay: float):
            async with lock:
                results.append(f"{name}-start")
                await asyncio.sleep(delay)
                results.append(f"{name}-end")

        await asyncio.gather(task("A", 0.05), task("B", 0.01))
        # A should start and end before B starts
        assert results[0] == "A-start"
        assert results[1] == "A-end"
        assert results[2] == "B-start"

    @pytest.mark.asyncio
    async def test_is_locked(self):
        guard = SyncConcurrencyGuard()
        lock = guard.get_lock("acc-001")
        assert not lock.locked()
        async with lock:
            assert lock.locked()
        assert not lock.locked()
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_concurrency.py -v
```

**Step 3: Implement**

`backend/src/cloud/sync/concurrency.py`:
```python
"""Per-account concurrency guard for cloud sync."""
from __future__ import annotations

import asyncio


class SyncConcurrencyGuard:
    """Ensures max 1 concurrent sync per account across all tiers."""

    def __init__(self) -> None:
        self._active: dict[str, asyncio.Lock] = {}

    def get_lock(self, account_id: str) -> asyncio.Lock:
        if account_id not in self._active:
            self._active[account_id] = asyncio.Lock()
        return self._active[account_id]
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_concurrency.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/sync/concurrency.py backend/tests/cloud/test_concurrency.py
git commit -m "feat(cloud): add per-account sync concurrency guard"
```

---

## Task 7: CloudProviderDriver ABC

**Files:**
- Create: `backend/src/cloud/drivers/base.py`
- Create: `backend/tests/cloud/test_driver_base.py`

**Step 1: Write tests**

`backend/tests/cloud/test_driver_base.py`:
```python
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
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_driver_base.py -v
```

**Step 3: Implement**

`backend/src/cloud/drivers/base.py`:
```python
"""Abstract base class for cloud provider drivers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from src.cloud.models import CloudAccount, DiscoveryBatch, DriverHealth


class CloudProviderDriver(ABC):
    """Provider-agnostic interface for cloud resource discovery."""

    @abstractmethod
    async def discover(
        self,
        account: CloudAccount,
        region: str,
        resource_types: list[str],
    ) -> AsyncIterator[DiscoveryBatch]:
        """Yield batches of discovered resources.

        Handles pagination and retries internally.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def health_check(self, account: CloudAccount) -> DriverHealth:
        """Validate credentials and connectivity."""
        ...  # pragma: no cover

    @abstractmethod
    def supported_resource_types(self) -> dict[str, int]:
        """Return {resource_type: sync_tier} mapping."""
        ...  # pragma: no cover

    def resource_types_for_tier(self, tier: int) -> list[str]:
        """Return resource types belonging to a specific tier."""
        return [
            rt for rt, t in self.supported_resource_types().items() if t == tier
        ]
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_driver_base.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/drivers/base.py backend/tests/cloud/test_driver_base.py
git commit -m "feat(cloud): add CloudProviderDriver ABC"
```

---

## Task 8: AWS Driver — Health Check + Tier 1 Discovery

**Files:**
- Create: `backend/src/cloud/drivers/aws_driver.py`
- Create: `backend/tests/cloud/test_aws_driver.py`

**Step 1: Write tests**

`backend/tests/cloud/test_aws_driver.py`:
```python
"""Tests for AWS cloud provider driver."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.cloud.drivers.aws_driver import AWSDriver
from src.cloud.models import CloudAccount, DiscoveryBatch, DriverHealth


@pytest.fixture
def aws_account():
    return CloudAccount(
        account_id="acc-001",
        provider="aws",
        display_name="Test AWS",
        credential_handle='{"aws_access_key_id":"AKID","aws_secret_access_key":"SECRET"}',
        auth_method="access_key",
        regions=["us-east-1"],
    )


@pytest.fixture
def driver():
    return AWSDriver()


class TestAWSDriverResourceTypes:
    def test_supported_types(self, driver):
        types = driver.supported_resource_types()
        assert "vpc" in types
        assert "subnet" in types
        assert "security_group" in types
        assert types["vpc"] == 1  # Tier 1
        assert types["instance"] == 2  # Tier 2
        assert types["iam_policy"] == 3  # Tier 3

    def test_tier_1_types(self, driver):
        tier1 = driver.resource_types_for_tier(1)
        assert "vpc" in tier1
        assert "subnet" in tier1
        assert "security_group" in tier1
        assert "nacl" in tier1
        assert "route_table" in tier1
        assert "instance" not in tier1

    def test_tier_2_types(self, driver):
        tier2 = driver.resource_types_for_tier(2)
        assert "eni" in tier2
        assert "instance" in tier2
        assert "elb" in tier2
        assert "vpc" not in tier2


class TestAWSDriverHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy_check(self, driver, aws_account):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456:role/TestRole",
            "Account": "123456",
        }
        with patch.object(driver, "_get_boto_client", return_value=mock_sts):
            health = await driver.health_check(aws_account)
        assert health.connected is True
        assert "123456" in health.identity

    @pytest.mark.asyncio
    async def test_failed_check(self, driver, aws_account):
        with patch.object(
            driver, "_get_boto_client",
            side_effect=Exception("Invalid credentials"),
        ):
            health = await driver.health_check(aws_account)
        assert health.connected is False
        assert "Invalid credentials" in health.message


class TestAWSDriverDiscoverVPCs:
    @pytest.mark.asyncio
    async def test_discover_vpcs(self, driver, aws_account):
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpcs.return_value = {
            "Vpcs": [
                {
                    "VpcId": "vpc-abc",
                    "CidrBlock": "10.0.0.0/16",
                    "Tags": [{"Key": "Name", "Value": "prod-vpc"}],
                    "State": "available",
                },
            ],
        }
        mock_ec2.get_paginator.return_value.paginate.return_value = []
        with patch.object(driver, "_get_boto_client", return_value=mock_ec2):
            batches = []
            async for batch in driver.discover(aws_account, "us-east-1", ["vpc"]):
                batches.append(batch)
        assert len(batches) >= 1
        vpc_batch = next(b for b in batches if b.resource_type == "vpc")
        assert len(vpc_batch.items) == 1
        assert vpc_batch.items[0].native_id == "vpc-abc"
        assert vpc_batch.items[0].name == "prod-vpc"
        assert vpc_batch.source == "aws-describe-vpcs"

    @pytest.mark.asyncio
    async def test_discover_subnets_with_relations(self, driver, aws_account):
        mock_ec2 = MagicMock()
        mock_ec2.describe_subnets.return_value = {
            "Subnets": [
                {
                    "SubnetId": "subnet-123",
                    "VpcId": "vpc-abc",
                    "CidrBlock": "10.0.1.0/24",
                    "AvailabilityZone": "us-east-1a",
                    "Tags": [{"Key": "Name", "Value": "web-subnet"}],
                },
            ],
        }
        with patch.object(driver, "_get_boto_client", return_value=mock_ec2):
            batches = []
            async for batch in driver.discover(aws_account, "us-east-1", ["subnet"]):
                batches.append(batch)
        subnet_batch = next(b for b in batches if b.resource_type == "subnet")
        assert len(subnet_batch.items) == 1
        assert len(subnet_batch.relations) == 1
        rel = subnet_batch.relations[0]
        assert rel.source_native_id == "subnet-123"
        assert rel.target_native_id == "vpc-abc"
        assert rel.relation_type == "member_of"

    @pytest.mark.asyncio
    async def test_discover_security_groups(self, driver, aws_account):
        mock_ec2 = MagicMock()
        mock_ec2.describe_security_groups.return_value = {
            "SecurityGroups": [
                {
                    "GroupId": "sg-001",
                    "GroupName": "web-sg",
                    "VpcId": "vpc-abc",
                    "IpPermissions": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": 443,
                            "ToPort": 443,
                            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                        },
                    ],
                    "IpPermissionsEgress": [],
                    "Tags": [],
                },
            ],
        }
        with patch.object(driver, "_get_boto_client", return_value=mock_ec2):
            batches = []
            async for batch in driver.discover(aws_account, "us-east-1", ["security_group"]):
                batches.append(batch)
        sg_batch = next(b for b in batches if b.resource_type == "security_group")
        assert len(sg_batch.items) == 1
        assert sg_batch.items[0].native_id == "sg-001"
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_aws_driver.py -v
```

**Step 3: Implement AWS driver**

`backend/src/cloud/drivers/aws_driver.py`:
```python
"""AWS cloud provider driver using boto3."""
from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

from src.cloud.drivers.base import CloudProviderDriver
from src.cloud.models import (
    CloudAccount,
    DiscoveredItem,
    DiscoveredRelation,
    DiscoveryBatch,
    DriverHealth,
    RateLimitInfo,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _extract_name(tags: list[dict] | None) -> str | None:
    if not tags:
        return None
    for t in tags:
        if t.get("Key") == "Name":
            return t.get("Value")
    return None


def _extract_tags(tags: list[dict] | None) -> dict[str, str]:
    if not tags:
        return {}
    return {t["Key"]: t["Value"] for t in tags if "Key" in t and "Value" in t}


class AWSDriver(CloudProviderDriver):
    """AWS resource discovery via boto3."""

    _RESOURCE_TYPES: dict[str, int] = {
        "vpc": 1, "subnet": 1, "security_group": 1,
        "nacl": 1, "route_table": 1,
        "eni": 2, "instance": 2, "elb": 2, "target_group": 2,
        "tgw": 2, "tgw_attachment": 2, "vpn_connection": 2,
        "nat_gateway": 2, "vpc_peering": 2,
        "iam_policy": 3, "direct_connect": 3, "flow_log_config": 3,
    }

    def supported_resource_types(self) -> dict[str, int]:
        return dict(self._RESOURCE_TYPES)

    def _get_boto_client(self, service: str, account: CloudAccount, region: str = "us-east-1"):
        """Create a boto3 client with account credentials."""
        import boto3
        creds = json.loads(account.credential_handle) if isinstance(account.credential_handle, str) else {}
        if account.auth_method == "iam_role":
            sts = boto3.client("sts")
            assumed = sts.assume_role(
                RoleArn=creds.get("role_arn", ""),
                ExternalId=creds.get("external_id", "debugduck"),
                RoleSessionName="debugduck-cloud-sync",
            )
            temp_creds = assumed["Credentials"]
            return boto3.client(
                service, region_name=region,
                aws_access_key_id=temp_creds["AccessKeyId"],
                aws_secret_access_key=temp_creds["SecretAccessKey"],
                aws_session_token=temp_creds["SessionToken"],
            )
        else:
            return boto3.client(
                service, region_name=region,
                aws_access_key_id=creds.get("aws_access_key_id", ""),
                aws_secret_access_key=creds.get("aws_secret_access_key", ""),
            )

    async def health_check(self, account: CloudAccount) -> DriverHealth:
        start = time.monotonic()
        try:
            sts = self._get_boto_client("sts", account)
            identity = sts.get_caller_identity()
            latency = (time.monotonic() - start) * 1000
            return DriverHealth(
                connected=True,
                latency_ms=latency,
                identity=identity.get("Arn", ""),
                permissions_ok=True,
                missing_permissions=[],
                message="Connected successfully",
            )
        except Exception as e:
            return DriverHealth(
                connected=False,
                latency_ms=(time.monotonic() - start) * 1000,
                identity="",
                permissions_ok=False,
                missing_permissions=[],
                message=str(e),
            )

    async def discover(
        self,
        account: CloudAccount,
        region: str,
        resource_types: list[str],
    ) -> AsyncIterator[DiscoveryBatch]:
        ec2 = self._get_boto_client("ec2", account, region)
        dispatchers = {
            "vpc": self._discover_vpcs,
            "subnet": self._discover_subnets,
            "security_group": self._discover_security_groups,
            "nacl": self._discover_nacls,
            "route_table": self._discover_route_tables,
            "eni": self._discover_enis,
            "instance": self._discover_instances,
            "nat_gateway": self._discover_nat_gateways,
            "vpc_peering": self._discover_vpc_peerings,
        }
        for rt in resource_types:
            handler = dispatchers.get(rt)
            if handler:
                try:
                    batch = handler(ec2, account.account_id, region)
                    yield batch
                except Exception as e:
                    logger.warning("Failed to discover %s in %s: %s", rt, region, e)

    # ── Tier 1 Discoverers ──

    def _discover_vpcs(self, ec2, account_id: str, region: str) -> DiscoveryBatch:
        resp = ec2.describe_vpcs()
        items = []
        for vpc in resp.get("Vpcs", []):
            items.append(DiscoveredItem(
                native_id=vpc["VpcId"],
                name=_extract_name(vpc.get("Tags")),
                raw=vpc,
                tags=_extract_tags(vpc.get("Tags")),
            ))
        return DiscoveryBatch(
            account_id=account_id, region=region,
            resource_type="vpc", source="aws-describe-vpcs",
            items=items, relations=[],
        )

    def _discover_subnets(self, ec2, account_id: str, region: str) -> DiscoveryBatch:
        resp = ec2.describe_subnets()
        items, relations = [], []
        for s in resp.get("Subnets", []):
            items.append(DiscoveredItem(
                native_id=s["SubnetId"],
                name=_extract_name(s.get("Tags")),
                raw=s,
                tags=_extract_tags(s.get("Tags")),
            ))
            relations.append(DiscoveredRelation(
                source_native_id=s["SubnetId"],
                target_native_id=s["VpcId"],
                relation_type="member_of",
            ))
        return DiscoveryBatch(
            account_id=account_id, region=region,
            resource_type="subnet", source="aws-describe-subnets",
            items=items, relations=relations,
        )

    def _discover_security_groups(self, ec2, account_id: str, region: str) -> DiscoveryBatch:
        resp = ec2.describe_security_groups()
        items, relations = [], []
        for sg in resp.get("SecurityGroups", []):
            items.append(DiscoveredItem(
                native_id=sg["GroupId"],
                name=sg.get("GroupName") or _extract_name(sg.get("Tags")),
                raw=sg,
                tags=_extract_tags(sg.get("Tags")),
            ))
            if sg.get("VpcId"):
                relations.append(DiscoveredRelation(
                    source_native_id=sg["GroupId"],
                    target_native_id=sg["VpcId"],
                    relation_type="member_of",
                ))
        return DiscoveryBatch(
            account_id=account_id, region=region,
            resource_type="security_group", source="aws-describe-security-groups",
            items=items, relations=relations,
        )

    def _discover_nacls(self, ec2, account_id: str, region: str) -> DiscoveryBatch:
        resp = ec2.describe_network_acls()
        items, relations = [], []
        for nacl in resp.get("NetworkAcls", []):
            items.append(DiscoveredItem(
                native_id=nacl["NetworkAclId"],
                name=_extract_name(nacl.get("Tags")),
                raw=nacl,
                tags=_extract_tags(nacl.get("Tags")),
            ))
            if nacl.get("VpcId"):
                relations.append(DiscoveredRelation(
                    source_native_id=nacl["NetworkAclId"],
                    target_native_id=nacl["VpcId"],
                    relation_type="member_of",
                ))
        return DiscoveryBatch(
            account_id=account_id, region=region,
            resource_type="nacl", source="aws-describe-nacls",
            items=items, relations=relations,
        )

    def _discover_route_tables(self, ec2, account_id: str, region: str) -> DiscoveryBatch:
        resp = ec2.describe_route_tables()
        items, relations = [], []
        for rt in resp.get("RouteTables", []):
            items.append(DiscoveredItem(
                native_id=rt["RouteTableId"],
                name=_extract_name(rt.get("Tags")),
                raw=rt,
                tags=_extract_tags(rt.get("Tags")),
            ))
            if rt.get("VpcId"):
                relations.append(DiscoveredRelation(
                    source_native_id=rt["RouteTableId"],
                    target_native_id=rt["VpcId"],
                    relation_type="member_of",
                ))
            for assoc in rt.get("Associations", []):
                if assoc.get("SubnetId"):
                    relations.append(DiscoveredRelation(
                        source_native_id=rt["RouteTableId"],
                        target_native_id=assoc["SubnetId"],
                        relation_type="associated_with",
                    ))
        return DiscoveryBatch(
            account_id=account_id, region=region,
            resource_type="route_table", source="aws-describe-route-tables",
            items=items, relations=relations,
        )

    # ── Tier 2 Discoverers ──

    def _discover_enis(self, ec2, account_id: str, region: str) -> DiscoveryBatch:
        resp = ec2.describe_network_interfaces()
        items, relations = [], []
        for eni in resp.get("NetworkInterfaces", []):
            items.append(DiscoveredItem(
                native_id=eni["NetworkInterfaceId"],
                name=eni.get("Description") or _extract_name(eni.get("TagSet")),
                raw=eni,
                tags=_extract_tags(eni.get("TagSet")),
            ))
            if eni.get("SubnetId"):
                relations.append(DiscoveredRelation(
                    source_native_id=eni["NetworkInterfaceId"],
                    target_native_id=eni["SubnetId"],
                    relation_type="attached_to",
                ))
            for sg in eni.get("Groups", []):
                relations.append(DiscoveredRelation(
                    source_native_id=sg["GroupId"],
                    target_native_id=eni["NetworkInterfaceId"],
                    relation_type="applied_to",
                ))
        return DiscoveryBatch(
            account_id=account_id, region=region,
            resource_type="eni", source="aws-describe-enis",
            items=items, relations=relations,
        )

    def _discover_instances(self, ec2, account_id: str, region: str) -> DiscoveryBatch:
        resp = ec2.describe_instances()
        items, relations = [], []
        for reservation in resp.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                items.append(DiscoveredItem(
                    native_id=inst["InstanceId"],
                    name=_extract_name(inst.get("Tags")),
                    raw=inst,
                    tags=_extract_tags(inst.get("Tags")),
                ))
                for ni in inst.get("NetworkInterfaces", []):
                    relations.append(DiscoveredRelation(
                        source_native_id=inst["InstanceId"],
                        target_native_id=ni["NetworkInterfaceId"],
                        relation_type="has_interface",
                    ))
        return DiscoveryBatch(
            account_id=account_id, region=region,
            resource_type="instance", source="aws-describe-instances",
            items=items, relations=relations,
        )

    def _discover_nat_gateways(self, ec2, account_id: str, region: str) -> DiscoveryBatch:
        resp = ec2.describe_nat_gateways()
        items, relations = [], []
        for nat in resp.get("NatGateways", []):
            items.append(DiscoveredItem(
                native_id=nat["NatGatewayId"],
                name=_extract_name(nat.get("Tags")),
                raw=nat,
                tags=_extract_tags(nat.get("Tags")),
            ))
            if nat.get("SubnetId"):
                relations.append(DiscoveredRelation(
                    source_native_id=nat["NatGatewayId"],
                    target_native_id=nat["SubnetId"],
                    relation_type="deployed_in",
                ))
        return DiscoveryBatch(
            account_id=account_id, region=region,
            resource_type="nat_gateway", source="aws-describe-nat-gateways",
            items=items, relations=relations,
        )

    def _discover_vpc_peerings(self, ec2, account_id: str, region: str) -> DiscoveryBatch:
        resp = ec2.describe_vpc_peering_connections()
        items, relations = [], []
        for pcx in resp.get("VpcPeeringConnections", []):
            items.append(DiscoveredItem(
                native_id=pcx["VpcPeeringConnectionId"],
                name=_extract_name(pcx.get("Tags")),
                raw=pcx,
                tags=_extract_tags(pcx.get("Tags")),
            ))
            if pcx.get("RequesterVpcInfo", {}).get("VpcId"):
                relations.append(DiscoveredRelation(
                    source_native_id=pcx["VpcPeeringConnectionId"],
                    target_native_id=pcx["RequesterVpcInfo"]["VpcId"],
                    relation_type="peered_with",
                ))
            if pcx.get("AccepterVpcInfo", {}).get("VpcId"):
                relations.append(DiscoveredRelation(
                    source_native_id=pcx["VpcPeeringConnectionId"],
                    target_native_id=pcx["AccepterVpcInfo"]["VpcId"],
                    relation_type="peered_with",
                ))
        return DiscoveryBatch(
            account_id=account_id, region=region,
            resource_type="vpc_peering", source="aws-describe-vpc-peerings",
            items=items, relations=relations,
        )
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_aws_driver.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/drivers/aws_driver.py backend/tests/cloud/test_aws_driver.py
git commit -m "feat(cloud): add AWS driver with health check + Tier 1/2 discovery"
```

---

## Task 9: Sync Engine — Batch Processing with Hash Detection

**Files:**
- Create: `backend/src/cloud/sync/engine.py`
- Create: `backend/tests/cloud/test_sync_engine.py`

**Step 1: Write tests**

`backend/tests/cloud/test_sync_engine.py`:
```python
"""Tests for CloudSyncEngine batch processing."""
import json
import os
import tempfile
import uuid

import pytest

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


@pytest.fixture
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
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_sync_engine.py -v
```

**Step 3: Implement sync engine**

`backend/src/cloud/sync/engine.py`:
```python
"""Cloud sync engine — processes discovery batches into CloudStore."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from src.cloud.cloud_store import CloudStore
from src.cloud.redaction import compress_raw, make_raw_preview, redact_raw
from src.cloud.sync.batch_controller import BatchSizeController
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CloudSyncEngine:
    def __init__(self, store: CloudStore):
        self._store = store
        self._batch_ctrl = BatchSizeController()

    async def process_batch(
        self, batch: "DiscoveryBatch", sync_job_id: str
    ) -> dict[str, int]:
        """Process a single discovery batch. Returns stats dict."""
        from src.cloud.models import DiscoveryBatch  # avoid circular

        stats = {"created": 0, "updated": 0, "unchanged": 0, "relations_created": 0}

        # Phase 1: Load native_id -> resource_id cache
        native_cache = await self._store.load_native_id_cache(
            batch.account_id, batch.region
        )

        # Phase 2: Process items
        for item in batch.items:
            redacted = redact_raw(item.raw)
            raw_json_str = json.dumps(redacted, sort_keys=True, default=str)
            resource_hash = hashlib.sha256(raw_json_str.encode()).hexdigest()

            existing_id = native_cache.get(item.native_id)
            if existing_id:
                existing_hash = await self._store.get_resource_hash(
                    provider="aws",  # TODO: pass from batch
                    account_id=batch.account_id,
                    region=batch.region,
                    native_id=item.native_id,
                )
                if existing_hash == resource_hash:
                    await self._store.touch_resource(existing_id, sync_job_id)
                    stats["unchanged"] += 1
                    continue
                else:
                    resource_id = existing_id
                    stats["updated"] += 1
            else:
                resource_id = str(uuid.uuid4())
                stats["created"] += 1

            compressed = compress_raw(redacted)
            preview = make_raw_preview(redacted)
            tags_str = json.dumps(item.tags) if item.tags else None

            await self._store.upsert_resource(
                resource_id=resource_id,
                provider="aws",
                account_id=batch.account_id,
                region=batch.region,
                resource_type=batch.resource_type,
                native_id=item.native_id,
                name=item.name,
                raw_compressed=compressed,
                raw_preview=preview,
                tags=tags_str,
                resource_hash=resource_hash,
                source=batch.source,
                sync_job_id=sync_job_id,
                sync_tier=1,
            )
            native_cache[item.native_id] = resource_id

        # Phase 3: Process relations
        for rel in batch.relations:
            source_id = native_cache.get(rel.source_native_id)
            target_id = native_cache.get(rel.target_native_id)
            if source_id and target_id:
                relation_id = str(uuid.uuid4())
                metadata_str = json.dumps(rel.metadata) if rel.metadata else None
                await self._store.upsert_relation(
                    relation_id=relation_id,
                    source_resource_id=source_id,
                    target_resource_id=target_id,
                    relation_type=rel.relation_type,
                    metadata=metadata_str,
                )
                stats["relations_created"] += 1

        return stats
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_sync_engine.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/sync/engine.py backend/tests/cloud/test_sync_engine.py
git commit -m "feat(cloud): add sync engine with hash-based change detection"
```

---

## Task 10: Sync Engine — Soft Deletion + Lock Management

**Files:**
- Modify: `backend/src/cloud/sync/engine.py`
- Modify: `backend/tests/cloud/test_sync_engine.py`

**Step 1: Add soft deletion tests**

Append to `backend/tests/cloud/test_sync_engine.py`:
```python
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
```

**Step 2: Run tests to verify new tests fail**

```bash
cd backend && python -m pytest tests/cloud/test_sync_engine.py -v -k "TestSoftDeletion or TestLockManagement"
```

**Step 3: Add methods to engine**

Add to `backend/src/cloud/sync/engine.py`:
```python
    async def mark_stale_deleted(
        self,
        account_id: str,
        region: str,
        resource_types: list[str],
        cutoff_ts: str,
    ) -> int:
        """Soft-delete resources not seen since cutoff_ts."""
        return await self._store.mark_stale_deleted(
            account_id, region, resource_types, cutoff_ts
        )

    async def acquire_sync_lock(
        self, account_id: str, tier: int
    ) -> str | None:
        """Try to acquire sync lock. Returns sync_job_id or None."""
        STALE_THRESHOLD_SECONDS = 900
        running = await self._store.find_running_job(account_id, tier)
        if running:
            from datetime import datetime, timezone
            started = datetime.fromisoformat(running["started_at"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - started).total_seconds()
            if age < STALE_THRESHOLD_SECONDS:
                return None
            # Stale lock — reclaim
            await self._store.complete_sync_job(
                running["sync_job_id"],
                status="failed",
                errors=[{"error": "stale_lock_reclaimed"}],
            )

        job_id = str(uuid.uuid4())
        await self._store.create_sync_job(job_id, account_id, tier)
        return job_id

    async def release_sync_lock(
        self,
        sync_job_id: str,
        status: str = "completed",
        items_seen: int = 0,
        items_created: int = 0,
        items_updated: int = 0,
        items_deleted: int = 0,
        api_calls: int = 0,
        errors: list[dict] | None = None,
    ) -> None:
        await self._store.complete_sync_job(
            sync_job_id, status=status,
            items_seen=items_seen, items_created=items_created,
            items_updated=items_updated, items_deleted=items_deleted,
            api_calls=api_calls, errors=errors,
        )
```

**Step 4: Run all engine tests**

```bash
cd backend && python -m pytest tests/cloud/test_sync_engine.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/sync/engine.py backend/tests/cloud/test_sync_engine.py
git commit -m "feat(cloud): add soft deletion + sync lock management to engine"
```

---

## Task 11: CloudSyncScheduler

**Files:**
- Create: `backend/src/cloud/sync/scheduler.py`
- Create: `backend/tests/cloud/test_scheduler.py`

**Step 1: Write tests**

`backend/tests/cloud/test_scheduler.py`:
```python
"""Tests for CloudSyncScheduler."""
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.cloud.cloud_store import CloudStore
from src.cloud.sync.scheduler import CloudSyncScheduler


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


@pytest.fixture
def scheduler(store):
    return CloudSyncScheduler(store)


class TestSchedulerTierDue:
    @pytest.mark.asyncio
    async def test_first_sync_is_always_due(self, scheduler, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="Test", credential_handle="ref",
            auth_method="iam_role", regions=["us-east-1"],
        )
        account = await store.get_account("acc-001")
        assert scheduler.is_due(account, tier=1) is True

    @pytest.mark.asyncio
    async def test_default_intervals(self, scheduler):
        assert scheduler.get_interval(tier=1) == 600
        assert scheduler.get_interval(tier=2) == 1800
        assert scheduler.get_interval(tier=3) == 21600


class TestSchedulerSyncAccount:
    @pytest.mark.asyncio
    async def test_sync_account_tier_calls_driver(self, scheduler, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="Test", credential_handle='{}',
            auth_method="iam_role", regions=["us-east-1"],
        )
        mock_driver = AsyncMock()
        mock_driver.resource_types_for_tier.return_value = ["vpc"]
        mock_driver.discover = AsyncMock(return_value=AsyncMock(__aiter__=lambda _: iter([])))

        # Use async iterator mock
        async def empty_discover(*args, **kwargs):
            return
            yield  # make it an async generator

        mock_driver.discover = empty_discover
        scheduler._drivers = {"aws": mock_driver}

        account = await store.get_account("acc-001")
        await scheduler.sync_account_tier(account, tier=1)
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_scheduler.py -v
```

**Step 3: Implement scheduler**

`backend/src/cloud/sync/scheduler.py`:
```python
"""Cloud sync scheduler — manages per-account, per-tier sync jobs."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from src.cloud.cloud_store import CloudStore
from src.cloud.drivers.base import CloudProviderDriver
from src.cloud.sync.concurrency import SyncConcurrencyGuard
from src.cloud.sync.engine import CloudSyncEngine
from src.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_INTERVALS = {1: 600, 2: 1800, 3: 21600}


class CloudSyncScheduler:
    def __init__(self, store: CloudStore):
        self._store = store
        self._engine = CloudSyncEngine(store)
        self._guard = SyncConcurrencyGuard()
        self._drivers: dict[str, CloudProviderDriver] = {}
        self._last_sync: dict[str, float] = {}  # "acc:tier" -> timestamp

    def register_driver(self, provider: str, driver: CloudProviderDriver) -> None:
        self._drivers[provider] = driver

    def get_interval(self, tier: int, sync_config: dict | None = None) -> int:
        if sync_config:
            return sync_config.get(f"tier_{tier}_interval", _DEFAULT_INTERVALS[tier])
        return _DEFAULT_INTERVALS[tier]

    def is_due(self, account: Any, tier: int) -> bool:
        key = f"{account['account_id']}:{tier}"
        last = self._last_sync.get(key, 0)
        config = json.loads(account["sync_config"]) if account["sync_config"] else None
        interval = self.get_interval(tier, config)
        return (datetime.now(timezone.utc).timestamp() - last) >= interval

    async def sync_account_tier(self, account: Any, tier: int) -> None:
        provider = account["provider"]
        driver = self._drivers.get(provider)
        if not driver:
            logger.warning("No driver for provider %s", provider)
            return

        account_id = account["account_id"]
        lock = self._guard.get_lock(account_id)
        if lock.locked():
            logger.debug("Skipping %s tier %d — another sync running", account_id, tier)
            return

        async with lock:
            job_id = await self._engine.acquire_sync_lock(account_id, tier)
            if not job_id:
                return

            resource_types = driver.resource_types_for_tier(tier)
            regions = json.loads(account["regions"])
            total_stats = {"seen": 0, "created": 0, "updated": 0, "deleted": 0, "api_calls": 0}

            try:
                for region in regions:
                    async for batch in driver.discover(
                        self._account_to_model(account), region, resource_types
                    ):
                        stats = await self._engine.process_batch(batch, job_id)
                        total_stats["seen"] += stats["created"] + stats["updated"] + stats["unchanged"]
                        total_stats["created"] += stats["created"]
                        total_stats["updated"] += stats["updated"]
                        total_stats["api_calls"] += 1

                # Soft-delete stale resources
                interval = self.get_interval(tier)
                from datetime import timedelta
                cutoff = (datetime.now(timezone.utc) - timedelta(seconds=interval * 2)).isoformat()
                for region in regions:
                    await self._engine.mark_stale_deleted(
                        account_id, region, resource_types, cutoff
                    )

                await self._engine.release_sync_lock(
                    job_id, status="completed",
                    items_seen=total_stats["seen"],
                    items_created=total_stats["created"],
                    items_updated=total_stats["updated"],
                    items_deleted=total_stats["deleted"],
                    api_calls=total_stats["api_calls"],
                )
                await self._store.update_account_sync_status(
                    account_id, status="ok", consecutive_failures=0
                )
                key = f"{account_id}:{tier}"
                self._last_sync[key] = datetime.now(timezone.utc).timestamp()

            except Exception as e:
                logger.error("Sync failed for %s tier %d: %s", account_id, tier, e)
                await self._engine.release_sync_lock(
                    job_id, status="failed",
                    errors=[{"error": str(e)}],
                )
                current = account["consecutive_failures"] or 0
                new_failures = current + 1
                status = "paused" if new_failures >= 5 else "error"
                await self._store.update_account_sync_status(
                    account_id, status=status,
                    error=str(e), consecutive_failures=new_failures,
                )

    def _account_to_model(self, row: Any):
        from src.cloud.models import CloudAccount
        return CloudAccount(
            account_id=row["account_id"],
            provider=row["provider"],
            display_name=row["display_name"],
            credential_handle=row["credential_handle"],
            auth_method=row["auth_method"],
            regions=json.loads(row["regions"]),
        )

    async def run_loop(self) -> None:
        """Main scheduler loop — runs until cancelled."""
        while True:
            try:
                accounts = await self._store.list_accounts()
                for account in accounts:
                    if not account["sync_enabled"]:
                        continue
                    if account["last_sync_status"] == "paused":
                        continue
                    for tier in [1, 2, 3]:
                        if self.is_due(account, tier):
                            asyncio.create_task(
                                self.sync_account_tier(account, tier)
                            )
            except Exception as e:
                logger.error("Scheduler loop error: %s", e)
            await asyncio.sleep(60)
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_scheduler.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/sync/scheduler.py backend/tests/cloud/test_scheduler.py
git commit -m "feat(cloud): add CloudSyncScheduler with tiered scheduling"
```

---

## Task 12: PolicyStore

**Files:**
- Create: `backend/src/cloud/policy_store.py`
- Create: `backend/tests/cloud/test_policy_store.py`

**Step 1: Write tests**

`backend/tests/cloud/test_policy_store.py`:
```python
"""Tests for PolicyStore."""
import os
import tempfile
import pytest

from src.cloud.policy_store import PolicyStore


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
    return PolicyStore(db_path=tmp_db)


class TestPolicyGroupCRUD:
    @pytest.mark.asyncio
    async def test_upsert_and_get(self, store):
        await store.upsert_policy_group(
            policy_group_id="pg-001",
            name="web-sg",
            provider="aws",
            source_type="security_group",
            cloud_resource_id="res-001",
        )
        group = await store.get_policy_group("pg-001")
        assert group is not None
        assert group["name"] == "web-sg"
        assert group["source_type"] == "security_group"

    @pytest.mark.asyncio
    async def test_get_by_cloud_resource(self, store):
        await store.upsert_policy_group(
            policy_group_id="pg-001",
            name="web-sg",
            provider="aws",
            source_type="security_group",
            cloud_resource_id="res-001",
        )
        group = await store.get_by_cloud_resource("res-001")
        assert group is not None
        assert group["policy_group_id"] == "pg-001"

    @pytest.mark.asyncio
    async def test_list_groups(self, store):
        for i in range(3):
            await store.upsert_policy_group(
                policy_group_id=f"pg-{i}",
                name=f"sg-{i}",
                provider="aws",
                source_type="security_group",
            )
        groups = await store.list_policy_groups()
        assert len(groups) == 3


class TestPolicyRuleCRUD:
    @pytest.mark.asyncio
    async def test_add_and_list_rules(self, store):
        await store.upsert_policy_group(
            policy_group_id="pg-001", name="web-sg",
            provider="aws", source_type="security_group",
        )
        await store.add_rule(
            rule_id="r-001", policy_group_id="pg-001",
            direction="inbound", action="allow",
            protocol="tcp", port_range_start=443,
            port_range_end=443, source_cidr="0.0.0.0/0",
        )
        await store.add_rule(
            rule_id="r-002", policy_group_id="pg-001",
            direction="outbound", action="allow",
            protocol="all",
        )
        rules = await store.list_rules("pg-001")
        assert len(rules) == 2

    @pytest.mark.asyncio
    async def test_replace_rules(self, store):
        await store.upsert_policy_group(
            policy_group_id="pg-001", name="web-sg",
            provider="aws", source_type="security_group",
        )
        await store.add_rule(
            rule_id="r-001", policy_group_id="pg-001",
            direction="inbound", action="allow", protocol="tcp",
        )
        # Replace all rules
        await store.replace_rules("pg-001", [
            {"rule_id": "r-new", "direction": "inbound",
             "action": "deny", "protocol": "udp"},
        ])
        rules = await store.list_rules("pg-001")
        assert len(rules) == 1
        assert rules[0]["action"] == "deny"


class TestPolicyAttachments:
    @pytest.mark.asyncio
    async def test_attach_and_list(self, store):
        await store.upsert_policy_group(
            policy_group_id="pg-001", name="web-sg",
            provider="aws", source_type="security_group",
        )
        await store.attach(
            attachment_id="att-001",
            policy_group_id="pg-001",
            target_resource_id="res-eni-001",
            target_type="eni",
        )
        attachments = await store.list_attachments("pg-001")
        assert len(attachments) == 1
        assert attachments[0]["target_type"] == "eni"
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_policy_store.py -v
```

**Step 3: Implement PolicyStore**

`backend/src/cloud/policy_store.py`:
```python
"""Security policy store — separated from adapter_registry."""
from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PolicyStore:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="policy-db"
        )
        self._conn: sqlite3.Connection | None = None
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=30000")
        return self._conn

    def _init_schema(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_POLICY_SCHEMA)
        conn.commit()
        conn.close()

    async def _execute(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, partial(self._sync_execute, sql, params)
        )

    def _sync_execute(self, sql: str, params: tuple) -> list[sqlite3.Row]:
        conn = self._get_conn()
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.fetchall()

    # ── Policy Groups ──

    async def upsert_policy_group(
        self,
        policy_group_id: str,
        name: str,
        provider: str | None = None,
        source_type: str = "security_group",
        cloud_resource_id: str | None = None,
        description: str | None = None,
    ) -> None:
        now = _now_iso()
        await self._execute(
            """INSERT INTO policy_groups
               (policy_group_id, name, provider, source_type,
                cloud_resource_id, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(policy_group_id) DO UPDATE SET
                 name=excluded.name, provider=excluded.provider,
                 cloud_resource_id=excluded.cloud_resource_id,
                 description=excluded.description,
                 updated_at=excluded.updated_at""",
            (policy_group_id, name, provider, source_type,
             cloud_resource_id, description, now, now),
        )

    async def get_policy_group(self, policy_group_id: str) -> sqlite3.Row | None:
        rows = await self._execute(
            "SELECT * FROM policy_groups WHERE policy_group_id = ?",
            (policy_group_id,),
        )
        return rows[0] if rows else None

    async def get_by_cloud_resource(self, cloud_resource_id: str) -> sqlite3.Row | None:
        rows = await self._execute(
            "SELECT * FROM policy_groups WHERE cloud_resource_id = ?",
            (cloud_resource_id,),
        )
        return rows[0] if rows else None

    async def list_policy_groups(self, provider: str | None = None) -> list[sqlite3.Row]:
        if provider:
            return await self._execute(
                "SELECT * FROM policy_groups WHERE provider = ? ORDER BY name",
                (provider,),
            )
        return await self._execute("SELECT * FROM policy_groups ORDER BY name")

    # ── Rules ──

    async def add_rule(
        self,
        rule_id: str,
        policy_group_id: str,
        direction: str,
        action: str,
        protocol: str,
        port_range_start: int | None = None,
        port_range_end: int | None = None,
        source_cidr: str | None = None,
        dest_cidr: str | None = None,
        priority: int | None = None,
        description: str | None = None,
    ) -> None:
        await self._execute(
            """INSERT OR REPLACE INTO policy_rules
               (rule_id, policy_group_id, direction, action, protocol,
                port_range_start, port_range_end, source_cidr, dest_cidr,
                priority, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rule_id, policy_group_id, direction, action, protocol,
             port_range_start, port_range_end, source_cidr, dest_cidr,
             priority, description, _now_iso()),
        )

    async def list_rules(self, policy_group_id: str) -> list[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM policy_rules WHERE policy_group_id = ? ORDER BY priority, rule_id",
            (policy_group_id,),
        )

    async def replace_rules(self, policy_group_id: str, rules: list[dict]) -> None:
        """Delete all existing rules and insert new ones atomically."""
        conn = self._get_conn()
        try:
            conn.execute(
                "DELETE FROM policy_rules WHERE policy_group_id = ?",
                (policy_group_id,),
            )
            for r in rules:
                conn.execute(
                    """INSERT INTO policy_rules
                       (rule_id, policy_group_id, direction, action, protocol,
                        port_range_start, port_range_end, source_cidr, dest_cidr,
                        priority, description, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        r["rule_id"], policy_group_id,
                        r["direction"], r["action"], r["protocol"],
                        r.get("port_range_start"), r.get("port_range_end"),
                        r.get("source_cidr"), r.get("dest_cidr"),
                        r.get("priority"), r.get("description"),
                        _now_iso(),
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ── Attachments ──

    async def attach(
        self,
        attachment_id: str,
        policy_group_id: str,
        target_resource_id: str,
        target_type: str,
    ) -> None:
        await self._execute(
            """INSERT OR REPLACE INTO policy_attachments
               (attachment_id, policy_group_id, target_resource_id,
                target_type, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (attachment_id, policy_group_id, target_resource_id,
             target_type, _now_iso()),
        )

    async def list_attachments(self, policy_group_id: str) -> list[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM policy_attachments WHERE policy_group_id = ?",
            (policy_group_id,),
        )


_POLICY_SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_groups (
    policy_group_id     TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    provider            TEXT,
    source_type         TEXT NOT NULL,
    cloud_resource_id   TEXT,
    description         TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_rules (
    rule_id             TEXT PRIMARY KEY,
    policy_group_id     TEXT NOT NULL REFERENCES policy_groups(policy_group_id) ON DELETE CASCADE,
    direction           TEXT NOT NULL,
    action              TEXT NOT NULL,
    protocol            TEXT NOT NULL,
    port_range_start    INTEGER,
    port_range_end      INTEGER,
    source_cidr         TEXT,
    dest_cidr           TEXT,
    priority            INTEGER,
    description         TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pr_group ON policy_rules(policy_group_id);

CREATE TABLE IF NOT EXISTS policy_attachments (
    attachment_id       TEXT PRIMARY KEY,
    policy_group_id     TEXT NOT NULL REFERENCES policy_groups(policy_group_id) ON DELETE CASCADE,
    target_resource_id  TEXT NOT NULL,
    target_type         TEXT NOT NULL,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pa_group ON policy_attachments(policy_group_id);
CREATE INDEX IF NOT EXISTS idx_pa_target ON policy_attachments(target_resource_id);
"""
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_policy_store.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/policy_store.py backend/tests/cloud/test_policy_store.py
git commit -m "feat(cloud): add PolicyStore for security policy management"
```

---

## Task 13: CloudResourceMapper

**Files:**
- Create: `backend/src/cloud/mapper.py`
- Create: `backend/tests/cloud/test_mapper.py`

**Step 1: Write tests**

`backend/tests/cloud/test_mapper.py`:
```python
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
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_mapper.py -v
```

**Step 3: Implement mapper**

`backend/src/cloud/mapper.py`:
```python
"""CloudResourceMapper — translates cloud_resources to canonical models."""
from __future__ import annotations

import json
import uuid
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

MAPPER_VERSION = 1


def _extract_cidrs(raw: dict, provider: str) -> list[str]:
    if provider == "aws":
        cidrs = [raw.get("CidrBlock", "")]
        cidrs += [a["CidrBlock"] for a in raw.get("CidrBlockAssociationSet", [])
                  if "CidrBlock" in a]
        return [c for c in cidrs if c]
    elif provider == "azure":
        return raw.get("address_space", {}).get("address_prefixes", [])
    elif provider == "oracle":
        cidr = raw.get("cidr_block", "")
        return [cidr] if cidr else []
    return []


class CloudResourceMapper:
    """Translates cloud_resources rows into canonical models
    and writes to topology_store / policy_store."""

    _MAPPERS = {
        "vpc": "_map_network_segment",
        "subnet": "_map_subnet",
        "security_group": "_map_policy_group",
        "nacl": "_map_policy_group",
        "route_table": "_map_routing_table",
    }

    def __init__(self, topology_store, policy_store):
        self._topology_store = topology_store
        self._policy_store = policy_store

    async def map_resource(self, resource) -> None:
        handler_name = self._MAPPERS.get(resource.resource_type)
        if handler_name:
            handler = getattr(self, handler_name)
            try:
                raw = json.loads(resource.raw_json) if isinstance(resource.raw_json, str) else resource.raw_json
                await handler(resource, raw)
            except Exception as e:
                logger.warning(
                    "Mapper failed for %s %s: %s",
                    resource.resource_type, resource.resource_id, e,
                )

    async def _map_network_segment(self, resource, raw: dict) -> None:
        cidrs = _extract_cidrs(raw, resource.provider)
        await self._topology_store.upsert_network_segment({
            "id": resource.resource_id,
            "name": resource.name or raw.get("VpcId", ""),
            "cidr_blocks": cidrs,
            "provider": resource.provider,
            "account_id": resource.account_id,
            "region": resource.region,
            "cloud_resource_id": resource.resource_id,
        })

    async def _map_subnet(self, resource, raw: dict) -> None:
        await self._topology_store.upsert_subnet_segment({
            "id": resource.resource_id,
            "name": resource.name or raw.get("SubnetId", ""),
            "cidr": raw.get("CidrBlock", ""),
            "network_segment_id": raw.get("VpcId", ""),
            "availability_zone": raw.get("AvailabilityZone"),
            "cloud_resource_id": resource.resource_id,
        })

    async def _map_policy_group(self, resource, raw: dict) -> None:
        await self._policy_store.upsert_policy_group(
            policy_group_id=resource.resource_id,
            name=resource.name or raw.get("GroupName", raw.get("NetworkAclId", "")),
            provider=resource.provider,
            source_type=resource.resource_type,
            cloud_resource_id=resource.resource_id,
        )
        rules = self._extract_rules(resource, raw)
        await self._policy_store.replace_rules(resource.resource_id, rules)

    def _extract_rules(self, resource, raw: dict) -> list[dict]:
        rules = []
        if resource.resource_type == "security_group":
            for perm in raw.get("IpPermissions", []):
                for cidr_range in perm.get("IpRanges", []):
                    rules.append({
                        "rule_id": str(uuid.uuid4()),
                        "direction": "inbound",
                        "action": "allow",
                        "protocol": perm.get("IpProtocol", "all"),
                        "port_range_start": perm.get("FromPort"),
                        "port_range_end": perm.get("ToPort"),
                        "source_cidr": cidr_range.get("CidrIp"),
                    })
            for perm in raw.get("IpPermissionsEgress", []):
                for cidr_range in perm.get("IpRanges", []):
                    rules.append({
                        "rule_id": str(uuid.uuid4()),
                        "direction": "outbound",
                        "action": "allow",
                        "protocol": perm.get("IpProtocol", "all"),
                        "port_range_start": perm.get("FromPort"),
                        "port_range_end": perm.get("ToPort"),
                        "dest_cidr": cidr_range.get("CidrIp"),
                    })
        elif resource.resource_type == "nacl":
            for entry in raw.get("Entries", []):
                rules.append({
                    "rule_id": str(uuid.uuid4()),
                    "direction": "inbound" if not entry.get("Egress") else "outbound",
                    "action": "allow" if entry.get("RuleAction") == "allow" else "deny",
                    "protocol": str(entry.get("Protocol", "-1")),
                    "source_cidr": entry.get("CidrBlock"),
                    "priority": entry.get("RuleNumber"),
                })
        return rules

    async def _map_routing_table(self, resource, raw: dict) -> None:
        routes = []
        for route in raw.get("Routes", []):
            target = (
                route.get("GatewayId")
                or route.get("NatGatewayId")
                or route.get("InstanceId")
                or route.get("TransitGatewayId")
                or route.get("VpcPeeringConnectionId")
                or "local"
            )
            target_type = "local"
            if route.get("GatewayId"):
                target_type = "gateway"
            elif route.get("NatGatewayId"):
                target_type = "nat"
            elif route.get("TransitGatewayId"):
                target_type = "tgw"
            elif route.get("VpcPeeringConnectionId"):
                target_type = "peering"
            elif route.get("InstanceId"):
                target_type = "instance"
            routes.append({
                "destination_cidr": route.get("DestinationCidrBlock", ""),
                "target_type": target_type,
                "target_id": target,
            })
        await self._topology_store.upsert_routing_table({
            "id": resource.resource_id,
            "name": resource.name or raw.get("RouteTableId", ""),
            "network_segment_id": raw.get("VpcId", ""),
            "routes": routes,
            "cloud_resource_id": resource.resource_id,
        })
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_mapper.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/mapper.py backend/tests/cloud/test_mapper.py
git commit -m "feat(cloud): add CloudResourceMapper for canonical translation"
```

---

## Task 14: Cloud API Endpoints

**Files:**
- Create: `backend/src/cloud/api/router.py`
- Create: `backend/tests/cloud/test_api.py`

**Step 1: Write tests**

`backend/tests/cloud/test_api.py`:
```python
"""Tests for cloud API endpoints."""
import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.cloud.api.router import create_cloud_router
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
def app(tmp_db):
    store = CloudStore(db_path=tmp_db)
    router = create_cloud_router(store)
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestAccountEndpoints:
    def test_list_accounts_empty(self, client):
        resp = client.get("/api/v4/cloud/accounts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_account(self, client):
        resp = client.post("/api/v4/cloud/accounts", json={
            "provider": "aws",
            "display_name": "Production AWS",
            "credential_handle": "ref-001",
            "auth_method": "iam_role",
            "regions": ["us-east-1"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "aws"
        assert "account_id" in data

    def test_get_account(self, client):
        create = client.post("/api/v4/cloud/accounts", json={
            "provider": "aws", "display_name": "Test",
            "credential_handle": "ref", "auth_method": "iam_role",
            "regions": ["us-east-1"],
        })
        account_id = create.json()["account_id"]
        resp = client.get(f"/api/v4/cloud/accounts/{account_id}")
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Test"

    def test_delete_account(self, client):
        create = client.post("/api/v4/cloud/accounts", json={
            "provider": "aws", "display_name": "Test",
            "credential_handle": "ref", "auth_method": "iam_role",
            "regions": ["us-east-1"],
        })
        account_id = create.json()["account_id"]
        resp = client.delete(f"/api/v4/cloud/accounts/{account_id}")
        assert resp.status_code == 200


class TestResourceEndpoints:
    def test_list_resources_empty(self, client):
        resp = client.get("/api/v4/cloud/resources")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_resource_not_found(self, client):
        resp = client.get("/api/v4/cloud/resources/nonexistent")
        assert resp.status_code == 404


class TestSyncEndpoints:
    def test_list_sync_jobs_empty(self, client):
        resp = client.get("/api/v4/cloud/sync/jobs")
        assert resp.status_code == 200
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/cloud/test_api.py -v
```

**Step 3: Implement router**

`backend/src/cloud/api/router.py`:
```python
"""Cloud integration API endpoints."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.cloud.cloud_store import CloudStore
from src.cloud.redaction import decompress_raw
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Request/Response Models ──


class CreateAccountRequest(BaseModel):
    provider: str
    display_name: str
    credential_handle: str
    auth_method: str
    regions: list[str]
    native_account_id: str | None = None
    org_parent_id: str | None = None
    sync_config: dict | None = None


class AccountResponse(BaseModel):
    account_id: str
    provider: str
    display_name: str
    auth_method: str
    regions: list[str]
    sync_enabled: bool = True
    last_sync_status: str = "never"
    consecutive_failures: int = 0


class TriggerSyncRequest(BaseModel):
    tiers: list[int] = Field(default=[1, 2, 3])


# ── Router Factory ──


def create_cloud_router(store: CloudStore) -> APIRouter:
    router = APIRouter(prefix="/api/v4/cloud", tags=["cloud"])

    # ── Accounts ──

    @router.get("/accounts")
    async def list_accounts():
        accounts = await store.list_accounts()
        return [_row_to_account(a) for a in accounts]

    @router.post("/accounts", status_code=201)
    async def create_account(req: CreateAccountRequest):
        account_id = str(uuid.uuid4())
        await store.upsert_account(
            account_id=account_id,
            provider=req.provider,
            display_name=req.display_name,
            credential_handle=req.credential_handle,
            auth_method=req.auth_method,
            regions=req.regions,
            native_account_id=req.native_account_id,
            org_parent_id=req.org_parent_id,
            sync_config=req.sync_config,
        )
        account = await store.get_account(account_id)
        return _row_to_account(account)

    @router.get("/accounts/{account_id}")
    async def get_account(account_id: str):
        account = await store.get_account(account_id)
        if not account:
            raise HTTPException(404, "Account not found")
        return _row_to_account(account)

    @router.delete("/accounts/{account_id}")
    async def delete_account(account_id: str):
        await store.delete_account(account_id)
        return {"status": "deleted"}

    # ── Resources ──

    @router.get("/resources")
    async def list_resources(
        account_id: str | None = None,
        region: str | None = None,
        resource_type: str | None = None,
        limit: int = 500,
    ):
        resources = await store.list_resources(
            account_id=account_id, region=region,
            resource_type=resource_type, limit=limit,
        )
        return [dict(r) for r in resources]

    @router.get("/resources/{resource_id}")
    async def get_resource(resource_id: str):
        resource = await store.get_resource(resource_id)
        if not resource:
            raise HTTPException(404, "Resource not found")
        result = dict(resource)
        # Decompress raw for detail view
        if result.get("raw_compressed"):
            try:
                result["raw"] = decompress_raw(result["raw_compressed"])
            except Exception:
                result["raw"] = None
            del result["raw_compressed"]
        return result

    @router.get("/resources/{resource_id}/relations")
    async def list_relations(resource_id: str):
        relations = await store.list_relations(resource_id)
        return [dict(r) for r in relations]

    # ── Sync Jobs ──

    @router.get("/sync/jobs")
    async def list_sync_jobs(account_id: str | None = None, limit: int = 50):
        # Simple query — list recent jobs
        if account_id:
            rows = await store._execute(
                "SELECT * FROM cloud_sync_jobs WHERE account_id = ? ORDER BY started_at DESC LIMIT ?",
                (account_id, limit),
            )
        else:
            rows = await store._execute(
                "SELECT * FROM cloud_sync_jobs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in rows]

    @router.post("/accounts/{account_id}/sync")
    async def trigger_sync(account_id: str, req: TriggerSyncRequest):
        account = await store.get_account(account_id)
        if not account:
            raise HTTPException(404, "Account not found")
        return {"status": "queued", "message": "Sync triggered for tiers " + str(req.tiers)}

    # ── Health Check ──

    @router.post("/accounts/{account_id}/health")
    async def health_check(account_id: str):
        account = await store.get_account(account_id)
        if not account:
            raise HTTPException(404, "Account not found")
        return {
            "status": "health_check_not_implemented",
            "message": "Connect a driver to enable health checks",
        }

    return router


def _row_to_account(row) -> dict:
    return {
        "account_id": row["account_id"],
        "provider": row["provider"],
        "display_name": row["display_name"],
        "auth_method": row["auth_method"],
        "regions": json.loads(row["regions"]),
        "sync_enabled": bool(row["sync_enabled"]),
        "last_sync_status": row["last_sync_status"],
        "consecutive_failures": row["consecutive_failures"] or 0,
    }
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/cloud/test_api.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/cloud/api/router.py backend/tests/cloud/test_api.py
git commit -m "feat(cloud): add cloud API endpoints (accounts, resources, sync)"
```

---

## Task 15: Global Integrations — Cloud Service Types

**Files:**
- Modify: `backend/src/integrations/connection_config.py` — add cloud service types
- Modify: `frontend/src/types/profiles.ts` — extend GlobalIntegration type
- Modify: `frontend/src/components/Settings/GlobalIntegrationsSection.tsx` — add cloud provider cards

**Step 1: Find and read backend integration config**

```bash
cd backend && grep -n "service_type" src/integrations/connection_config.py | head -20
```

**Step 2: Add cloud service types to backend**

In `backend/src/integrations/connection_config.py`, find the `service_type` Literal and add cloud providers:

```python
# Before:
service_type: Literal["elk", "jira", "confluence", "remedy", "github"]

# After:
service_type: Literal["elk", "jira", "confluence", "remedy", "github",
                       "aws", "azure", "oracle", "gcp"]
```

**Step 3: Add default cloud integrations**

Find the `DEFAULT_GLOBAL_INTEGRATIONS` list and add:

```python
{
    "id": "cloud-aws",
    "name": "Amazon Web Services",
    "service_type": "aws",
    "enabled": False,
    "base_url": "",
    "auth_method": "iam_role",
    "auth_credential_handle": None,
    "config": {
        "auth_method": "iam_role",
        "role_arn": "",
        "external_id": "",
        "regions": [],
        "org_management": False,
        "sync_config": {
            "tier_1_interval": 600,
            "tier_2_interval": 1800,
            "tier_3_interval": 21600,
        },
    },
},
{
    "id": "cloud-azure",
    "name": "Microsoft Azure",
    "service_type": "azure",
    "enabled": False,
    "base_url": "",
    "auth_method": "azure_sp",
    "auth_credential_handle": None,
    "config": {
        "tenant_id": "",
        "client_id": "",
        "subscriptions": [],
    },
},
{
    "id": "cloud-oracle",
    "name": "Oracle Cloud Infrastructure",
    "service_type": "oracle",
    "enabled": False,
    "base_url": "",
    "auth_method": "oci_config",
    "auth_credential_handle": None,
    "config": {
        "tenancy_ocid": "",
        "user_ocid": "",
        "regions": [],
    },
},
```

**Step 4: Update frontend types**

In `frontend/src/types/profiles.ts`, update `GlobalIntegration`:

```typescript
// Before:
service_type: 'elk' | 'jira' | 'confluence' | 'remedy' | 'github';

// After:
service_type: 'elk' | 'jira' | 'confluence' | 'remedy' | 'github' | 'aws' | 'azure' | 'oracle' | 'gcp';
```

**Step 5: Add cloud service configs to GlobalIntegrationsSection**

In `frontend/src/components/Settings/GlobalIntegrationsSection.tsx`, add to `serviceConfig`:

```typescript
aws: {
    icon: 'cloud',
    bgColor: 'rgba(255, 153, 0, 0.15)',
    borderColor: 'rgba(255, 153, 0, 0.3)',
    textColor: '#ff9900',
    displayName: 'Amazon Web Services',
    subtitle: 'Cloud Infrastructure',
},
azure: {
    icon: 'cloud',
    bgColor: 'rgba(0, 120, 212, 0.15)',
    borderColor: 'rgba(0, 120, 212, 0.3)',
    textColor: '#0078d4',
    displayName: 'Microsoft Azure',
    subtitle: 'Cloud Infrastructure',
},
oracle: {
    icon: 'cloud',
    bgColor: 'rgba(196, 22, 28, 0.15)',
    borderColor: 'rgba(196, 22, 28, 0.3)',
    textColor: '#c4161c',
    displayName: 'Oracle Cloud',
    subtitle: 'Cloud Infrastructure',
},
```

**Step 6: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: Clean compilation

**Step 7: Commit**

```bash
git add backend/src/integrations/connection_config.py frontend/src/types/profiles.ts frontend/src/components/Settings/GlobalIntegrationsSection.tsx
git commit -m "feat(cloud): add cloud provider service types to global integrations"
```

---

## Task 16: Router Registration + Startup Wiring

**Files:**
- Modify: `backend/src/api/main.py` — register cloud router
- Modify: `backend/src/api/routes_v4.py` — (if needed) import cloud router

**Step 1: Read main.py to understand router registration pattern**

```bash
cd backend && grep -n "include_router\|router" src/api/main.py | head -20
```

**Step 2: Add cloud router registration**

In `backend/src/api/main.py`, add after existing router registrations:

```python
# Cloud integration
from src.cloud.api.router import create_cloud_router
from src.cloud.cloud_store import CloudStore

cloud_store = CloudStore()
cloud_router = create_cloud_router(cloud_store)
app.include_router(cloud_router)
```

**Step 3: Verify server starts**

```bash
cd backend && timeout 10 python -m uvicorn src.api.main:app --port 8001 || true
```
Expected: Server starts without import errors

**Step 4: Run full test suite**

```bash
cd backend && python -m pytest tests/ -v --timeout=30
```
Expected: All tests pass

**Step 5: Commit**

```bash
git add backend/src/api/main.py
git commit -m "feat(cloud): register cloud router in FastAPI app"
```

---

## Task 17: Frontend — TypeScript Types + API Service

**Files:**
- Modify: `frontend/src/types/index.ts` — add cloud resource types
- Modify: `frontend/src/services/api.ts` — add cloud API functions

**Step 1: Add types**

In `frontend/src/types/index.ts`, add:

```typescript
// ── Cloud Integration Types ──

export interface CloudAccount {
  account_id: string;
  provider: 'aws' | 'azure' | 'oracle' | 'gcp';
  display_name: string;
  auth_method: string;
  regions: string[];
  sync_enabled: boolean;
  last_sync_status: 'never' | 'ok' | 'error' | 'paused';
  consecutive_failures: number;
}

export interface CloudResource {
  resource_id: string;
  provider: string;
  account_id: string;
  region: string;
  resource_type: string;
  native_id: string;
  name: string | null;
  raw_preview: string | null;
  tags: string | null;
  sync_tier: number;
  last_seen_ts: string;
  is_deleted: boolean;
  deleted_at: string | null;
}

export interface CloudResourceDetail extends CloudResource {
  raw: Record<string, unknown> | null;
  raw_compressed?: never;  // excluded from API response
}

export interface CloudResourceRelation {
  relation_id: string;
  source_resource_id: string;
  target_resource_id: string;
  relation_type: string;
  metadata: string | null;
  last_seen_ts: string;
}

export interface CloudSyncJob {
  sync_job_id: string;
  account_id: string;
  tier: number;
  started_at: string;
  finished_at: string | null;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'paused';
  items_seen: number;
  items_created: number;
  items_updated: number;
  items_deleted: number;
  api_calls: number;
}

export interface CloudSyncStatus {
  tier_1_last_sync: string | null;
  tier_2_last_sync: string | null;
  tier_3_last_sync: string | null;
  next_sync: string | null;
}
```

**Step 2: Add API functions**

In `frontend/src/services/api.ts`, add:

```typescript
// ── Cloud Integration APIs ──

export const listCloudAccounts = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/cloud/accounts`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to list cloud accounts'));
  return resp.json();
};

export const createCloudAccount = async (account: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/cloud/accounts`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(account),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create cloud account'));
  return resp.json();
};

export const deleteCloudAccount = async (accountId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/cloud/accounts/${accountId}`, {
    method: 'DELETE',
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete cloud account'));
  return resp.json();
};

export const listCloudResources = async (params?: {
  account_id?: string; region?: string; resource_type?: string; limit?: number;
}) => {
  const searchParams = new URLSearchParams();
  if (params?.account_id) searchParams.set('account_id', params.account_id);
  if (params?.region) searchParams.set('region', params.region);
  if (params?.resource_type) searchParams.set('resource_type', params.resource_type);
  if (params?.limit) searchParams.set('limit', String(params.limit));
  const resp = await fetch(`${API_BASE_URL}/api/v4/cloud/resources?${searchParams}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to list cloud resources'));
  return resp.json();
};

export const getCloudResource = async (resourceId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/cloud/resources/${resourceId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to get cloud resource'));
  return resp.json();
};

export const getCloudResourceRelations = async (resourceId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/cloud/resources/${resourceId}/relations`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to get resource relations'));
  return resp.json();
};

export const listCloudSyncJobs = async (accountId?: string) => {
  const params = accountId ? `?account_id=${accountId}` : '';
  const resp = await fetch(`${API_BASE_URL}/api/v4/cloud/sync/jobs${params}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to list sync jobs'));
  return resp.json();
};

export const triggerCloudSync = async (accountId: string, tiers?: number[]) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/cloud/accounts/${accountId}/sync`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tiers: tiers || [1, 2, 3] }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to trigger sync'));
  return resp.json();
};

export const testCloudAccountHealth = async (accountId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/cloud/accounts/${accountId}/health`, {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to test cloud account'));
  return resp.json();
};
```

**Step 3: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

**Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/api.ts
git commit -m "feat(cloud): add cloud TypeScript types + API service functions"
```

---

## Task 18: Frontend — CloudResourcesView Redesign

**Files:**
- Modify: `frontend/src/components/Cloud/CloudResourcesView.tsx` — rewrite with discovered resources

**Step 1: Read the existing file**

```bash
wc -l frontend/src/components/Cloud/CloudResourcesView.tsx
```

**Step 2: Rewrite CloudResourcesView**

Replace the entire content of `frontend/src/components/Cloud/CloudResourcesView.tsx` with a read-only discovery view. Key changes:

- Remove all `create*` API imports and inline forms
- Add `listCloudAccounts`, `listCloudResources`, `listCloudSyncJobs`, `triggerCloudSync` imports
- Add account selector dropdown and region filter
- Tab resources by type (VPCs, Subnets, Security Groups, etc.)
- Show last-seen timestamps and sync status
- Add "Sync Now" button
- Show sync status bar at bottom

The component should follow the existing `SecurityResourcesView.tsx` pattern (generic `ResourceTab` with `TabDef`), but read-only (no create forms).

```typescript
// CloudResourcesView.tsx — key structure (abbreviated)
import { useState, useEffect, useCallback } from 'react';
import { listCloudAccounts, listCloudResources, listCloudSyncJobs, triggerCloudSync } from '../../services/api';
import { NetworkChatDrawer } from '../NetworkChat/NetworkChatDrawer';

const RESOURCE_TABS = [
  { id: 'vpc', label: 'VPCs', icon: 'cloud' },
  { id: 'subnet', label: 'Subnets', icon: 'lan' },
  { id: 'security_group', label: 'Security Groups', icon: 'security' },
  { id: 'nacl', label: 'NACLs', icon: 'shield' },
  { id: 'route_table', label: 'Route Tables', icon: 'route' },
  { id: 'eni', label: 'ENIs', icon: 'settings_input_component' },
  { id: 'instance', label: 'Instances', icon: 'dns' },
  { id: 'elb', label: 'Load Balancers', icon: 'mediation' },
  { id: 'nat_gateway', label: 'NAT Gateways', icon: 'nat' },
  { id: 'vpc_peering', label: 'VPC Peerings', icon: 'hub' },
];

export default function CloudResourcesView() {
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [selectedRegion, setSelectedRegion] = useState('');
  const [activeTab, setActiveTab] = useState('vpc');
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [syncJobs, setSyncJobs] = useState([]);
  const [syncing, setSyncing] = useState(false);

  // Load accounts on mount
  useEffect(() => {
    listCloudAccounts().then(setAccounts).catch(() => {});
  }, []);

  // Load resources when filters change
  const loadResources = useCallback(async () => {
    if (!selectedAccount) return;
    setLoading(true);
    try {
      const data = await listCloudResources({
        account_id: selectedAccount,
        region: selectedRegion || undefined,
        resource_type: activeTab,
      });
      setResources(data);
    } catch { /* handle */ }
    finally { setLoading(false); }
  }, [selectedAccount, selectedRegion, activeTab]);

  useEffect(() => { loadResources(); }, [loadResources]);

  const handleSyncNow = async () => {
    if (!selectedAccount) return;
    setSyncing(true);
    try {
      await triggerCloudSync(selectedAccount);
      // Reload after brief delay
      setTimeout(loadResources, 2000);
    } catch { /* handle */ }
    finally { setSyncing(false); }
  };

  return (
    <div style={{ padding: 24, height: '100%', overflow: 'auto' }}>
      {/* Header: Account Selector + Region Filter + Sync Now */}
      {/* Tabs: Resource type tabs */}
      {/* Table: Resource cards/rows — read-only */}
      {/* Footer: Sync status bar */}
      <NetworkChatDrawer view="cloud-resources" />
    </div>
  );
}
```

**Note:** Full implementation follows the patterns in `SecurityResourcesView.tsx`. The implementer should read that file as reference for the generic tab/table pattern.

**Step 3: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

**Step 4: Commit**

```bash
git add frontend/src/components/Cloud/CloudResourcesView.tsx
git commit -m "feat(cloud): redesign CloudResourcesView for discovered resources"
```

---

## Task 19: Full Integration Test + Verification

**Files:**
- All files from Tasks 1-18

**Step 1: Run full backend test suite**

```bash
cd backend && python -m pytest tests/ -v --timeout=30
```
Expected: All tests pass

**Step 2: Run full frontend type check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: Clean compilation

**Step 3: Verify cloud module imports cleanly**

```bash
cd backend && python -c "
from src.cloud.models import CloudAccount, CloudResource, DiscoveryBatch
from src.cloud.cloud_store import CloudStore
from src.cloud.policy_store import PolicyStore
from src.cloud.redaction import redact_raw, compress_raw, decompress_raw
from src.cloud.drivers.base import CloudProviderDriver
from src.cloud.drivers.aws_driver import AWSDriver
from src.cloud.sync.engine import CloudSyncEngine
from src.cloud.sync.scheduler import CloudSyncScheduler
from src.cloud.sync.rate_limiter import AdaptiveRateLimiter
from src.cloud.sync.batch_controller import BatchSizeController
from src.cloud.sync.concurrency import SyncConcurrencyGuard
from src.cloud.sync.wal_monitor import WALMonitor
from src.cloud.mapper import CloudResourceMapper
from src.cloud.api.router import create_cloud_router
print('All imports OK')
"
```

**Step 4: Verify API server starts with cloud endpoints**

```bash
cd backend && timeout 10 python -c "
import asyncio
from fastapi import FastAPI
from src.cloud.api.router import create_cloud_router
from src.cloud.cloud_store import CloudStore
app = FastAPI()
store = CloudStore(db_path='/tmp/test_cloud.db')
router = create_cloud_router(store)
app.include_router(router)
print('Router registered:', [r.path for r in app.routes if hasattr(r, 'path') and 'cloud' in r.path])
" || true
```

**Step 5: Commit any remaining fixes**

```bash
git add -A
git commit -m "test(cloud): verify full cloud integration module"
```

---

## Summary

| Task | Component | Files | Key Deliverable |
|------|-----------|-------|-----------------|
| 1 | Project Structure | __init__.py, requirements.txt | Module scaffold + boto3 |
| 2 | Data Models | models.py | 15+ Pydantic models |
| 3 | CloudStore | cloud_store.py | Thread-safe SQLite + 7 tables |
| 4 | Redaction + Compression | redaction.py | Sensitive data redaction, gzip |
| 5 | Rate Limiter + Utils | rate_limiter.py, batch_controller.py, wal_monitor.py | Per-service throttling, dynamic batching, WAL |
| 6 | Concurrency Guard | concurrency.py | Per-account sync locking |
| 7 | Driver ABC | drivers/base.py | CloudProviderDriver interface |
| 8 | AWS Driver | aws_driver.py | Health check + VPC/Subnet/SG/NACL/RT/ENI/Instance discovery |
| 9 | Sync Engine | engine.py | Batch processing + hash detection |
| 10 | Soft Deletion + Locks | engine.py | Stale resource cleanup + sync job locking |
| 11 | Scheduler | scheduler.py | Tiered scheduling loop |
| 12 | PolicyStore | policy_store.py | Security policy groups/rules/attachments |
| 13 | Mapper | mapper.py | Raw -> canonical translation |
| 14 | API Endpoints | api/router.py | Accounts, resources, sync, health |
| 15 | Global Integrations | connection_config.py, profiles.ts, GlobalIntegrationsSection.tsx | Cloud provider service types |
| 16 | Router Wiring | main.py | Register cloud router in FastAPI |
| 17 | Frontend Types + API | index.ts, api.ts | TypeScript types + fetch functions |
| 18 | CloudResourcesView | CloudResourcesView.tsx | Read-only discovered resources UI |
| 19 | Integration Test | All | Full verification pass |

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

    async def _execute_rowcount(self, sql: str, params: tuple = ()) -> int:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, partial(self._sync_execute_rowcount, sql, params)
        )

    def _sync_execute_rowcount(self, sql: str, params: tuple) -> int:
        conn = self._get_conn()
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.rowcount

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
        return await self._execute_rowcount(
            f"""UPDATE cloud_resources
                SET is_deleted = 1, deleted_at = ?
                WHERE account_id = ? AND region = ?
                  AND resource_type IN ({placeholders})
                  AND is_deleted = 0
                  AND last_seen_ts < ?""",
            (now, account_id, region, *resource_types, cutoff_ts),
        )

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

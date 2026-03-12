"""Security policy store — separated from adapter_registry.

Manages policy groups (security groups / NACLs / firewall rules),
individual rules within each group, and attachments to target resources.

Uses the same ThreadPoolExecutor(max_workers=1) pattern as CloudStore
so all SQLite writes are serialised on a single dedicated thread.
"""
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

    # ── Connection ──

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=30000")
        return self._conn

    def _init_schema(self) -> None:
        """Create tables synchronously at startup."""
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_POLICY_SCHEMA)
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
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self._executor,
            partial(self._sync_replace_rules, policy_group_id, rules),
        )

    def _sync_replace_rules(self, policy_group_id: str, rules: list[dict]) -> None:
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


# ── Schema DDL ──

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

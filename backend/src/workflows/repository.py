from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import sqlite3

import aiosqlite

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


class WorkflowRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._write_lock = asyncio.Lock()

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
                sql = sql_file.read_text()
                for stmt in sql.split(";"):
                    stmt = stmt.strip()
                    if not stmt:
                        continue
                    try:
                        await db.execute(stmt)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column" not in str(exc):
                            raise
            await db.commit()

    @asynccontextmanager
    async def _conn(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            yield db

    async def create_workflow(
        self, *, name: str, description: str | None, created_by: str | None
    ) -> str:
        wf_id = _new_id()
        async with self._conn() as db:
            await db.execute(
                "INSERT INTO workflows (id, name, description, created_at, created_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (wf_id, name, description, _now(), created_by),
            )
            await db.commit()
        return wf_id

    async def get_workflow(self, id: str) -> dict[str, Any] | None:
        async with self._conn() as db:
            async with db.execute(
                "SELECT * FROM workflows WHERE id = ?", (id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def list_workflows(self) -> list[dict[str, Any]]:
        async with self._conn() as db:
            async with db.execute(
                "SELECT * FROM workflows WHERE deleted_at IS NULL ORDER BY created_at ASC"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def soft_delete_workflow(self, id: str) -> None:
        async with self._conn() as db:
            await db.execute(
                "UPDATE workflows SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                (_now(), id),
            )
            await db.commit()

    async def has_active_runs(self, workflow_id: str) -> bool:
        async with self._conn() as db:
            async with db.execute(
                "SELECT 1 FROM workflow_runs wr "
                "JOIN workflow_versions wv ON wr.workflow_version_id = wv.id "
                "WHERE wv.workflow_id = ? AND wr.status IN ('running', 'pending', 'cancelling') "
                "LIMIT 1",
                (workflow_id,),
            ) as cur:
                return await cur.fetchone() is not None

    async def update_workflow(
        self, id: str, *, name: str | None = None, description: str | None = None
    ) -> None:
        parts: list[str] = []
        vals: list[Any] = []
        if name is not None:
            parts.append("name = ?")
            vals.append(name)
        if description is not None:
            parts.append("description = ?")
            vals.append(description)
        if not parts:
            return
        vals.append(id)
        async with self._conn() as db:
            await db.execute(
                f"UPDATE workflows SET {', '.join(parts)} WHERE id = ?",
                tuple(vals),
            )
            await db.commit()

    async def duplicate_workflow(self, source_id: str, new_name: str) -> str:
        source = await self.get_workflow(source_id)
        if source is None:
            raise LookupError("source workflow not found")
        latest = await self.get_latest_version(source_id)
        if latest is None:
            raise LookupError("source has no versions")
        new_id = _new_id()
        async with self._conn() as db:
            await db.execute(
                "INSERT INTO workflows (id, name, description, created_at, created_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (new_id, new_name, source["description"], _now(), source.get("created_by")),
            )
            v_id = _new_id()
            await db.execute(
                "INSERT INTO workflow_versions "
                "(id, workflow_id, version, dag_json, compiled_json, is_active, created_at) "
                "VALUES (?, ?, 1, ?, ?, 1, ?)",
                (v_id, new_id, latest["dag_json"], latest["compiled_json"], _now()),
            )
            await db.commit()
        return new_id

    async def rollback_version(
        self, workflow_id: str, target_version: int
    ) -> tuple[str, int]:
        target = await self.get_version(workflow_id, target_version)
        if target is None:
            raise LookupError("target version not found")
        latest = await self.get_latest_version(workflow_id)
        next_version = (latest["version"] + 1) if latest else 1
        v_id = await self.create_version(
            workflow_id, next_version, target["dag_json"], target["compiled_json"]
        )
        return v_id, next_version

    async def list_runs(
        self,
        *,
        workflow_id: str | None = None,
        statuses: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        sort: str = "started_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        where: list[str] = []
        params: list[Any] = []
        if workflow_id is not None:
            where.append(
                "wr.workflow_version_id IN "
                "(SELECT id FROM workflow_versions WHERE workflow_id = ?)"
            )
            params.append(workflow_id)
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            where.append(f"wr.status IN ({placeholders})")
            params.extend(statuses)
        if from_date:
            where.append("wr.started_at >= ?")
            params.append(from_date)
        if to_date:
            where.append("wr.started_at <= ?")
            params.append(to_date)
        where_clause = " AND ".join(where) if where else "1=1"
        sort_col = "wr.started_at"
        order_dir = "DESC" if order == "desc" else "ASC"
        async with self._conn() as db:
            async with db.execute(
                f"SELECT COUNT(*) FROM workflow_runs wr WHERE {where_clause}",
                tuple(params),
            ) as cur:
                total = (await cur.fetchone())[0]
            async with db.execute(
                f"SELECT wr.* FROM workflow_runs wr "
                f"WHERE {where_clause} ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
        return rows, total

    async def get_latest_run_for_workflow(
        self, workflow_id: str
    ) -> dict[str, Any] | None:
        async with self._conn() as db:
            async with db.execute(
                "SELECT wr.* FROM workflow_runs wr "
                "JOIN workflow_versions wv ON wr.workflow_version_id = wv.id "
                "WHERE wv.workflow_id = ? ORDER BY wr.started_at DESC LIMIT 1",
                (workflow_id,),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def create_version(
        self,
        workflow_id: str,
        version: int,
        dag_json: str,
        compiled_json: str,
    ) -> str:
        v_id = _new_id()
        async with self._conn() as db:
            await db.execute(
                "INSERT INTO workflow_versions "
                "(id, workflow_id, version, dag_json, compiled_json, is_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?)",
                (v_id, workflow_id, version, dag_json, compiled_json, _now()),
            )
            await db.commit()
        return v_id

    async def get_version(
        self, workflow_id: str, version: int
    ) -> dict[str, Any] | None:
        async with self._conn() as db:
            async with db.execute(
                "SELECT * FROM workflow_versions WHERE workflow_id = ? AND version = ?",
                (workflow_id, version),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def list_versions(self, workflow_id: str) -> list[dict[str, Any]]:
        async with self._conn() as db:
            async with db.execute(
                "SELECT * FROM workflow_versions WHERE workflow_id = ? "
                "ORDER BY version DESC",
                (workflow_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_latest_version(
        self, workflow_id: str
    ) -> dict[str, Any] | None:
        async with self._conn() as db:
            async with db.execute(
                "SELECT * FROM workflow_versions WHERE workflow_id = ? "
                "ORDER BY version DESC LIMIT 1",
                (workflow_id,),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def create_run(
        self,
        *,
        workflow_version_id: str,
        inputs_json: str,
        idempotency_key: str | None,
        run_mode: str = "workflow",
    ) -> str:
        async with self._conn() as db:
            if idempotency_key is not None:
                async with db.execute(
                    "SELECT id FROM workflow_runs WHERE workflow_version_id = ? "
                    "AND idempotency_key = ?",
                    (workflow_version_id, idempotency_key),
                ) as cur:
                    existing = await cur.fetchone()
                    if existing:
                        return existing["id"]
            run_id = _new_id()
            await db.execute(
                "INSERT INTO workflow_runs "
                "(id, workflow_version_id, status, started_at, inputs_json, "
                "idempotency_key, run_mode) "
                "VALUES (?, ?, 'pending', NULL, ?, ?, ?)",
                (run_id, workflow_version_id, inputs_json, idempotency_key, run_mode),
            )
            await db.commit()
            return run_id

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        async with self._conn() as db:
            async with db.execute(
                "SELECT * FROM workflow_runs WHERE id = ?", (run_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def update_run_status(
        self,
        run_id: str,
        status: str,
        ended_at: str | None = None,
        error_json: str | None = None,
    ) -> None:
        async with self._conn() as db:
            await db.execute(
                "UPDATE workflow_runs SET status = ?, ended_at = COALESCE(?, ended_at), "
                "error_json = COALESCE(?, error_json) WHERE id = ?",
                (status, ended_at, error_json, run_id),
            )
            await db.commit()

    async def create_step_run(
        self, run_id: str, step_id: str, attempt: int
    ) -> str:
        sr_id = _new_id()
        async with self._conn() as db:
            await db.execute(
                "INSERT INTO workflow_step_runs "
                "(id, run_id, step_id, status, started_at, attempt) "
                "VALUES (?, ?, ?, 'running', ?, ?)",
                (sr_id, run_id, step_id, _now(), attempt),
            )
            await db.commit()
        return sr_id

    async def update_step_run(
        self,
        step_run_id: str,
        status: str,
        output_json: str | None = None,
        ended_at: str | None = None,
        duration_ms: int | None = None,
        error_json: str | None = None,
    ) -> None:
        async with self._conn() as db:
            await db.execute(
                "UPDATE workflow_step_runs SET status = ?, "
                "output_json = COALESCE(?, output_json), "
                "ended_at = COALESCE(?, ended_at), "
                "duration_ms = COALESCE(?, duration_ms), "
                "error_json = COALESCE(?, error_json) "
                "WHERE id = ?",
                (status, output_json, ended_at, duration_ms, error_json, step_run_id),
            )
            await db.commit()

    async def list_step_runs(self, run_id: str) -> list[dict[str, Any]]:
        async with self._conn() as db:
            async with db.execute(
                "SELECT * FROM workflow_step_runs WHERE run_id = ? "
                "ORDER BY started_at ASC",
                (run_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def append_event(
        self,
        run_id: str,
        type: str,
        node_id: str | None = None,
        attempt: int | None = None,
        duration_ms: int | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
        parent_node_id: str | None = None,
        payload_json: str | None = None,
    ) -> tuple[str, int]:
        # Sequence is computed inside the write lock + transaction so concurrent
        # appenders cannot observe the same MAX(sequence) and produce duplicates.
        event_id = _new_id()
        async with self._write_lock:
            async with self._conn() as db:
                await db.execute("BEGIN IMMEDIATE")
                async with db.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM workflow_run_events "
                    "WHERE run_id = ?",
                    (run_id,),
                ) as cur:
                    row = await cur.fetchone()
                    sequence = int(row[0])
                await db.execute(
                    "INSERT INTO workflow_run_events "
                    "(event_id, run_id, sequence, timestamp, type, node_id, attempt, "
                    "duration_ms, error_class, error_message, parent_node_id, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        run_id,
                        sequence,
                        _now(),
                        type,
                        node_id,
                        attempt,
                        duration_ms,
                        error_class,
                        error_message,
                        parent_node_id,
                        payload_json,
                    ),
                )
                await db.commit()
        return event_id, sequence

    async def list_events(
        self, run_id: str, after_sequence: int = 0
    ) -> list[dict[str, Any]]:
        async with self._conn() as db:
            async with db.execute(
                "SELECT * FROM workflow_run_events WHERE run_id = ? AND sequence > ? "
                "ORDER BY sequence ASC",
                (run_id, after_sequence),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

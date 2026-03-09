"""SQLite persistence for remediation plans and audit log."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, UTC


class RemediationStore:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._ensure_tables()

    def _conn(self):
        c = sqlite3.connect(self._db_path)
        c.row_factory = sqlite3.Row
        return c

    def _ensure_tables(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS remediation_plans (
                    plan_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    finding_id TEXT,
                    action TEXT NOT NULL,
                    params TEXT NOT NULL DEFAULT '{}',
                    sql_preview TEXT NOT NULL,
                    impact_assessment TEXT DEFAULT '',
                    rollback_sql TEXT,
                    requires_downtime INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    executed_at TEXT,
                    completed_at TEXT,
                    result_summary TEXT,
                    before_state TEXT,
                    after_state TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    entry_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    sql_executed TEXT NOT NULL,
                    status TEXT NOT NULL,
                    before_state TEXT DEFAULT '{}',
                    after_state TEXT DEFAULT '{}',
                    error TEXT,
                    timestamp TEXT NOT NULL
                )
            """)

    def create_plan(self, profile_id: str, action: str, params: dict,
                    sql_preview: str, impact_assessment: str = "",
                    rollback_sql: str | None = None,
                    requires_downtime: bool = False,
                    finding_id: str | None = None) -> dict:
        plan_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT INTO remediation_plans
                   (plan_id, profile_id, finding_id, action, params, sql_preview,
                    impact_assessment, rollback_sql, requires_downtime, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (plan_id, profile_id, finding_id, action,
                 json.dumps(params), sql_preview, impact_assessment,
                 rollback_sql, int(requires_downtime), "pending", now),
            )
        return self.get_plan(plan_id)

    def get_plan(self, plan_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM remediation_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_plan(row)

    def update_plan(self, plan_id: str, **fields) -> dict | None:
        allowed = {
            "status", "approved_at", "executed_at", "completed_at",
            "result_summary", "before_state", "after_state",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_plan(plan_id)
        # JSON-encode dict fields
        for key in ("before_state", "after_state"):
            if key in updates and isinstance(updates[key], dict):
                updates[key] = json.dumps(updates[key])
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [plan_id]
        with self._conn() as c:
            c.execute(
                f"UPDATE remediation_plans SET {set_clause} WHERE plan_id = ?",
                values,
            )
        return self.get_plan(plan_id)

    def list_plans(self, profile_id: str, status: str | None = None) -> list[dict]:
        query = "SELECT * FROM remediation_plans WHERE profile_id = ?"
        params: list = [profile_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        with self._conn() as c:
            rows = c.execute(query, params).fetchall()
        return [self._row_to_plan(r) for r in rows]

    def add_audit_entry(self, plan_id: str, profile_id: str, action: str,
                        sql_executed: str, status: str,
                        before_state: dict | None = None,
                        after_state: dict | None = None,
                        error: str | None = None) -> dict:
        entry_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT INTO audit_log
                   (entry_id, plan_id, profile_id, action, sql_executed,
                    status, before_state, after_state, error, timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (entry_id, plan_id, profile_id, action, sql_executed,
                 status, json.dumps(before_state or {}),
                 json.dumps(after_state or {}), error, now),
            )
        return self._get_audit_entry(entry_id)

    def get_audit_log(self, profile_id: str, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM audit_log WHERE profile_id = ? ORDER BY timestamp DESC LIMIT ?",
                (profile_id, limit),
            ).fetchall()
        return [self._row_to_audit(r) for r in rows]

    def _get_audit_entry(self, entry_id: str) -> dict:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM audit_log WHERE entry_id = ?", (entry_id,)
            ).fetchone()
        return self._row_to_audit(row) if row else {}

    @staticmethod
    def _row_to_plan(row) -> dict:
        d = dict(row)
        d["params"] = json.loads(d.get("params") or "{}")
        d["requires_downtime"] = bool(d.get("requires_downtime", 0))
        for key in ("before_state", "after_state"):
            val = d.get(key)
            if val and isinstance(val, str):
                d[key] = json.loads(val)
        return d

    @staticmethod
    def _row_to_audit(row) -> dict:
        d = dict(row)
        for key in ("before_state", "after_state"):
            val = d.get(key)
            if val and isinstance(val, str):
                d[key] = json.loads(val)
        return d

"""SQLite-backed store for diagnostic run history."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Optional


class DiagnosticRunStore:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._ensure_table()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS db_diagnostic_runs (
                    run_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    findings TEXT NOT NULL DEFAULT '[]',
                    summary TEXT NOT NULL DEFAULT ''
                )
            """)

    def create(self, profile_id: str) -> dict:
        run_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO db_diagnostic_runs (run_id, profile_id, started_at) VALUES (?,?,?)",
                (run_id, profile_id, now),
            )
        return self.get(run_id)  # type: ignore

    def get(self, run_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM db_diagnostic_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "run_id": row["run_id"],
            "profile_id": row["profile_id"],
            "status": row["status"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "findings": json.loads(row["findings"]),
            "summary": row["summary"],
        }

    def update(self, run_id: str, **fields) -> None:
        allowed = {"status", "summary", "completed_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [run_id]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE db_diagnostic_runs SET {set_clause} WHERE run_id = ?",
                values,
            )

    def add_finding(self, run_id: str, finding: dict) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT findings FROM db_diagnostic_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if not row:
                return
            findings = json.loads(row["findings"])
            findings.append(finding)
            conn.execute(
                "UPDATE db_diagnostic_runs SET findings = ? WHERE run_id = ?",
                (json.dumps(findings), run_id),
            )

    def list_by_profile(self, profile_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM db_diagnostic_runs WHERE profile_id = ? ORDER BY started_at DESC",
                (profile_id,),
            ).fetchall()
        return [
            {
                "run_id": r["run_id"],
                "profile_id": r["profile_id"],
                "status": r["status"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
                "findings": json.loads(r["findings"]),
                "summary": r["summary"],
            }
            for r in rows
        ]

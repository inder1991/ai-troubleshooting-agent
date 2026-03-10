"""Evidence artifact storage for database diagnostic sessions.

Stores large tool outputs (EXPLAIN plans, pg_stat dumps) outside
LLM context. Agents receive compact summaries; full content is
retrievable by artifact_id for UI preview and audit.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional


class EvidenceStore:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence_artifacts (
                    artifact_id   TEXT PRIMARY KEY,
                    session_id    TEXT NOT NULL,
                    evidence_id   TEXT NOT NULL,
                    source_agent  TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    summary_json  TEXT NOT NULL,
                    full_content  TEXT NOT NULL,
                    preview       TEXT,
                    timestamp     TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_evidence_session
                ON evidence_artifacts(session_id)
            """)

    def create(
        self,
        session_id: str,
        evidence_id: str,
        source_agent: str,
        artifact_type: str,
        summary_json: dict,
        full_content: str,
        preview: Optional[str] = None,
    ) -> dict:
        artifact_id = f"art-{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        row = {
            "artifact_id": artifact_id,
            "session_id": session_id,
            "evidence_id": evidence_id,
            "source_agent": source_agent,
            "artifact_type": artifact_type,
            "summary_json": json.dumps(summary_json),
            "full_content": full_content,
            "preview": preview,
            "timestamp": timestamp,
        }
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO evidence_artifacts
                   (artifact_id, session_id, evidence_id, source_agent,
                    artifact_type, summary_json, full_content, preview, timestamp)
                   VALUES (:artifact_id, :session_id, :evidence_id, :source_agent,
                           :artifact_type, :summary_json, :full_content, :preview, :timestamp)""",
                row,
            )
        row["summary_json"] = summary_json
        return row

    def get(self, artifact_id: str) -> Optional[dict]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM evidence_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["summary_json"] = json.loads(result["summary_json"])
        return result

    def list_by_session(self, session_id: str) -> list[dict]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM evidence_artifacts WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r["summary_json"] = json.loads(r["summary_json"])
            results.append(r)
        return results

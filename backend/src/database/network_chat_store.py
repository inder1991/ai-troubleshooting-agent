"""SQLite-backed store for network-chat threads and messages.

Provides persistence for the LLM-powered chat overlay on network
views (topology, flows, knowledge-graph).  Each user+view pair has
at most one *active* (non-escalated) thread at a time.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional


class NetworkChatStore:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._ensure_tables()

    # ── connection helper ─────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ── schema bootstrap ──────────────────────────────────────

    def _ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS network_chat_threads (
                    thread_id               TEXT PRIMARY KEY,
                    user_id                 TEXT NOT NULL,
                    view                    TEXT NOT NULL,
                    created_at              TEXT NOT NULL,
                    last_message_at         TEXT NOT NULL,
                    investigation_session_id TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS network_chat_messages (
                    message_id  TEXT PRIMARY KEY,
                    thread_id   TEXT NOT NULL
                                REFERENCES network_chat_threads(thread_id),
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    tool_name   TEXT,
                    tool_args   TEXT,
                    tool_result TEXT,
                    timestamp   TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ncm_thread
                ON network_chat_messages(thread_id, timestamp)
            """)

    # ── Thread ops ────────────────────────────────────────────

    def create_thread(self, user_id: str, view: str) -> dict:
        thread_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO network_chat_threads
                   (thread_id, user_id, view, created_at, last_message_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (thread_id, user_id, view, now, now),
            )
        return self.get_thread(thread_id)  # type: ignore[return-value]

    def get_thread(self, thread_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM network_chat_threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_active_thread(self, user_id: str, view: str) -> Optional[dict]:
        """Return the most recent non-escalated thread for *user_id* + *view*."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM network_chat_threads
                   WHERE user_id = ?
                     AND view = ?
                     AND investigation_session_id IS NULL
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (user_id, view),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def escalate_thread(
        self, thread_id: str, investigation_session_id: str
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE network_chat_threads
                   SET investigation_session_id = ?
                   WHERE thread_id = ?""",
                (investigation_session_id, thread_id),
            )

    # ── Message ops ───────────────────────────────────────────

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        tool_name: Optional[str] = None,
        tool_args: Optional[dict] = None,
        tool_result: Optional[dict] = None,
    ) -> dict:
        message_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO network_chat_messages
                   (message_id, thread_id, role, content,
                    tool_name, tool_args, tool_result, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message_id,
                    thread_id,
                    role,
                    content,
                    tool_name,
                    json.dumps(tool_args) if tool_args is not None else None,
                    json.dumps(tool_result) if tool_result is not None else None,
                    now,
                ),
            )
            # bump thread's last_message_at
            conn.execute(
                """UPDATE network_chat_threads
                   SET last_message_at = ?
                   WHERE thread_id = ?""",
                (now, thread_id),
            )
        return self._get_message(message_id)  # type: ignore[return-value]

    def list_messages(self, thread_id: str, limit: int = 20) -> list[dict]:
        """Return the *last* ``limit`` messages, ordered chronologically."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM (
                       SELECT * FROM network_chat_messages
                       WHERE thread_id = ?
                       ORDER BY timestamp DESC
                       LIMIT ?
                   ) sub
                   ORDER BY timestamp ASC""",
                (thread_id, limit),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    # ── internal helpers ──────────────────────────────────────

    def _get_message(self, message_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM network_chat_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_message(row)

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["tool_args"] = json.loads(d["tool_args"]) if d["tool_args"] else None
        d["tool_result"] = json.loads(d["tool_result"]) if d["tool_result"] else None
        return d

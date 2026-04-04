"""DiagnosticStore: abstract interface + SQLite + Redis implementations + factory."""
from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    event_json  TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id);

CREATE TABLE IF NOT EXISTS llm_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    agent_name    TEXT,
    model         TEXT,
    call_type     TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    latency_ms    INTEGER,
    success       INTEGER,
    error         TEXT,
    fallback_used INTEGER,
    response_json TEXT,
    created_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_session ON llm_calls(session_id);
"""


class DiagnosticStore(ABC):
    @abstractmethod
    async def initialize(self) -> None:
        """Create tables / connections. Call once on startup."""

    @abstractmethod
    async def append_event(self, session_id: str, event: dict) -> int:
        """Persist event. Returns assigned sequence_number (monotonically increasing)."""

    @abstractmethod
    async def get_events(self, session_id: str, after_sequence: int = 0) -> list[dict]:
        """Return events for session with sequence_number > after_sequence, ordered ascending."""

    @abstractmethod
    async def log_llm_call(self, record: dict) -> None:
        """Persist LLM call metadata."""

    @abstractmethod
    async def get_llm_calls(self, session_id: str) -> list[dict]:
        """Return all LLM call records for session, ordered by created_at."""

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """Remove all events and llm_calls for the session (called on TTL expiry)."""


class SQLiteDiagnosticStore(DiagnosticStore):
    def __init__(self, path: str) -> None:
        self._path = path

    async def initialize(self) -> None:
        os.makedirs(os.path.dirname(self._path) if os.path.dirname(self._path) else ".", exist_ok=True)
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_DDL)
            await db.commit()

    async def append_event(self, session_id: str, event: dict) -> int:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "INSERT INTO events (session_id, event_json, created_at) VALUES (?, ?, ?)",
                (session_id, json.dumps(event, default=str), time.time()),
            )
            await db.commit()
            return cur.lastrowid  # AUTOINCREMENT rowid = sequence_number

    async def get_events(self, session_id: str, after_sequence: int = 0) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, event_json FROM events WHERE session_id=? AND id>? ORDER BY id ASC",
                (session_id, after_sequence),
            )
            rows = await cur.fetchall()
        result = []
        for row in rows:
            try:
                evt = json.loads(row["event_json"])
                evt["sequence_number"] = row["id"]
                result.append(evt)
            except json.JSONDecodeError:
                logger.warning("Corrupt event in store for session %s", session_id)
        return result

    async def log_llm_call(self, record: dict) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """INSERT INTO llm_calls
                   (session_id, agent_name, model, call_type, input_tokens, output_tokens,
                    latency_ms, success, error, fallback_used, response_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.get("session_id", ""),
                    record.get("agent_name"),
                    record.get("model"),
                    record.get("call_type"),
                    record.get("input_tokens", 0),
                    record.get("output_tokens", 0),
                    record.get("latency_ms", 0),
                    1 if record.get("success") else 0,
                    record.get("error"),
                    1 if record.get("fallback_used") else 0,
                    json.dumps(record.get("response_json") or {}, default=str),
                    record.get("created_at", time.time()),
                ),
            )
            await db.commit()

    async def get_llm_calls(self, session_id: str) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM llm_calls WHERE session_id=? ORDER BY created_at ASC",
                (session_id,),
            )
            rows = await cur.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["success"] = bool(d["success"])
            d["fallback_used"] = bool(d["fallback_used"])
            try:
                d["response_json"] = json.loads(d["response_json"] or "{}")
            except json.JSONDecodeError:
                d["response_json"] = {}
            result.append(d)
        return result

    async def delete_session(self, session_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM events WHERE session_id=?", (session_id,))
            await db.execute("DELETE FROM llm_calls WHERE session_id=?", (session_id,))
            await db.commit()


class RedisDiagnosticStore(DiagnosticStore):
    """Redis implementation. Activated via DIAGNOSTIC_STORE_BACKEND=redis."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._redis = None

    async def initialize(self) -> None:
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(self._url, decode_responses=True)

    async def append_event(self, session_id: str, event: dict) -> int:
        key = f"diag:events:{session_id}"
        serialized = json.dumps(event, default=str)
        await self._redis.rpush(key, serialized)
        seq = await self._redis.llen(key)
        return seq  # 1-based length = sequence_number

    async def get_events(self, session_id: str, after_sequence: int = 0) -> list[dict]:
        key = f"diag:events:{session_id}"
        raw = await self._redis.lrange(key, after_sequence, -1)
        result = []
        for i, item in enumerate(raw):
            try:
                evt = json.loads(item)
                evt["sequence_number"] = after_sequence + i + 1
                result.append(evt)
            except json.JSONDecodeError:
                pass
        return result

    async def log_llm_call(self, record: dict) -> None:
        key = f"diag:llm:{record.get('session_id', '')}"
        await self._redis.rpush(key, json.dumps(record, default=str))

    async def get_llm_calls(self, session_id: str) -> list[dict]:
        key = f"diag:llm:{session_id}"
        raw = await self._redis.lrange(key, 0, -1)
        result = []
        for item in raw:
            try:
                result.append(json.loads(item))
            except json.JSONDecodeError:
                pass
        return result

    async def delete_session(self, session_id: str) -> None:
        await self._redis.delete(
            f"diag:events:{session_id}",
            f"diag:llm:{session_id}",
        )


# Module-level singleton — initialized once at startup
_store: DiagnosticStore | None = None


def get_store() -> DiagnosticStore:
    """Return the configured store. Call initialize() before first use."""
    global _store
    if _store is None:
        backend = os.getenv("DIAGNOSTIC_STORE_BACKEND", "sqlite")
        if backend == "redis":
            _store = RedisDiagnosticStore(url=os.getenv("REDIS_URL", "redis://localhost:6379"))
        else:
            path = os.getenv("DIAGNOSTIC_DB_PATH", "data/diagnostics.db")
            _store = SQLiteDiagnosticStore(path=path)
    return _store

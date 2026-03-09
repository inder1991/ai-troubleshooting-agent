"""SQLite persistence for SNMP trap and syslog events."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "debugduck.db"


class EventStore:
    """SQLite store for trap and syslog events received by protocol collectors."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db = str(db_path or DEFAULT_DB)
        self._ensure_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ── Schema ──

    def _ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trap_events (
                    event_id   TEXT PRIMARY KEY,
                    device_ip  TEXT,
                    device_id  TEXT,
                    oid        TEXT,
                    value      TEXT,
                    severity   TEXT,
                    timestamp  REAL,
                    raw_json   TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS syslog_events (
                    event_id   TEXT PRIMARY KEY,
                    device_ip  TEXT,
                    device_id  TEXT,
                    facility   TEXT,
                    severity   TEXT,
                    hostname   TEXT,
                    app_name   TEXT,
                    message    TEXT,
                    timestamp  REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trap_device_id
                ON trap_events(device_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trap_timestamp
                ON trap_events(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trap_severity
                ON trap_events(severity)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_syslog_device_id
                ON syslog_events(device_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_syslog_timestamp
                ON syslog_events(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_syslog_severity
                ON syslog_events(severity)
            """)

    # ── Trap Inserts ──

    def insert_trap(self, event: dict[str, Any]) -> None:
        """Insert a single SNMP trap event."""
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trap_events
                    (event_id, device_ip, device_id, oid, value, severity, timestamp, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event["event_id"],
                event.get("device_ip"),
                event.get("device_id"),
                event.get("oid"),
                event.get("value"),
                event.get("severity"),
                event.get("timestamp", time.time()),
                json.dumps(event.get("raw", {})) if event.get("raw") else event.get("raw_json"),
            ))

    def insert_trap_batch(self, events: list[dict[str, Any]]) -> None:
        """Batch-insert SNMP trap events in a single transaction."""
        with self._conn() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO trap_events
                    (event_id, device_ip, device_id, oid, value, severity, timestamp, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    e["event_id"],
                    e.get("device_ip"),
                    e.get("device_id"),
                    e.get("oid"),
                    e.get("value"),
                    e.get("severity"),
                    e.get("timestamp", time.time()),
                    json.dumps(e.get("raw", {})) if e.get("raw") else e.get("raw_json"),
                )
                for e in events
            ])

    # ── Syslog Inserts ──

    def insert_syslog(self, event: dict[str, Any]) -> None:
        """Insert a single syslog event."""
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO syslog_events
                    (event_id, device_ip, device_id, facility, severity, hostname, app_name, message, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event["event_id"],
                event.get("device_ip"),
                event.get("device_id"),
                event.get("facility"),
                event.get("severity"),
                event.get("hostname"),
                event.get("app_name"),
                event.get("message"),
                event.get("timestamp", time.time()),
            ))

    def insert_syslog_batch(self, events: list[dict[str, Any]]) -> None:
        """Batch-insert syslog events in a single transaction."""
        with self._conn() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO syslog_events
                    (event_id, device_ip, device_id, facility, severity, hostname, app_name, message, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    e["event_id"],
                    e.get("device_ip"),
                    e.get("device_id"),
                    e.get("facility"),
                    e.get("severity"),
                    e.get("hostname"),
                    e.get("app_name"),
                    e.get("message"),
                    e.get("timestamp", time.time()),
                )
                for e in events
            ])

    # ── Trap Queries ──

    def query_traps(
        self,
        device_id: str | None = None,
        severity: str | None = None,
        oid: str | None = None,
        time_from: float | None = None,
        time_to: float | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query trap events with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []

        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if oid:
            clauses.append("oid = ?")
            params.append(oid)
        if time_from is not None:
            clauses.append("timestamp >= ?")
            params.append(time_from)
        if time_to is not None:
            clauses.append("timestamp <= ?")
            params.append(time_to)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(limit, 1000))
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM trap_events {where} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def query_syslog(
        self,
        device_id: str | None = None,
        severity: str | None = None,
        facility: str | None = None,
        search: str | None = None,
        time_from: float | None = None,
        time_to: float | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query syslog events with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []

        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if facility:
            clauses.append("facility = ?")
            params.append(facility)
        if search:
            clauses.append("message LIKE ?")
            params.append(f"%{search}%")
        if time_from is not None:
            clauses.append("timestamp >= ?")
            params.append(time_from)
        if time_to is not None:
            clauses.append("timestamp <= ?")
            params.append(time_to)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(limit, 1000))
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM syslog_events {where} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    # ── Summaries ──

    def trap_summary(
        self,
        time_from: float | None = None,
        time_to: float | None = None,
    ) -> dict[str, Any]:
        """Aggregate trap statistics: counts by severity and top OIDs."""
        clauses: list[str] = []
        params: list[Any] = []

        if time_from is not None:
            clauses.append("timestamp >= ?")
            params.append(time_from)
        if time_to is not None:
            clauses.append("timestamp <= ?")
            params.append(time_to)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._conn() as conn:
            severity_rows = conn.execute(
                f"SELECT severity, COUNT(*) as cnt FROM trap_events {where} GROUP BY severity",
                params,
            ).fetchall()

            oid_rows = conn.execute(
                f"SELECT oid, COUNT(*) as cnt FROM trap_events {where} GROUP BY oid ORDER BY cnt DESC LIMIT 20",
                params,
            ).fetchall()

        return {
            "counts_by_severity": {row["severity"]: row["cnt"] for row in severity_rows},
            "top_oids": [{"oid": row["oid"], "count": row["cnt"]} for row in oid_rows],
        }

    def syslog_summary(
        self,
        time_from: float | None = None,
        time_to: float | None = None,
    ) -> dict[str, Any]:
        """Aggregate syslog statistics: counts by severity and facility."""
        clauses: list[str] = []
        params: list[Any] = []

        if time_from is not None:
            clauses.append("timestamp >= ?")
            params.append(time_from)
        if time_to is not None:
            clauses.append("timestamp <= ?")
            params.append(time_to)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._conn() as conn:
            severity_rows = conn.execute(
                f"SELECT severity, COUNT(*) as cnt FROM syslog_events {where} GROUP BY severity",
                params,
            ).fetchall()

            facility_rows = conn.execute(
                f"SELECT facility, COUNT(*) as cnt FROM syslog_events {where} GROUP BY facility ORDER BY cnt DESC",
                params,
            ).fetchall()

        return {
            "counts_by_severity": {row["severity"]: row["cnt"] for row in severity_rows},
            "counts_by_facility": {row["facility"]: row["cnt"] for row in facility_rows},
        }

    # ── Maintenance ──

    def prune_old_events(self, days: int = 30) -> dict[str, int]:
        """Delete events older than N days. Returns count of deleted rows per table."""
        cutoff = time.time() - (days * 86400)

        with self._conn() as conn:
            trap_cur = conn.execute(
                "DELETE FROM trap_events WHERE timestamp < ?", (cutoff,)
            )
            syslog_cur = conn.execute(
                "DELETE FROM syslog_events WHERE timestamp < ?", (cutoff,)
            )

        return {
            "traps_deleted": trap_cur.rowcount,
            "syslog_deleted": syslog_cur.rowcount,
        }

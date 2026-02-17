"""
Audit logger for tracking credential and integration changes.

Stores audit events in SQLite and emits structured log output.
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("audit")

DEFAULT_DB_PATH = "./data/debugduck.db"


class AuditLogger:
    """Records audit events for integration/profile changes."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    def _ensure_tables(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT DEFAULT 'system',
                details TEXT
            )
        """)
        conn.commit()
        conn.close()

    def log(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        details: Optional[str] = None,
        actor: str = "system",
    ) -> str:
        """Record an audit event. Returns the audit log ID."""
        audit_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "INSERT INTO audit_logs (id, timestamp, entity_type, entity_id, action, actor, details) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (audit_id, ts, entity_type, entity_id, action, actor, details),
        )
        conn.commit()
        conn.close()

        # Also emit structured log
        logger.info(
            "Audit: %s %s %s",
            action,
            entity_type,
            entity_id,
            extra={
                "action": action,
                "extra": {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "actor": actor,
                    "details": details,
                },
            },
        )

        return audit_id

    def list_recent(
        self, limit: int = 50, entity_type: Optional[str] = None
    ) -> list[dict]:
        """Query recent audit logs with optional entity_type filter."""
        conn = sqlite3.connect(self._db_path)
        if entity_type:
            rows = conn.execute(
                "SELECT id, timestamp, entity_type, entity_id, action, actor, details "
                "FROM audit_logs WHERE entity_type = ? ORDER BY timestamp DESC LIMIT ?",
                (entity_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, timestamp, entity_type, entity_id, action, actor, details "
                "FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()

        return [
            {
                "id": r[0],
                "timestamp": r[1],
                "entity_type": r[2],
                "entity_id": r[3],
                "action": r[4],
                "actor": r[5],
                "details": r[6],
            }
            for r in rows
        ]

"""Configuration drift detection — backup configs, diff against baseline, alert on changes."""

from __future__ import annotations

import asyncio
import sqlite3
import time
import difflib
from pathlib import Path
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "config_drift.db"


class ConfigDriftEngine:
    """Detects configuration changes by comparing running configs against baselines."""

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS config_baselines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                config_text TEXT NOT NULL,
                captured_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cb_device ON config_baselines(device_id, captured_at);

            CREATE TABLE IF NOT EXISTS drift_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                diff_text TEXT NOT NULL,
                lines_changed INTEGER DEFAULT 0,
                detected_at REAL NOT NULL,
                acknowledged INTEGER DEFAULT 0,
                acknowledged_by TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_de_device ON drift_events(device_id, detected_at);
        """)
        conn.close()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def store_baseline(self, device_id: str, config_text: str) -> None:
        conn = self._get_conn()
        conn.execute("INSERT INTO config_baselines (device_id, config_text, captured_at) VALUES (?, ?, ?)",
                     (device_id, config_text, time.time()))
        conn.commit()
        conn.close()

    def get_latest_baseline(self, device_id: str) -> str | None:
        conn = self._get_conn()
        row = conn.execute("SELECT config_text FROM config_baselines WHERE device_id=? ORDER BY captured_at DESC LIMIT 1",
                          (device_id,)).fetchone()
        conn.close()
        return row[0] if row else None

    def detect_drift(self, device_id: str, current_config: str) -> dict | None:
        baseline = self.get_latest_baseline(device_id)
        if not baseline:
            self.store_baseline(device_id, current_config)
            return None

        diff = list(difflib.unified_diff(
            baseline.splitlines(keepends=True),
            current_config.splitlines(keepends=True),
            fromfile="baseline",
            tofile="current",
            lineterm=""
        ))

        if not diff:
            return None

        diff_text = "\n".join(diff)
        lines_changed = sum(1 for line in diff if line.startswith("+") or line.startswith("-"))

        conn = self._get_conn()
        conn.execute("INSERT INTO drift_events (device_id, diff_text, lines_changed, detected_at) VALUES (?, ?, ?, ?)",
                    (device_id, diff_text, lines_changed, time.time()))
        conn.commit()
        conn.close()

        logger.warning("Config drift detected on %s: %d lines changed", device_id, lines_changed)
        return {"device_id": device_id, "lines_changed": lines_changed, "diff": diff_text}

    def get_drift_events(self, device_id: str = "", limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        if device_id:
            rows = conn.execute("SELECT id, device_id, lines_changed, detected_at, acknowledged FROM drift_events WHERE device_id=? ORDER BY detected_at DESC LIMIT ?",
                               (device_id, limit)).fetchall()
        else:
            rows = conn.execute("SELECT id, device_id, lines_changed, detected_at, acknowledged FROM drift_events ORDER BY detected_at DESC LIMIT ?",
                               (limit,)).fetchall()
        conn.close()
        return [{"id": r[0], "device_id": r[1], "lines_changed": r[2], "detected_at": r[3], "acknowledged": bool(r[4])} for r in rows]

    def get_drift_detail(self, drift_id: int) -> dict | None:
        conn = self._get_conn()
        row = conn.execute("SELECT id, device_id, diff_text, lines_changed, detected_at FROM drift_events WHERE id=?", (drift_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "device_id": row[1], "diff": row[2], "lines_changed": row[3], "detected_at": row[4]}

    def acknowledge_drift(self, drift_id: int, user: str = "") -> None:
        conn = self._get_conn()
        conn.execute("UPDATE drift_events SET acknowledged=1, acknowledged_by=? WHERE id=?", (user, drift_id))
        conn.commit()
        conn.close()

    def set_new_baseline(self, device_id: str, config_text: str) -> None:
        self.store_baseline(device_id, config_text)
        logger.info("New baseline set for %s", device_id)

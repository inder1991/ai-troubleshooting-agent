"""SQLite time-series metrics store for device, interface, and probe metrics."""

from __future__ import annotations

import sqlite3
import time
import threading
from pathlib import Path
from typing import Any, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "metrics.db"


class SQLiteMetricsStore:
    """Thread-safe SQLite time-series metrics store.

    Stores device-level metrics (CPU, memory, sessions),
    interface-level metrics (bps, errors, utilization),
    and probe metrics (ping RTT, packet loss).

    Retention: 7 days default. Older data auto-pruned.
    """

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS device_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                device_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                unit TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_dm_device_ts ON device_metrics(device_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_dm_metric ON device_metrics(device_id, metric_name, timestamp);

            CREATE TABLE IF NOT EXISTS interface_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                device_id TEXT NOT NULL,
                interface_name TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                unit TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_im_device_iface_ts ON interface_metrics(device_id, interface_name, timestamp);

            CREATE TABLE IF NOT EXISTS probe_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                target_ip TEXT NOT NULL,
                probe_type TEXT NOT NULL DEFAULT 'icmp',
                latency_ms REAL DEFAULT 0,
                packet_loss_pct REAL DEFAULT 0,
                status TEXT DEFAULT 'ok'
            );
            CREATE INDEX IF NOT EXISTS idx_pm_target_ts ON probe_metrics(target_ip, timestamp);

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                device_id TEXT DEFAULT '',
                source_ip TEXT DEFAULT '',
                event_type TEXT NOT NULL DEFAULT 'info',
                severity TEXT DEFAULT 'info',
                message TEXT NOT NULL,
                raw_data TEXT DEFAULT '',
                acknowledged INTEGER DEFAULT 0,
                acknowledged_by TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_ev_device_ts ON events(device_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_ev_severity ON events(severity, timestamp);

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                device_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                threshold REAL NOT NULL,
                message TEXT DEFAULT '',
                acknowledged INTEGER DEFAULT 0,
                acknowledged_by TEXT DEFAULT '',
                resolved INTEGER DEFAULT 0,
                resolved_at REAL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_al_device ON alerts(device_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_al_active ON alerts(acknowledged, resolved);
        """)
        conn.close()
        logger.info("SQLite metrics store initialized at %s", self.db_path)

    def write_device_metric(self, device_id: str, metric_name: str, value: float, unit: str = "") -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO device_metrics (timestamp, device_id, metric_name, metric_value, unit) VALUES (?, ?, ?, ?, ?)",
            (time.time(), device_id, metric_name, float(value), unit)
        )
        conn.commit()

    def write_interface_metric(self, device_id: str, interface_name: str, metric_name: str, value: float, unit: str = "") -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO interface_metrics (timestamp, device_id, interface_name, metric_name, metric_value, unit) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), device_id, interface_name, metric_name, float(value), unit)
        )
        conn.commit()

    def write_probe_metric(self, target_ip: str, probe_type: str, latency_ms: float, packet_loss_pct: float, status: str = "ok") -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO probe_metrics (timestamp, target_ip, probe_type, latency_ms, packet_loss_pct, status) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), target_ip, probe_type, latency_ms, packet_loss_pct, status)
        )
        conn.commit()

    def write_event(self, device_id: str, source_ip: str, event_type: str, severity: str, message: str, raw_data: str = "") -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO events (timestamp, device_id, source_ip, event_type, severity, message, raw_data) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), device_id, source_ip, event_type, severity, message, raw_data)
        )
        conn.commit()
        return cursor.lastrowid

    def write_alert(self, device_id: str, rule_id: str, severity: str, metric_name: str, value: float, threshold: float, message: str = "") -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO alerts (timestamp, device_id, rule_id, severity, metric_name, metric_value, threshold, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), device_id, rule_id, severity, metric_name, value, threshold, message)
        )
        conn.commit()
        return cursor.lastrowid

    def query_device_metrics(self, device_id: str, metric_name: str, start_ts: float = 0, end_ts: float = 0, limit: int = 500) -> list[dict]:
        if end_ts == 0:
            end_ts = time.time()
        if start_ts == 0:
            start_ts = end_ts - 3600  # Default 1 hour
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT timestamp, metric_value, unit FROM device_metrics WHERE device_id=? AND metric_name=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp DESC LIMIT ?",
            (device_id, metric_name, start_ts, end_ts, limit)
        ).fetchall()
        return [{"timestamp": r[0], "value": r[1], "unit": r[2]} for r in rows]

    def query_interface_metrics(self, device_id: str, interface_name: str, metric_name: str, start_ts: float = 0, end_ts: float = 0, limit: int = 500) -> list[dict]:
        if end_ts == 0:
            end_ts = time.time()
        if start_ts == 0:
            start_ts = end_ts - 3600
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT timestamp, metric_value, unit FROM interface_metrics WHERE device_id=? AND interface_name=? AND metric_name=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp DESC LIMIT ?",
            (device_id, interface_name, metric_name, start_ts, end_ts, limit)
        ).fetchall()
        return [{"timestamp": r[0], "value": r[1], "unit": r[2]} for r in rows]

    def get_latest_device_metric(self, device_id: str, metric_name: str) -> float | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT metric_value FROM device_metrics WHERE device_id=? AND metric_name=? ORDER BY timestamp DESC LIMIT 1",
            (device_id, metric_name)
        ).fetchone()
        return row[0] if row else None

    def get_device_health_summary(self, device_id: str) -> dict:
        """Get latest CPU, memory, and interface summary."""
        cpu = self.get_latest_device_metric(device_id, "cpu_pct")
        memory = self.get_latest_device_metric(device_id, "memory_pct")
        return {
            "device_id": device_id,
            "cpu_pct": cpu,
            "memory_pct": memory,
            "last_polled": time.time(),
        }

    def get_active_alerts(self, device_id: str = "", severity: str = "", limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        query = "SELECT id, timestamp, device_id, rule_id, severity, metric_name, metric_value, threshold, message, acknowledged FROM alerts WHERE resolved=0"
        params: list = []
        if device_id:
            query += " AND device_id=?"
            params.append(device_id)
        if severity:
            query += " AND severity=?"
            params.append(severity)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [{"id": r[0], "timestamp": r[1], "device_id": r[2], "rule_id": r[3], "severity": r[4], "metric_name": r[5], "metric_value": r[6], "threshold": r[7], "message": r[8], "acknowledged": bool(r[9])} for r in rows]

    def get_active_alert_count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM alerts WHERE resolved=0 AND acknowledged=0").fetchone()
        return row[0] if row else 0

    def acknowledge_alert(self, alert_id: int, user: str = "") -> None:
        conn = self._get_conn()
        conn.execute("UPDATE alerts SET acknowledged=1, acknowledged_by=? WHERE id=?", (user, alert_id))
        conn.commit()

    def get_events(self, device_id: str = "", severity: str = "", limit: int = 100, start_ts: float = 0) -> list[dict]:
        conn = self._get_conn()
        query = "SELECT id, timestamp, device_id, source_ip, event_type, severity, message FROM events WHERE 1=1"
        params: list = []
        if device_id:
            query += " AND device_id=?"
            params.append(device_id)
        if severity:
            query += " AND severity=?"
            params.append(severity)
        if start_ts:
            query += " AND timestamp>=?"
            params.append(start_ts)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [{"id": r[0], "timestamp": r[1], "device_id": r[2], "source_ip": r[3], "event_type": r[4], "severity": r[5], "message": r[6]} for r in rows]

    def cleanup_old_metrics(self, retention_days: int = 7) -> int:
        cutoff = time.time() - (retention_days * 86400)
        conn = self._get_conn()
        deleted = 0
        for table in ["device_metrics", "interface_metrics", "probe_metrics"]:
            cursor = conn.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,))
            deleted += cursor.rowcount
        conn.commit()
        if deleted:
            logger.info("Cleaned up %d old metric rows (retention: %dd)", deleted, retention_days)
        return deleted

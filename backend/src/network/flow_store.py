"""Flow aggregation store — aggregates NetFlow/IPFIX records into queryable summaries."""

from __future__ import annotations

import sqlite3
import time
import threading
from pathlib import Path
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "flows.db"


class FlowStore:
    """SQLite-based flow aggregation store."""

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS flows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                src_ip TEXT NOT NULL,
                dst_ip TEXT NOT NULL,
                src_port INTEGER DEFAULT 0,
                dst_port INTEGER DEFAULT 0,
                protocol INTEGER DEFAULT 6,
                bytes_total INTEGER DEFAULT 0,
                packets_total INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                src_as INTEGER DEFAULT 0,
                dst_as INTEGER DEFAULT 0,
                application TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_fl_ts ON flows(timestamp);
            CREATE INDEX IF NOT EXISTS idx_fl_src ON flows(src_ip, timestamp);
            CREATE INDEX IF NOT EXISTS idx_fl_dst ON flows(dst_ip, timestamp);
        """)
        conn.close()

    def ingest_flow(self, flow: dict) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO flows (timestamp, src_ip, dst_ip, src_port, dst_port, protocol, bytes_total, packets_total, duration_ms, src_as, dst_as, application) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), flow.get("src_ip", ""), flow.get("dst_ip", ""), flow.get("src_port", 0), flow.get("dst_port", 0), flow.get("protocol", 6), flow.get("bytes", 0), flow.get("packets", 0), flow.get("duration_ms", 0), flow.get("src_as", 0), flow.get("dst_as", 0), flow.get("application", ""))
        )
        conn.commit()

    def get_top_talkers(self, time_range_seconds: int = 3600, limit: int = 20) -> list[dict]:
        cutoff = time.time() - time_range_seconds
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT src_ip, SUM(bytes_total) as total_bytes, COUNT(*) as flow_count FROM flows WHERE timestamp > ? GROUP BY src_ip ORDER BY total_bytes DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
        return [{"src_ip": r[0], "total_bytes": r[1], "flow_count": r[2]} for r in rows]

    def get_top_applications(self, time_range_seconds: int = 3600, limit: int = 20) -> list[dict]:
        cutoff = time.time() - time_range_seconds
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT dst_port, protocol, SUM(bytes_total) as total_bytes, COUNT(*) as flow_count FROM flows WHERE timestamp > ? GROUP BY dst_port, protocol ORDER BY total_bytes DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
        return [{"dst_port": r[0], "protocol": r[1], "total_bytes": r[2], "flow_count": r[3]} for r in rows]

    def get_conversations(self, time_range_seconds: int = 3600, limit: int = 20) -> list[dict]:
        cutoff = time.time() - time_range_seconds
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT src_ip, dst_ip, SUM(bytes_total) as total_bytes, COUNT(*) as flow_count FROM flows WHERE timestamp > ? GROUP BY src_ip, dst_ip ORDER BY total_bytes DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
        return [{"src_ip": r[0], "dst_ip": r[1], "total_bytes": r[2], "flow_count": r[3]} for r in rows]

    def get_protocol_breakdown(self, time_range_seconds: int = 3600) -> dict:
        cutoff = time.time() - time_range_seconds
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT protocol, SUM(bytes_total) as total_bytes FROM flows WHERE timestamp > ? GROUP BY protocol",
            (cutoff,)
        ).fetchall()
        proto_names = {6: "TCP", 17: "UDP", 1: "ICMP", 47: "GRE"}
        return {proto_names.get(r[0], str(r[0])): r[1] for r in rows}

    def get_volume_timeline(self, time_range_seconds: int = 3600, bucket_seconds: int = 300) -> list[dict]:
        cutoff = time.time() - time_range_seconds
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT CAST(timestamp / ? AS INTEGER) * ? as bucket, SUM(bytes_total) as total_bytes, COUNT(*) as flow_count FROM flows WHERE timestamp > ? GROUP BY bucket ORDER BY bucket",
            (bucket_seconds, bucket_seconds, cutoff)
        ).fetchall()
        return [{"timestamp": r[0], "bytes": r[1], "flows": r[2]} for r in rows]

    def cleanup(self, retention_hours: int = 24) -> int:
        cutoff = time.time() - (retention_hours * 3600)
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM flows WHERE timestamp < ?", (cutoff,))
        conn.commit()
        return cursor.rowcount

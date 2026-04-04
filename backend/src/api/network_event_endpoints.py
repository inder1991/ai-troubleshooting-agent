"""REST endpoints for syslog and SNMP trap events."""

from __future__ import annotations

import time
from fastapi import APIRouter, Query
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v4/events", tags=["events"])

_metrics_store = None   # SQLiteMetricsStore — general events table
_event_store = None     # collectors.event_store.EventStore — traps + syslog tables


def init_events(metrics_store, event_store):
    """Called from main.py startup to wire in storage backends."""
    global _metrics_store, _event_store
    _metrics_store = metrics_store
    _event_store = event_store


# ── General events (syslog + traps merged into SQLiteMetricsStore.events) ──

@router.get("")
async def get_events(
    device_id: Optional[str] = None,
    severity: Optional[str] = None,
    range: str = "1h",
    limit: int = Query(default=100, le=1000),
):
    """List events from the general events table (syslog + trap summaries)."""
    if not _metrics_store:
        return {"events": [], "total": 0}

    seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    start_ts = time.time() - seconds

    events = _metrics_store.get_events(
        device_id=device_id or "",
        severity=severity or "",
        limit=limit,
        start_ts=start_ts,
    )
    return {"events": events, "total": len(events)}


@router.get("/rate")
async def get_event_rate(range: str = "1h", interval: str = "5m"):
    """Event rate over time — bucketed for timeline chart."""
    if not _metrics_store:
        return {"buckets": []}

    seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    bucket_secs = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}.get(interval, 300)
    start_ts = time.time() - seconds

    conn = _metrics_store._get_conn()
    rows = conn.execute(
        "SELECT CAST((timestamp - ?) / ? AS INTEGER) AS bucket, COUNT(*) AS cnt "
        "FROM events WHERE timestamp >= ? GROUP BY bucket ORDER BY bucket",
        (start_ts, bucket_secs, start_ts),
    ).fetchall()

    now = time.time()
    buckets = [
        {
            "timestamp": start_ts + r[0] * bucket_secs,
            "count": r[1],
        }
        for r in rows
    ]
    return {"buckets": buckets, "bucket_seconds": bucket_secs}


@router.get("/unacknowledged/count")
async def get_unacknowledged_count():
    """Count of unacknowledged events — used for bell badge."""
    if not _metrics_store:
        return {"count": 0}
    conn = _metrics_store._get_conn()
    row = conn.execute(
        "SELECT COUNT(*) FROM events WHERE acknowledged=0"
    ).fetchone()
    return {"count": row[0] if row else 0}


@router.post("/{event_id}/acknowledge")
async def acknowledge_event(event_id: int, user: str = ""):
    """Acknowledge a general event."""
    if not _metrics_store:
        return {"ok": False, "error": "not_initialized"}
    conn = _metrics_store._get_conn()
    conn.execute(
        "UPDATE events SET acknowledged=1, acknowledged_by=? WHERE id=?",
        (user, event_id),
    )
    conn.connection.commit() if hasattr(conn, "connection") else conn.commit()
    return {"ok": True}


# ── SNMP Trap events (EventStore) ──

@router.get("/traps")
async def get_trap_events(
    device_id: Optional[str] = None,
    severity: Optional[str] = None,
    oid: Optional[str] = None,
    range: str = "1h",
    limit: int = Query(default=100, le=1000),
):
    """List SNMP trap events."""
    if not _event_store:
        return {"events": [], "total": 0}

    seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    time_from = time.time() - seconds

    events = _event_store.query_traps(
        device_id=device_id,
        severity=severity,
        oid=oid,
        time_from=time_from,
        limit=limit,
    )
    return {"events": events, "total": len(events)}


@router.get("/traps/summary")
async def get_trap_summary(range: str = "1h"):
    """Trap counts by severity and top OIDs."""
    if not _event_store:
        return {"counts_by_severity": {}, "top_oids": []}
    seconds = {"1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    time_from = time.time() - seconds
    return _event_store.trap_summary(time_from=time_from)


# ── Syslog events (EventStore) ──

@router.get("/syslog")
async def get_syslog_events(
    device_id: Optional[str] = None,
    severity: Optional[str] = None,
    facility: Optional[str] = None,
    search: Optional[str] = None,
    range: str = "1h",
    limit: int = Query(default=100, le=1000),
):
    """List syslog events."""
    if not _event_store:
        return {"events": [], "total": 0}

    seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    time_from = time.time() - seconds

    events = _event_store.query_syslog(
        device_id=device_id,
        severity=severity,
        facility=facility,
        search=search,
        time_from=time_from,
        limit=limit,
    )
    return {"events": events, "total": len(events)}


@router.get("/syslog/summary")
async def get_syslog_summary(range: str = "1h"):
    """Syslog counts by severity and facility."""
    if not _event_store:
        return {"counts_by_severity": {}, "counts_by_facility": {}}
    seconds = {"1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    time_from = time.time() - seconds
    return _event_store.syslog_summary(time_from=time_from)

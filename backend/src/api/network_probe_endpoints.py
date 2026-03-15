"""REST endpoints for ping probes."""

from __future__ import annotations
import time
from fastapi import APIRouter
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v4/probes", tags=["probes"])

_metrics_store = None
_ping_scheduler = None


def init_probes(metrics_store, ping_scheduler):
    global _metrics_store, _ping_scheduler
    _metrics_store = metrics_store
    _ping_scheduler = ping_scheduler


@router.get("")
async def list_probes():
    """List configured probe targets with latest status."""
    if not _ping_scheduler:
        return {"targets": []}
    results = []
    for target in _ping_scheduler._targets:
        ip = target.get("ip", "")
        # Get latest probe result
        if _metrics_store:
            conn = _metrics_store._get_conn()
            row = conn.execute(
                "SELECT latency_ms, packet_loss_pct, status, timestamp FROM probe_metrics WHERE target_ip=? ORDER BY timestamp DESC LIMIT 1",
                (ip,)
            ).fetchone()
            results.append({
                "ip": ip,
                "name": target.get("name", ""),
                "latency_ms": row[0] if row else None,
                "packet_loss_pct": row[1] if row else None,
                "status": row[2] if row else "unknown",
                "last_probed": row[3] if row else None,
            })
        else:
            results.append({"ip": ip, "name": target.get("name", ""), "status": "unknown"})
    return {"targets": results}


@router.get("/{target_ip}/history")
async def get_probe_history(target_ip: str, range: str = "1h"):
    """Get probe history (RTT + loss over time)."""
    if not _metrics_store:
        return {"data": []}
    seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    cutoff = time.time() - seconds
    conn = _metrics_store._get_conn()
    rows = conn.execute(
        "SELECT timestamp, latency_ms, packet_loss_pct, status FROM probe_metrics WHERE target_ip=? AND timestamp>? ORDER BY timestamp",
        (target_ip, cutoff)
    ).fetchall()
    return {"data": [{"timestamp": r[0], "latency_ms": r[1], "packet_loss_pct": r[2], "status": r[3]} for r in rows]}

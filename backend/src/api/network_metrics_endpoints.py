"""REST endpoints for network device metrics and monitoring."""

from __future__ import annotations

import time
from fastapi import APIRouter, Query
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v4/monitoring", tags=["monitoring"])

# These will be set on startup
_metrics_store = None
_snmp_scheduler = None
_sqlite_alert_engine = None


def init_monitoring(metrics_store, snmp_scheduler, alert_engine=None):
    """Initialize module-level references (called from main.py startup)."""
    global _metrics_store, _snmp_scheduler, _sqlite_alert_engine
    _metrics_store = metrics_store
    _snmp_scheduler = snmp_scheduler
    _sqlite_alert_engine = alert_engine


@router.get("/summary")
async def get_monitoring_summary():
    """Aggregate monitoring summary for Observatory overview."""
    if not _metrics_store:
        return {"status": "not_initialized", "devices_polled": 0}

    devices_polled = len(_snmp_scheduler._devices) if _snmp_scheduler else 0
    active_alerts = _metrics_store.get_active_alert_count()

    return {
        "status": "active" if devices_polled > 0 else "no_devices",
        "devices_polled": devices_polled,
        "active_alerts": active_alerts,
        "polling_interval_seconds": _snmp_scheduler.interval if _snmp_scheduler else 0,
    }


@router.get("/devices/health/batch")
async def get_batch_device_health():
    """Get health status for all polled devices — used by topology canvas for coloring."""
    if not _metrics_store or not _snmp_scheduler:
        return {"devices": {}}

    result = {}
    for device in _snmp_scheduler._devices:
        device_id = device.get("id", "")
        cpu = _metrics_store.get_latest_device_metric(device_id, "cpu_pct")
        memory = _metrics_store.get_latest_device_metric(device_id, "memory_pct")

        if cpu is None:
            status = "unknown"
        elif cpu > 95 or (memory and memory > 95):
            status = "critical"
        elif cpu > 80 or (memory and memory > 85):
            status = "degraded"
        else:
            status = "healthy"

        result[device_id] = {
            "status": status,
            "cpu_pct": round(cpu, 1) if cpu is not None else None,
            "memory_pct": round(memory, 1) if memory is not None else None,
        }

    return {"devices": result}


@router.get("/devices/{device_id}/health")
async def get_device_health(device_id: str):
    """Get latest health summary for a device."""
    if not _metrics_store:
        return {"error": "Metrics store not initialized"}
    return _metrics_store.get_device_health_summary(device_id)


@router.get("/devices/{device_id}/metrics")
async def get_device_metrics(
    device_id: str,
    metric: str = "cpu_pct",
    range: str = "1h",
):
    """Get time-series metrics for a device."""
    if not _metrics_store:
        return {"data": []}

    range_seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}.get(range, 3600)
    end_ts = time.time()
    start_ts = end_ts - range_seconds

    data = _metrics_store.query_device_metrics(device_id, metric, start_ts, end_ts)
    return {"device_id": device_id, "metric": metric, "range": range, "data": data}


@router.get("/devices/{device_id}/interfaces/{interface_name}/metrics")
async def get_interface_metrics(
    device_id: str,
    interface_name: str,
    metric: str = "bps_in",
    range: str = "1h",
):
    """Get time-series metrics for a device interface."""
    if not _metrics_store:
        return {"data": []}

    range_seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    end_ts = time.time()
    start_ts = end_ts - range_seconds

    data = _metrics_store.query_interface_metrics(device_id, interface_name, metric, start_ts, end_ts)
    return {"device_id": device_id, "interface": interface_name, "metric": metric, "data": data}


@router.get("/alerts")
async def get_alerts(
    device_id: str = "",
    severity: str = "",
    limit: int = 100,
):
    """Get active alerts."""
    if not _metrics_store:
        return {"alerts": [], "total": 0}
    alerts = _metrics_store.get_active_alerts(device_id, severity, limit)
    return {"alerts": alerts, "total": len(alerts)}


@router.get("/alerts/active/count")
async def get_active_alert_count():
    """Get count of unacknowledged alerts (for notification badge)."""
    if not _metrics_store:
        return {"count": 0}
    return {"count": _metrics_store.get_active_alert_count()}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, user: str = "operator"):
    """Acknowledge an alert."""
    if not _metrics_store:
        return {"error": "not initialized"}
    _metrics_store.acknowledge_alert(alert_id, user)
    return {"status": "acknowledged"}


@router.get("/events")
async def get_events(
    device_id: str = "",
    severity: str = "",
    limit: int = 100,
):
    """Get syslog/trap events."""
    if not _metrics_store:
        return {"events": [], "total": 0}
    events = _metrics_store.get_events(device_id, severity, limit)
    return {"events": events, "total": len(events)}


# ── Alert Rule CRUD (SQLite Alert Engine) ──


@router.get("/alert-rules")
async def get_alert_rules():
    """Get all configured alert threshold rules."""
    if not _sqlite_alert_engine:
        return {"rules": []}
    return {"rules": _sqlite_alert_engine.get_rules()}


@router.post("/alert-rules")
async def create_alert_rule(rule: dict):
    """Add a new alert threshold rule."""
    if not _sqlite_alert_engine:
        return {"error": "Alert engine not initialized"}
    required = {"id", "metric", "operator", "threshold", "severity", "message"}
    missing = required - set(rule.keys())
    if missing:
        return {"error": f"Missing required fields: {missing}"}
    _sqlite_alert_engine.add_rule(rule)
    return {"status": "created", "rule_id": rule["id"]}


@router.delete("/alert-rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Remove an alert threshold rule."""
    if not _sqlite_alert_engine:
        return {"error": "Alert engine not initialized"}
    _sqlite_alert_engine.remove_rule(rule_id)
    return {"status": "deleted", "rule_id": rule_id}

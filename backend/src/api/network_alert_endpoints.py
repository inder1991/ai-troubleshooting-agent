"""REST endpoints for alert management and threshold rules."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v4/alerts", tags=["alerts"])

_metrics_store = None     # SQLiteMetricsStore
_alert_engine = None      # SQLiteAlertEngine


def init_alerts(metrics_store, alert_engine):
    """Called from main.py startup to wire in storage + engine."""
    global _metrics_store, _alert_engine
    _metrics_store = metrics_store
    _alert_engine = alert_engine


# ── Alert queries ──

@router.get("")
async def get_alerts(
    device_id: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
):
    """List active (unresolved) alerts."""
    if not _metrics_store:
        return {"alerts": [], "total": 0}
    alerts = _metrics_store.get_active_alerts(
        device_id=device_id or "",
        severity=severity or "",
        limit=limit,
    )
    return {"alerts": alerts, "total": len(alerts)}


@router.get("/active/count")
async def get_active_alert_count():
    """Count of unacknowledged active alerts — for notification badge."""
    if not _metrics_store:
        return {"count": 0}
    return {"count": _metrics_store.get_active_alert_count()}


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, user: str = ""):
    """Acknowledge an alert by ID."""
    if not _metrics_store:
        raise HTTPException(status_code=503, detail="metrics store not initialized")
    _metrics_store.acknowledge_alert(alert_id, user)
    return {"ok": True, "alert_id": alert_id}


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: int):
    """Mark an alert as resolved."""
    if not _metrics_store:
        raise HTTPException(status_code=503, detail="metrics store not initialized")
    import time
    conn = _metrics_store._get_conn()
    conn.execute(
        "UPDATE alerts SET resolved=1, resolved_at=? WHERE id=?",
        (time.time(), alert_id),
    )
    conn.commit()
    return {"ok": True, "alert_id": alert_id}


# ── Alert rule management ──

class AlertRule(BaseModel):
    id: str
    metric: str
    operator: str       # >, <, >=, <=, ==, !=
    threshold: float
    severity: str       # warning | critical
    message: str = ""


@router.get("/rules")
async def get_alert_rules():
    """List all configured threshold rules."""
    if not _alert_engine:
        return {"rules": []}
    return {"rules": _alert_engine.get_rules()}


@router.post("/rules")
async def create_alert_rule(rule: AlertRule):
    """Add a custom threshold rule."""
    if not _alert_engine:
        raise HTTPException(status_code=503, detail="alert engine not initialized")

    # Check for duplicate ID
    existing_ids = {r["id"] for r in _alert_engine.get_rules()}
    if rule.id in existing_ids:
        raise HTTPException(status_code=409, detail=f"Rule '{rule.id}' already exists")

    _alert_engine.add_rule(rule.model_dump())
    logger.info("Alert rule added: %s", rule.id)
    return {"ok": True, "rule": rule.model_dump()}


@router.put("/rules/{rule_id}")
async def update_alert_rule(rule_id: str, rule: AlertRule):
    """Replace an existing threshold rule."""
    if not _alert_engine:
        raise HTTPException(status_code=503, detail="alert engine not initialized")

    existing_ids = {r["id"] for r in _alert_engine.get_rules()}
    if rule_id not in existing_ids:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

    _alert_engine.remove_rule(rule_id)
    updated = rule.model_dump()
    updated["id"] = rule_id
    _alert_engine.add_rule(updated)
    logger.info("Alert rule updated: %s", rule_id)
    return {"ok": True, "rule": updated}


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Remove a threshold rule."""
    if not _alert_engine:
        raise HTTPException(status_code=503, detail="alert engine not initialized")

    existing_ids = {r["id"] for r in _alert_engine.get_rules()}
    if rule_id not in existing_ids:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

    _alert_engine.remove_rule(rule_id)
    logger.info("Alert rule removed: %s", rule_id)
    return {"ok": True, "rule_id": rule_id}

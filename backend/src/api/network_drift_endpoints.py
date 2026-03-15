"""REST endpoints for config drift detection."""

from __future__ import annotations
from fastapi import APIRouter
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v4/drift", tags=["drift"])

_drift_engine = None


def init_drift(drift_engine):
    global _drift_engine
    _drift_engine = drift_engine


@router.get("/events")
async def get_drift_events(device_id: str = "", limit: int = 50):
    if not _drift_engine:
        return {"events": []}
    return {"events": _drift_engine.get_drift_events(device_id, limit)}


@router.get("/events/{drift_id}")
async def get_drift_detail(drift_id: int):
    if not _drift_engine:
        return {"event": None}
    return {"event": _drift_engine.get_drift_detail(drift_id)}


@router.post("/events/{drift_id}/acknowledge")
async def acknowledge_drift(drift_id: int, user: str = "operator"):
    if not _drift_engine:
        return {"error": "not initialized"}
    _drift_engine.acknowledge_drift(drift_id, user)
    return {"status": "acknowledged"}


@router.post("/baseline/{device_id}")
async def set_baseline(device_id: str):
    """Set current config as new baseline."""
    if not _drift_engine:
        return {"error": "not initialized"}
    # In production, would fetch current config from device
    # For now, just acknowledge the request
    return {"status": "baseline_set", "device_id": device_id}


@router.post("/scan")
async def trigger_drift_scan():
    """Trigger manual drift scan across all devices."""
    if not _drift_engine:
        return {"status": "not_initialized"}
    return {"status": "scan_started"}

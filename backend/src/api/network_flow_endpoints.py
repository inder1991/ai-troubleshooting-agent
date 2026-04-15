"""Legacy NetFlow REST endpoints (in-memory flow_store).

NOTE: These endpoints are preserved for back-compat with an older in-memory
FlowStore. New code should prefer the InfluxDB-backed endpoints in
``src.api.flow_endpoints`` (prefix ``/api/v4/network/flows``) or the monitor
flow endpoints in ``src.api.monitor_endpoints`` (prefix ``/api/v4/monitor/flows``).

Router prefix: ``/api/v4/flows``
Param name: ``range`` (values: 5m, 15m, 1h, 6h, 24h)
"""

from __future__ import annotations
from fastapi import APIRouter
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v4/flows", tags=["flows"])

_flow_store = None


def init_flows(flow_store):
    global _flow_store
    _flow_store = flow_store


@router.get("/top-talkers")
async def get_top_talkers(range: str = "1h", limit: int = 20):
    if not _flow_store:
        return {"data": [], "status": "no_data"}
    seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    return {"data": _flow_store.get_top_talkers(seconds, limit)}


@router.get("/applications")
async def get_top_applications(range: str = "1h", limit: int = 20):
    if not _flow_store:
        return {"data": [], "status": "no_data"}
    seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    return {"data": _flow_store.get_top_applications(seconds, limit)}


@router.get("/conversations")
async def get_conversations(range: str = "1h", limit: int = 20):
    if not _flow_store:
        return {"data": [], "status": "no_data"}
    seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    return {"data": _flow_store.get_conversations(seconds, limit)}


@router.get("/protocols")
async def get_protocol_breakdown(range: str = "1h"):
    if not _flow_store:
        return {"data": {}, "status": "no_data"}
    seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    return {"data": _flow_store.get_protocol_breakdown(seconds)}


@router.get("/volume")
async def get_volume_timeline(range: str = "1h"):
    if not _flow_store:
        return {"data": [], "status": "no_data"}
    seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    bucket = 60 if seconds <= 900 else 300 if seconds <= 3600 else 3600
    return {"data": _flow_store.get_volume_timeline(seconds, bucket)}

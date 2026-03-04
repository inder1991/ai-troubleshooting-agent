"""FastAPI router for Network Observatory — /api/v4/network/monitor."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Interface
from src.utils.logger import get_logger

logger = get_logger(__name__)

monitor_router = APIRouter(prefix="/api/v4/network/monitor", tags=["observatory"])

# Singletons — injected from main.py startup
_monitor = None
_topology_store = None
_knowledge_graph = None


def _get_monitor():
    return _monitor


def _get_topology_store():
    return _topology_store


def _get_knowledge_graph():
    return _knowledge_graph


class PromoteRequest(BaseModel):
    name: str
    device_type: str = "HOST"


@monitor_router.get("/snapshot")
async def get_snapshot():
    """Current state for the observatory dashboard."""
    mon = _get_monitor()
    if not mon:
        return {"devices": [], "links": [], "drifts": [], "candidates": []}
    return mon.get_snapshot()


@monitor_router.get("/drift")
async def list_drift_events():
    """List all active drift events."""
    store = _get_topology_store()
    return {"drifts": store.list_active_drift_events()}


@monitor_router.get("/device/{device_id}/history")
async def device_history(device_id: str, period: str = "24h"):
    """Latency/status history for a specific device."""
    store = _get_topology_store()
    period_map = {"1h": 1 / 24, "24h": 1, "7d": 7}
    days = period_map.get(period, 1)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    latency = store.query_metric_history("device", device_id, "latency_ms", since)
    packet_loss = store.query_metric_history("device", device_id, "packet_loss", since)
    return {
        "device_id": device_id,
        "period": period,
        "history": latency,
        "packet_loss_history": packet_loss,
    }


@monitor_router.post("/discover/{ip}/promote")
async def promote_discovery(ip: str, req: PromoteRequest):
    """Promote a discovered IP to a KG device."""
    store = _get_topology_store()
    kg = _get_knowledge_graph()

    candidates = store.list_discovery_candidates()
    candidate = next((c for c in candidates if c["ip"] == ip), None)
    if not candidate:
        raise HTTPException(404, f"No discovery candidate for IP {ip}")

    try:
        dt = DeviceType[req.device_type.upper()]
    except KeyError:
        dt = DeviceType.HOST

    device_id = f"device-discovered-{ip.replace('.', '-').replace(':', '-')}"
    device = Device(
        id=device_id,
        name=req.name,
        device_type=dt,
        management_ip=ip,
    )
    kg.add_device(device)

    # Create interface for the discovered IP
    iface = Interface(
        id=f"iface-{device_id}-discovered",
        device_id=device_id,
        name="discovered",
        ip=ip,
    )
    store.add_interface(iface)

    store.promote_candidate(ip, device_id)

    return {"status": "promoted", "device_id": device_id, "ip": ip}


@monitor_router.post("/discover/{ip}/dismiss")
async def dismiss_discovery(ip: str):
    """Dismiss a discovery candidate."""
    store = _get_topology_store()
    store.dismiss_candidate(ip)
    return {"status": "dismissed", "ip": ip}

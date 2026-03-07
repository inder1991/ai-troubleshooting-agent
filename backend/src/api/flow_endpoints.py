"""Flow analytics REST endpoints."""
from __future__ import annotations
from fastapi import APIRouter

flow_router = APIRouter(prefix="/api/v4/network/flows", tags=["flows"])

_metrics_store = None
_flow_receiver = None


def init_flow_endpoints(metrics_store, flow_receiver=None):
    global _metrics_store, _flow_receiver
    _metrics_store = metrics_store
    _flow_receiver = flow_receiver


@flow_router.get("/top-talkers")
async def top_talkers(window: str = "5m", limit: int = 20):
    if not _metrics_store:
        return []
    return await _metrics_store.query_top_talkers(window=window, limit=limit)


@flow_router.get("/traffic-matrix")
async def traffic_matrix(window: str = "15m"):
    if not _metrics_store:
        return []
    return await _metrics_store.query_traffic_matrix(window=window)


@flow_router.get("/protocol-breakdown")
async def protocol_breakdown(window: str = "1h"):
    if not _metrics_store:
        return []
    return await _metrics_store.query_protocol_breakdown(window=window)


@flow_router.get("/status")
def flow_status():
    return {
        "enabled": _flow_receiver is not None,
        "buffer_size": len(_flow_receiver.aggregator._buffer) if _flow_receiver else 0,
    }

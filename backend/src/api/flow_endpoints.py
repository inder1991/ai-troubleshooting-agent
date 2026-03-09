"""Flow analytics REST endpoints."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from src.network.asn_registry import lookup_asn as _asn_lookup

flow_router = APIRouter(prefix="/api/v4/network/flows", tags=["flows"])

_metrics_store = None
_flow_receiver = None

_WINDOW_PATTERN = re.compile(r"^\d+[smhd]$")


def _validate_window(window: str) -> str:
    """Validate that window matches the pattern: digits followed by s/m/h/d."""
    if not _WINDOW_PATTERN.match(window):
        raise HTTPException(
            422,
            f"Invalid window format: '{window}'. Must match pattern <number><s|m|h|d> (e.g. '5m', '1h').",
        )
    return window


def init_flow_endpoints(metrics_store, flow_receiver=None):
    global _metrics_store, _flow_receiver
    _metrics_store = metrics_store
    _flow_receiver = flow_receiver


@flow_router.get("/top-talkers")
async def top_talkers(window: str = "5m", limit: int = 20):
    _validate_window(window)
    if not _metrics_store:
        return []
    return await _metrics_store.query_top_talkers(window=window, limit=limit)


@flow_router.get("/traffic-matrix")
async def traffic_matrix(window: str = "15m"):
    _validate_window(window)
    if not _metrics_store:
        return []
    return await _metrics_store.query_traffic_matrix(window=window)


@flow_router.get("/protocol-breakdown")
async def protocol_breakdown(window: str = "1h"):
    _validate_window(window)
    if not _metrics_store:
        return []
    return await _metrics_store.query_protocol_breakdown(window=window)


@flow_router.get("/conversations")
async def flow_conversations(window: str = "5m", limit: int = 50):
    _validate_window(window)
    if _metrics_store:
        try:
            result = await _metrics_store.query_conversations(window=window, limit=limit)
            if result:
                return result
        except Exception:
            pass
    # Fallback to in-memory aggregator data
    if _flow_receiver:
        return _flow_receiver.aggregator.get_conversations(limit=limit)
    return []


@flow_router.get("/applications")
async def flow_applications(window: str = "1h", limit: int = 30):
    _validate_window(window)
    if _metrics_store:
        try:
            result = await _metrics_store.query_applications(window=window, limit=limit)
            if result:
                return result
        except Exception:
            pass
    # Fallback to in-memory aggregator data
    if _flow_receiver:
        return _flow_receiver.aggregator.get_applications(limit=limit)
    return []


@flow_router.get("/asn")
async def flow_asn(window: str = "1h", limit: int = 30):
    _validate_window(window)
    if _metrics_store:
        try:
            result = await _metrics_store.query_asn_breakdown(window=window, limit=limit)
            if result:
                return result
        except Exception:
            pass
    # Fallback to in-memory aggregator data
    if _flow_receiver:
        return _flow_receiver.aggregator.get_asn_breakdown(limit=limit)
    return []


@flow_router.get("/volume-timeline")
async def flow_volume_timeline(window: str = "1h", interval: str = "1m"):
    _validate_window(window)
    _validate_window(interval)
    if _metrics_store:
        try:
            return await _metrics_store.query_flow_volume_timeline(
                window=window, interval=interval,
            )
        except Exception:
            pass
    return []


@flow_router.get("/status")
def flow_status():
    return {
        "enabled": _flow_receiver is not None,
        "buffer_size": len(_flow_receiver.aggregator._buffer) if _flow_receiver else 0,
    }


@flow_router.get("/asn/lookup")
async def asn_lookup(asn: int):
    """Look up an ASN number and return its name and country."""
    result = _asn_lookup(asn)
    if result is None:
        raise HTTPException(404, f"ASN {asn} not found in registry")
    return {"asn": asn, **result}

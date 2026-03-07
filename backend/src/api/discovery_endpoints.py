"""FastAPI router for network discovery — /api/v4/network/discovery."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.utils.logger import get_logger

logger = get_logger(__name__)

discovery_router = APIRouter(prefix="/api/v4/network/discovery", tags=["discovery"])

# Singletons — injected from main.py startup
_topology_store = None
_discovery_engine = None


def init_discovery_endpoints(topology_store, discovery_engine=None):
    """Called from main.py startup to inject dependencies."""
    global _topology_store, _discovery_engine
    _topology_store = topology_store
    _discovery_engine = discovery_engine


def _get_topology_store():
    return _topology_store


def _get_discovery_engine():
    return _discovery_engine


# ── Request models ──


class ReverseDnsRequest(BaseModel):
    ip: str


# ── Endpoints ──


@discovery_router.get("/candidates")
async def list_candidates():
    """List all undismissed, unpromoted discovery candidates."""
    store = _get_topology_store()
    if not store:
        raise HTTPException(503, "Store not initialized")
    candidates = store.list_discovery_candidates()
    return {"candidates": candidates}


@discovery_router.post("/scan")
async def trigger_scan():
    """Trigger a subnet probe scan via the discovery engine.

    Returns 503 if the discovery engine was not initialized.
    """
    engine = _get_discovery_engine()
    if not engine:
        raise HTTPException(503, "Discovery engine not available")
    try:
        new_candidates = await engine.probe_known_subnets()
    except Exception as exc:
        logger.error("Discovery scan failed: %s", exc)
        raise HTTPException(500, f"Scan failed: {exc}")

    # Persist any new candidates
    store = _get_topology_store()
    if store:
        for c in new_candidates:
            store.upsert_discovery_candidate(
                ip=c["ip"],
                mac=c.get("mac", ""),
                hostname=c.get("hostname", ""),
                discovered_via=c.get("discovered_via", "probe"),
                source_device_id=c.get("source_device_id", ""),
            )

    return {"status": "completed", "new_candidates": new_candidates}


@discovery_router.post("/reverse-dns")
async def reverse_dns(req: ReverseDnsRequest):
    """Resolve a hostname for the given IP via the discovery engine.

    Returns 503 if the discovery engine was not initialized.
    """
    engine = _get_discovery_engine()
    if not engine:
        raise HTTPException(503, "Discovery engine not available")
    try:
        hostname = await engine.reverse_dns(req.ip)
    except Exception as exc:
        logger.error("Reverse DNS failed for %s: %s", req.ip, exc)
        raise HTTPException(500, f"Reverse DNS lookup failed: {exc}")

    return {"ip": req.ip, "hostname": hostname}

"""FastAPI router for network path troubleshooting — /api/v4/network."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File

from src.api.network_models import (
    DiagnoseRequest,
    DiagnoseResponse,
    TopologySaveRequest,
)
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Flow, DiagnosisStatus
from src.network.ipam_ingestion import parse_ipam_csv
from src.network.adapters.base import FirewallAdapter
from src.agents.network.graph import build_network_diagnostic_graph
from src.utils.logger import get_logger

logger = get_logger(__name__)

network_router = APIRouter(prefix="/api/v4/network", tags=["network"])

# ---------------------------------------------------------------------------
# Shared singletons (initialised lazily on first request)
# ---------------------------------------------------------------------------

_topology_store: TopologyStore | None = None
_knowledge_graph: NetworkKnowledgeGraph | None = None
_firewall_adapters: Dict[str, FirewallAdapter] = {}
_network_sessions: Dict[str, Dict[str, Any]] = {}


def _get_topology_store() -> TopologyStore:
    global _topology_store
    if _topology_store is None:
        _topology_store = TopologyStore()
    return _topology_store


def _get_knowledge_graph() -> NetworkKnowledgeGraph:
    global _knowledge_graph
    if _knowledge_graph is None:
        store = _get_topology_store()
        _knowledge_graph = NetworkKnowledgeGraph(store)
        _knowledge_graph.load_from_store()
    return _knowledge_graph


def _get_adapters() -> Dict[str, FirewallAdapter]:
    return _firewall_adapters


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------


async def _run_network_diagnosis(
    session_id: str, flow_id: str, graph, initial_state: dict
):
    try:
        _network_sessions[session_id]["phase"] = "running"
        result = await graph.ainvoke(initial_state)
        _network_sessions[session_id]["state"] = result
        _network_sessions[session_id]["phase"] = "complete"
    except Exception as e:
        logger.error("Network diagnosis failed", extra={"session_id": session_id, "error": str(e)})
        _network_sessions[session_id]["error"] = str(e)
        _network_sessions[session_id]["phase"] = "error"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@network_router.post("/diagnose", response_model=DiagnoseResponse)
async def diagnose(req: DiagnoseRequest, background_tasks: BackgroundTasks):
    """Start a network path diagnosis. Idempotent within 60 s window."""
    store = _get_topology_store()

    # Idempotent check — return existing flow if same params within 60 s
    recent = store.find_recent_flow(req.src_ip, req.dst_ip, req.port, within_seconds=60)
    if recent and recent.session_id:
        if recent.session_id in _network_sessions:
            return DiagnoseResponse(
                session_id=recent.session_id,
                flow_id=recent.id,
                status=_network_sessions[recent.session_id].get("phase", "running"),
                message="Existing diagnosis in progress",
            )

    session_id = req.session_id or str(uuid.uuid4())
    flow_id = str(uuid.uuid4())

    # Persist flow
    flow = Flow(
        id=flow_id,
        src_ip=req.src_ip,
        dst_ip=req.dst_ip,
        port=req.port,
        protocol=req.protocol,
        timestamp=datetime.now(timezone.utc).isoformat(),
        diagnosis_status=DiagnosisStatus.RUNNING,
        session_id=session_id,
    )
    store.add_flow(flow)

    # Build graph
    kg = _get_knowledge_graph()
    adapters = _get_adapters()
    compiled_graph = build_network_diagnostic_graph(kg, adapters)

    initial_state: dict = {
        "flow_id": flow_id,
        "src_ip": req.src_ip,
        "dst_ip": req.dst_ip,
        "port": req.port,
        "protocol": req.protocol,
        "session_id": session_id,
    }

    _network_sessions[session_id] = {
        "flow_id": flow_id,
        "phase": "queued",
        "state": initial_state,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    background_tasks.add_task(_run_network_diagnosis, session_id, flow_id, compiled_graph, initial_state)

    return DiagnoseResponse(
        session_id=session_id,
        flow_id=flow_id,
        status="queued",
        message="Network diagnosis started",
    )


@network_router.get("/session/{session_id}/findings")
async def get_findings(session_id: str):
    """Get diagnosis results from in-memory session state."""
    session = _network_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "flow_id": session.get("flow_id"),
        "phase": session.get("phase"),
        "error": session.get("error"),
        "state": session.get("state", {}),
    }


@network_router.post("/topology/save")
async def topology_save(req: TopologySaveRequest):
    """Save diagram JSON snapshot."""
    store = _get_topology_store()
    snap_id = store.save_diagram_snapshot(req.diagram_json, req.description)
    return {"snapshot_id": snap_id, "status": "saved"}


@network_router.get("/topology/load")
async def topology_load():
    """Load the latest diagram snapshot."""
    store = _get_topology_store()
    snapshot = store.load_diagram_snapshot()
    if not snapshot:
        return {"snapshot": None, "message": "No diagrams saved yet"}
    return {"snapshot": snapshot}


@network_router.post("/ipam/upload")
async def ipam_upload(file: UploadFile = File(...)):
    """Accept CSV file upload, parse IPAM data."""
    store = _get_topology_store()
    content = (await file.read()).decode("utf-8")
    stats = parse_ipam_csv(content, store)

    # Reload knowledge graph after IPAM import
    kg = _get_knowledge_graph()
    kg.load_from_store()

    return {"status": "imported", "stats": stats}


@network_router.get("/ipam/subnets")
async def ipam_subnets():
    """List all subnets from topology store."""
    store = _get_topology_store()
    subnets = store.list_subnets()
    return {"subnets": [s.model_dump() for s in subnets]}


@network_router.get("/ipam/devices")
async def ipam_devices():
    """List all devices from topology store."""
    store = _get_topology_store()
    devices = store.list_devices()
    return {"devices": [d.model_dump() for d in devices]}


@network_router.get("/adapters/status")
async def adapters_status():
    """Return health status for all configured adapters."""
    adapters = _get_adapters()
    results = []
    for device_id, adapter in adapters.items():
        health = await adapter.health_check()
        results.append({
            "device_id": device_id,
            "vendor": health.vendor.value,
            "status": health.status.value,
            "message": health.message,
            "snapshot_age_seconds": health.snapshot_age_seconds,
            "last_refresh": health.last_refresh,
        })
    return {"adapters": results}


@network_router.post("/adapters/{vendor}/refresh")
async def adapter_refresh(vendor: str):
    """Force refresh adapter snapshot for a vendor."""
    adapters = _get_adapters()
    # Find adapter by vendor
    target = None
    target_id = None
    for device_id, adapter in adapters.items():
        if adapter.vendor.value == vendor:
            target = adapter
            target_id = device_id
            break
    if not target:
        raise HTTPException(status_code=404, detail=f"No adapter configured for vendor: {vendor}")
    await target.refresh_snapshot()
    return {"status": "refreshed", "device_id": target_id, "vendor": vendor}


@network_router.get("/flows")
async def list_flows():
    """List past diagnosis flows."""
    store = _get_topology_store()
    flows = store.list_flows()
    return {"flows": [f.model_dump() for f in flows]}


@network_router.get("/flows/{flow_id}")
async def get_flow(flow_id: str):
    """Get specific flow details."""
    store = _get_topology_store()
    flow = store.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"flow": flow.model_dump()}

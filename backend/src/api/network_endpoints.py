"""FastAPI router for network path troubleshooting — /api/v4/network."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File

from src.api.network_models import (
    AdapterConfigureRequest,
    DiagnoseRequest,
    DiagnoseResponse,
    TopologySaveRequest,
)
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Flow, DiagnosisStatus
from src.network.ipam_ingestion import parse_ipam_csv, parse_ipam_excel
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

# Cap on stored sessions to prevent unbounded memory growth
_MAX_SESSIONS = 200


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
    store = _get_topology_store()
    try:
        _network_sessions[session_id]["phase"] = "running"
        result = await graph.ainvoke(initial_state)
        _network_sessions[session_id]["state"] = result
        # Writeback discovered hops to KG
        kg = _get_knowledge_graph()
        trace_hops = result.get("trace_hops", []) if isinstance(result, dict) else []
        if trace_hops:
            kg.writeback_discovered_hops(trace_hops)
        # Boost confidence on verified edges
        final_path = result.get("final_path", {}) if isinstance(result, dict) else {}
        hops = final_path.get("hops", [])
        for i in range(len(hops) - 1):
            kg.boost_edge_confidence(hops[i], hops[i + 1])
        _network_sessions[session_id]["phase"] = "complete"
        # Update flow status in SQLite
        confidence = result.get("confidence", 0.0) if isinstance(result, dict) else 0.0
        store.update_flow_status(flow_id, "complete", confidence)
    except Exception as e:
        logger.error("Network diagnosis failed", extra={"session_id": session_id, "error": str(e)})
        _network_sessions[session_id]["error"] = str(e)
        _network_sessions[session_id]["phase"] = "error"
        store.update_flow_status(flow_id, "error", 0.0)
    finally:
        # Evict oldest sessions if we exceed the cap
        if len(_network_sessions) > _MAX_SESSIONS:
            # Remove oldest completed/error sessions first
            to_remove = []
            for sid, sess in _network_sessions.items():
                if sess.get("phase") in ("complete", "error") and sid != session_id:
                    to_remove.append(sid)
            for sid in to_remove[:len(_network_sessions) - _MAX_SESSIONS]:
                _network_sessions.pop(sid, None)


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
    """Accept CSV or Excel file upload, parse IPAM data."""
    store = _get_topology_store()
    raw = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".xlsx"):
        stats = parse_ipam_excel(raw, store)
    else:
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = raw.decode("latin-1")
            except UnicodeDecodeError:
                raise HTTPException(400, "File is not valid UTF-8 or Latin-1 text")
        stats = parse_ipam_csv(content, store)

    # Reload knowledge graph after IPAM import
    kg = _get_knowledge_graph()
    kg.load_from_store()
    rf_graph = kg.export_react_flow_graph()

    return {
        "status": "imported",
        "stats": stats,
        # Frontend-expected field names (IPAMUploadDialog.tsx:54-56)
        "devices_imported": stats["devices_added"],
        "subnets_imported": stats["subnets_added"],
        # React Flow nodes/edges for canvas update (IPAMUploadDialog.tsx:59-61)
        "nodes": rf_graph["nodes"],
        "edges": rf_graph["edges"],
        # Validation warnings
        "warnings": stats.get("errors", []),
    }


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


@network_router.post("/adapters/test")
async def adapter_test(req: AdapterConfigureRequest):
    """Test adapter connection without saving."""
    from src.network.models import FirewallVendor
    from src.network.adapters.factory import create_adapter

    try:
        fw_vendor = FirewallVendor(req.vendor)
    except ValueError:
        return {"success": False, "message": f"Unknown vendor: {req.vendor}"}

    adapter = create_adapter(
        fw_vendor,
        api_endpoint=req.api_endpoint,
        api_key=req.api_key,
        extra_config=req.extra_config,
    )
    try:
        health = await adapter.health_check()
        return {"success": health.status.value == "connected", "message": health.message}
    except Exception as e:
        return {"success": False, "message": str(e)}


@network_router.post("/adapters/{vendor}/configure")
async def adapter_configure(vendor: str, req: AdapterConfigureRequest):
    """Configure a firewall adapter for a given vendor."""
    from src.network.models import FirewallVendor
    from src.network.adapters.factory import create_adapter

    try:
        fw_vendor = FirewallVendor(vendor)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown vendor: {vendor}")

    adapter = create_adapter(
        fw_vendor,
        api_endpoint=req.api_endpoint,
        api_key=req.api_key,
        extra_config=req.extra_config,
    )
    # Register by node_id if provided, else by vendor
    key = req.node_id or f"adapter-{vendor}"
    _firewall_adapters[key] = adapter
    # Persist config
    store = _get_topology_store()
    from src.network.models import AdapterConfig
    store.save_adapter_config(AdapterConfig(
        vendor=fw_vendor, api_endpoint=req.api_endpoint,
        api_key=req.api_key, extra_config=req.extra_config,
    ))
    return {"status": "configured", "vendor": vendor, "adapter_key": key}


@network_router.post("/adapters/{vendor}/refresh")
async def adapter_refresh(vendor: str):
    """Force refresh adapter snapshot for a vendor."""
    adapters = _get_adapters()
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
    # Reload KG to pick up new rules/routes from adapter
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "refreshed", "device_id": target_id, "vendor": vendor}


@network_router.get("/topology/versions")
async def topology_versions():
    """List recent diagram snapshots."""
    store = _get_topology_store()
    versions = store.list_diagram_snapshots()
    return {"versions": versions}


@network_router.get("/topology/load/{snap_id}")
async def topology_load_version(snap_id: int):
    """Load a specific diagram snapshot by ID."""
    store = _get_topology_store()
    snapshot = store.load_diagram_snapshot_by_id(snap_id)
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    return {"snapshot": snapshot}


@network_router.get("/topology/current")
async def topology_current():
    """Return current KG state as React Flow nodes/edges."""
    kg = _get_knowledge_graph()
    return kg.export_react_flow_graph()


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

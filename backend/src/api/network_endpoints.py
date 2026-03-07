"""FastAPI router for network path troubleshooting — /api/v4/network."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File

from src.api.network_models import (
    AdapterConfigureRequest,
    AdapterInstanceCreateRequest,
    AdapterInstanceUpdateRequest,
    AdapterBindRequest,
    DiagnoseRequest,
    DiagnoseResponse,
    HAGroupRequest,
    MatrixRequest,
    TopologyPromoteRequest,
    TopologySaveRequest,
)
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Flow, DiagnosisStatus
from src.network.ipam_ingestion import parse_ipam_csv, parse_ipam_excel
from src.network.adapters.base import FirewallAdapter
from src.network.adapters.registry import AdapterRegistry
from src.agents.network.graph import build_network_diagnostic_graph
from src.utils.logger import get_logger

logger = get_logger(__name__)

network_router = APIRouter(prefix="/api/v4/network", tags=["network"])

# ---------------------------------------------------------------------------
# Shared singletons (initialised lazily on first request)
# ---------------------------------------------------------------------------

_topology_store: TopologyStore | None = None
_knowledge_graph: NetworkKnowledgeGraph | None = None
_adapter_registry = AdapterRegistry()
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


def _get_adapters() -> AdapterRegistry:
    return _adapter_registry


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------


async def _run_network_diagnosis(
    session_id: str, flow_id: str, graph, initial_state: dict,
    bidirectional: bool = False, return_graph=None, return_state: dict | None = None,
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
            src = hops[i] if isinstance(hops[i], str) else hops[i].get("device_id", "") if isinstance(hops[i], dict) else ""
            dst = hops[i + 1] if isinstance(hops[i + 1], str) else hops[i + 1].get("device_id", "") if isinstance(hops[i + 1], dict) else ""
            if src and dst:
                kg.boost_edge_confidence(src, dst)
        # Return path (bidirectional)
        if bidirectional and return_graph and return_state:
            _network_sessions[session_id]["phase"] = "running_return"
            return_result = await return_graph.ainvoke(return_state)
            _network_sessions[session_id]["return_state"] = return_result
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

    if req.bidirectional:
        return_state = {
            "flow_id": flow_id,
            "src_ip": req.dst_ip,  # swapped
            "dst_ip": req.src_ip,  # swapped
            "port": req.port,
            "protocol": req.protocol,
            "session_id": session_id,
        }
        return_graph = build_network_diagnostic_graph(kg, adapters)
        background_tasks.add_task(
            _run_network_diagnosis, session_id, flow_id, compiled_graph, initial_state,
            bidirectional=True, return_graph=return_graph, return_state=return_state,
        )
    else:
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
        "return_state": session.get("return_state"),
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


@network_router.get("/ipam/interfaces")
async def ipam_interfaces():
    """List all interfaces from topology store."""
    store = _get_topology_store()
    interfaces = store.list_interfaces()
    return {"interfaces": [i.model_dump() for i in interfaces]}


# ---------------------------------------------------------------------------
# Entity CRUD endpoints (devices, subnets, interfaces, routes, VPCs, zones)
# ---------------------------------------------------------------------------


@network_router.get("/devices/{device_id}")
async def get_device(device_id: str):
    """Get a single device by ID."""
    store = _get_topology_store()
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"device": device.model_dump()}


@network_router.patch("/devices/{device_id}")
async def update_device(device_id: str, body: Dict[str, Any]):
    """Update device configuration fields."""
    store = _get_topology_store()
    device = store.update_device(device_id, **body)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    # Reload KG to pick up changes
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"device": device.model_dump()}


@network_router.delete("/devices/{device_id}")
async def delete_device_endpoint(device_id: str):
    """Delete a device and all its dependent entities (interfaces, routes, etc.)."""
    store = _get_topology_store()
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    store.delete_device(device_id)
    # Reload KG
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "deleted", "device_id": device_id}


@network_router.get("/devices/{device_id}/interfaces")
async def device_interfaces(device_id: str):
    """List interfaces for a specific device."""
    store = _get_topology_store()
    interfaces = store.list_interfaces(device_id=device_id)
    return {"interfaces": [i.model_dump() for i in interfaces]}


@network_router.get("/devices/{device_id}/routes")
async def device_routes(device_id: str):
    """List routes for a specific device."""
    store = _get_topology_store()
    routes = store.list_routes(device_id=device_id)
    return {"routes": [r.model_dump() for r in routes]}


@network_router.delete("/subnets/{subnet_id}")
async def delete_subnet(subnet_id: str):
    """Delete a subnet."""
    store = _get_topology_store()
    store.delete_subnet(subnet_id)
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "deleted", "subnet_id": subnet_id}


@network_router.delete("/interfaces/{interface_id}")
async def delete_interface(interface_id: str):
    """Delete an interface."""
    store = _get_topology_store()
    store.delete_interface(interface_id)
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "deleted", "interface_id": interface_id}


@network_router.delete("/routes/{route_id}")
async def delete_route(route_id: str):
    """Delete a route."""
    store = _get_topology_store()
    store.delete_route(route_id)
    return {"status": "deleted", "route_id": route_id}


@network_router.delete("/vpcs/{vpc_id}")
async def delete_vpc(vpc_id: str):
    """Delete a VPC and its route tables."""
    store = _get_topology_store()
    vpc = store.get_vpc(vpc_id)
    if not vpc:
        raise HTTPException(status_code=404, detail="VPC not found")
    store.delete_vpc(vpc_id)
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "deleted", "vpc_id": vpc_id}


@network_router.delete("/zones/{zone_id}")
async def delete_zone(zone_id: str):
    """Delete a zone."""
    store = _get_topology_store()
    store.delete_zone(zone_id)
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "deleted", "zone_id": zone_id}


# ---------------------------------------------------------------------------
# Instance-scoped adapter endpoints (multi-instance support)
# ---------------------------------------------------------------------------


def _strip_api_key(d: dict) -> dict:
    """Remove api_key from response dict for security."""
    return {k: v for k, v in d.items() if k != "api_key"}


def _safe_snapshot_age(seconds: float) -> float:
    """Clamp infinite snapshot age to 0 for JSON serialization."""
    import math
    return 0.0 if math.isinf(seconds) or math.isnan(seconds) else seconds


@network_router.get("/adapters")
async def list_adapter_instances():
    """List all adapter instances with live health status."""
    store = _get_topology_store()
    instances = store.list_adapter_instances()
    results = []
    for inst in instances:
        adapter = _adapter_registry.get_by_instance(inst.instance_id)
        health_info = {"status": "not_configured", "message": "Not loaded", "snapshot_age_seconds": 0, "last_refresh": ""}
        if adapter:
            try:
                health = await adapter.health_check()
                health_info = {
                    "status": health.status.value,
                    "message": health.message,
                    "snapshot_age_seconds": _safe_snapshot_age(health.snapshot_age_seconds),
                    "last_refresh": health.last_refresh,
                }
            except Exception as e:
                health_info = {"status": "unreachable", "message": str(e), "snapshot_age_seconds": 0, "last_refresh": ""}
        result = _strip_api_key(inst.model_dump())
        result["vendor"] = inst.vendor.value
        result.update(health_info)
        results.append(result)
    return {"adapters": results}


@network_router.post("/adapters")
async def create_adapter_instance(req: AdapterInstanceCreateRequest):
    """Create a new adapter instance."""
    from src.network.models import FirewallVendor, AdapterInstance
    from src.network.adapters.factory import create_adapter

    try:
        fw_vendor = FirewallVendor(req.vendor)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown vendor: {req.vendor}")

    instance = AdapterInstance(
        label=req.label,
        vendor=fw_vendor,
        api_endpoint=req.api_endpoint,
        api_key=req.api_key,
        extra_config=req.extra_config,
    )

    store = _get_topology_store()
    store.save_adapter_instance(instance)

    adapter = create_adapter(
        fw_vendor,
        api_endpoint=req.api_endpoint,
        api_key=req.api_key,
        extra_config=req.extra_config,
    )
    _adapter_registry.register(instance.instance_id, adapter)

    return {"status": "created", "instance_id": instance.instance_id, "label": instance.label}


@network_router.post("/adapters/test-new")
async def adapter_test_new(req: AdapterInstanceCreateRequest):
    """Test an unsaved adapter configuration."""
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


# ---------------------------------------------------------------------------
# Legacy adapter endpoints (must be before {instance_id} to avoid capture)
# ---------------------------------------------------------------------------


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
            "snapshot_age_seconds": _safe_snapshot_age(health.snapshot_age_seconds),
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
    # Register as an adapter instance for multi-instance support
    from src.network.models import AdapterConfig, AdapterInstance
    import uuid as _uuid
    store = _get_topology_store()

    instance_id = str(_uuid.uuid4())
    instance = AdapterInstance(
        instance_id=instance_id,
        label=req.node_id or f"{vendor}",
        vendor=fw_vendor,
        api_endpoint=req.api_endpoint,
        api_key=req.api_key,
        extra_config=req.extra_config,
    )
    store.save_adapter_instance(instance)

    key = req.node_id or instance_id
    _adapter_registry.register(instance_id, adapter, [key] if req.node_id else [])

    # Also persist to legacy table for backward compat
    store.save_adapter_config(AdapterConfig(
        vendor=fw_vendor, api_endpoint=req.api_endpoint,
        api_key=req.api_key, extra_config=req.extra_config,
    ))
    return {"status": "configured", "vendor": vendor, "adapter_key": key, "instance_id": instance_id}


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


# ---------------------------------------------------------------------------
# Instance-scoped adapter endpoints
# ---------------------------------------------------------------------------


@network_router.get("/adapters/{instance_id}")
async def get_adapter_instance(instance_id: str):
    """Get adapter instance detail with health."""
    store = _get_topology_store()
    inst = store.get_adapter_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Adapter instance not found")

    adapter = _adapter_registry.get_by_instance(instance_id)
    health_info = {"status": "not_configured", "message": "Not loaded", "snapshot_age_seconds": 0, "last_refresh": ""}
    if adapter:
        try:
            health = await adapter.health_check()
            health_info = {
                "status": health.status.value,
                "message": health.message,
                "snapshot_age_seconds": _safe_snapshot_age(health.snapshot_age_seconds),
                "last_refresh": health.last_refresh,
            }
        except Exception as e:
            health_info = {"status": "unreachable", "message": str(e), "snapshot_age_seconds": 0, "last_refresh": ""}

    result = _strip_api_key(inst.model_dump())
    result["vendor"] = inst.vendor.value
    result.update(health_info)
    bindings = store.list_device_bindings_for_instance(instance_id)
    result["bound_devices"] = bindings
    return result


@network_router.put("/adapters/{instance_id}")
async def update_adapter_instance(instance_id: str, req: AdapterInstanceUpdateRequest):
    """Update an existing adapter instance."""
    from src.network.models import AdapterInstance
    from src.network.adapters.factory import create_adapter

    store = _get_topology_store()
    existing = store.get_adapter_instance(instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Adapter instance not found")

    if req.label is not None:
        existing.label = req.label
    if req.api_endpoint is not None:
        existing.api_endpoint = req.api_endpoint
    if req.api_key is not None:
        existing.api_key = req.api_key
    if req.extra_config is not None:
        existing.extra_config = req.extra_config
    if req.device_groups is not None:
        existing.device_groups = req.device_groups

    store.save_adapter_instance(existing)

    # Re-create and re-register the adapter
    adapter = create_adapter(
        existing.vendor,
        api_endpoint=existing.api_endpoint,
        api_key=existing.api_key,
        extra_config=existing.extra_config,
    )
    _adapter_registry.register(instance_id, adapter)

    return {"status": "updated", "instance_id": instance_id}


@network_router.delete("/adapters/{instance_id}")
async def delete_adapter_instance(instance_id: str):
    """Delete an adapter instance and its device bindings."""
    store = _get_topology_store()
    existing = store.get_adapter_instance(instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Adapter instance not found")

    store.delete_adapter_instance(instance_id)
    _adapter_registry.remove(instance_id)

    return {"status": "deleted", "instance_id": instance_id}


@network_router.post("/adapters/{instance_id}/test")
async def adapter_instance_test(instance_id: str):
    """Test connection for an existing adapter instance."""
    adapter = _adapter_registry.get_by_instance(instance_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Adapter instance not found or not loaded")
    try:
        health = await adapter.health_check()
        return {"success": health.status.value == "connected", "message": health.message}
    except Exception as e:
        return {"success": False, "message": str(e)}


@network_router.post("/adapters/{instance_id}/refresh")
async def adapter_instance_refresh(instance_id: str):
    """Force refresh snapshot for a specific adapter instance."""
    adapter = _adapter_registry.get_by_instance(instance_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Adapter instance not found or not loaded")
    await adapter.refresh_snapshot()
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "refreshed", "instance_id": instance_id}


@network_router.get("/adapters/{instance_id}/discover")
async def adapter_discover_device_groups(instance_id: str):
    """Discover Panorama device groups for a Palo Alto adapter instance."""
    adapter = _adapter_registry.get_by_instance(instance_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Adapter instance not found or not loaded")

    if not hasattr(adapter, "discover_device_groups"):
        return {"device_groups": [], "message": "Device group discovery not supported for this vendor"}

    try:
        groups = await adapter.discover_device_groups()
        return {"device_groups": groups}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Discovery failed: {e}")


@network_router.post("/adapters/{instance_id}/bind")
async def adapter_bind_devices(instance_id: str, req: AdapterBindRequest):
    """Bind device_ids to an adapter instance."""
    store = _get_topology_store()
    existing = store.get_adapter_instance(instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Adapter instance not found")

    for device_id in req.device_ids:
        store.save_device_binding(device_id, instance_id)
        _adapter_registry.bind_device(device_id, instance_id)

    return {"status": "bound", "instance_id": instance_id, "device_ids": req.device_ids}


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


@network_router.post("/topology/promote")
async def topology_promote(req: TopologyPromoteRequest):
    """Promote canvas nodes/edges to the authoritative Knowledge Graph."""
    kg = _get_knowledge_graph()
    result = kg.promote_from_canvas(req.nodes, req.edges)
    return {"status": "promoted", **result}


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


@network_router.post("/matrix")
async def reachability_matrix(req: MatrixRequest):
    """Compute zone-to-zone reachability matrix."""
    from src.agents.network.reachability_matrix import compute_reachability_matrix
    kg = _get_knowledge_graph()
    result = compute_reachability_matrix(kg, req.zone_ids)
    return result


@network_router.post("/ha-groups")
async def create_ha_group(req: HAGroupRequest):
    """Create an HA group."""
    from src.network.models import HAGroup, HAMode
    store = _get_topology_store()
    group = HAGroup(
        id=str(uuid.uuid4()),
        name=req.name,
        ha_mode=HAMode(req.ha_mode),
        member_ids=req.member_ids,
        virtual_ips=req.virtual_ips,
        active_member_id=req.active_member_id,
    )
    store.add_ha_group(group)
    # Update member devices with ha_group_id
    for mid in req.member_ids:
        device = store.get_device(mid)
        if device:
            role = "active" if mid == req.active_member_id else "standby"
            if req.ha_mode == "active_active":
                role = "member"
            device.ha_group_id = group.id
            device.ha_role = role
            store.add_device(device)
    return {"status": "created", "ha_group_id": group.id}


@network_router.get("/ha-groups")
async def list_ha_groups():
    """List all HA groups."""
    store = _get_topology_store()
    groups = store.list_ha_groups()
    return {"ha_groups": [g.model_dump() for g in groups]}


@network_router.get("/ha-groups/{group_id}/validate")
async def validate_ha(group_id: str):
    """Validate an HA group against topology rules."""
    from src.network.ha_validation import validate_ha_group

    store = _get_topology_store()
    group = store.get_ha_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="HA group not found")
    errors = validate_ha_group(store, group)
    return {"group_id": group_id, "valid": len(errors) == 0, "errors": errors}


@network_router.get("/ha-groups/{group_id}")
async def get_ha_group(group_id: str):
    """Get HA group details."""
    store = _get_topology_store()
    group = store.get_ha_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="HA group not found")
    return {"ha_group": group.model_dump()}


@network_router.delete("/ha-groups/{group_id}")
async def delete_ha_group(group_id: str):
    """Delete an HA group and clear member references."""
    store = _get_topology_store()
    group = store.get_ha_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="HA group not found")
    store.delete_ha_group(group_id)
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "deleted", "ha_group_id": group_id}

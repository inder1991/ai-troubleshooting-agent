"""FastAPI router for network path troubleshooting — /api/v4/network."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile, File

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
from src.network.discovery_engine import DiscoveryEngine
from src.network.models import Flow, DiagnosisStatus, IPAddress, IPStatus, Subnet
from src.network.ipam_ingestion import parse_ipam_csv, parse_ipam_excel
from src.network.ipam_ingestion import populate_subnet_ips
from src.network.adapters.base import FirewallAdapter
from src.network.adapters.registry import AdapterRegistry
from src.agents.network.graph import build_network_diagnostic_graph
from src.utils.logger import get_logger

logger = get_logger(__name__)

network_router = APIRouter(prefix="/api/v4/network", tags=["network"])

# Maximum file size for IPAM imports (50 MB)
MAX_IMPORT_SIZE = 50 * 1024 * 1024

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
async def ipam_upload(request: Request, file: UploadFile = File(...)):
    """Accept CSV or Excel file upload, parse IPAM data.

    Enforces a MAX_IMPORT_SIZE (50 MB) limit. Checks Content-Length header
    first for fast rejection, then streams in 64 KB chunks to enforce the
    limit even when Content-Length is absent.
    """
    # Fast reject via Content-Length header if present
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_IMPORT_SIZE:
                raise HTTPException(413, f"File exceeds maximum import size of {MAX_IMPORT_SIZE} bytes")
        except ValueError:
            pass  # Non-numeric Content-Length; fall through to streaming check

    # Stream in chunks to enforce size limit when Content-Length is missing
    chunks: list[bytes] = []
    total_size = 0
    chunk_size = 64 * 1024  # 64 KB
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_IMPORT_SIZE:
            raise HTTPException(413, f"File exceeds maximum import size of {MAX_IMPORT_SIZE} bytes")
        chunks.append(chunk)
    raw = b"".join(chunks)

    store = _get_topology_store()
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
# IPAM — Subnet Management
# ---------------------------------------------------------------------------

@network_router.get("/ipam/subnets/{subnet_id}")
async def ipam_subnet_detail(subnet_id: str):
    """Get subnet detail with utilization stats."""
    store = _get_topology_store()
    subnet = store.get_subnet(subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")
    util = store.get_subnet_utilization(subnet_id)
    data = subnet.model_dump()
    data.update(util)
    return data


@network_router.put("/ipam/subnets/{subnet_id}")
async def ipam_update_subnet(subnet_id: str, body: dict):
    """Update subnet fields."""
    store = _get_topology_store()
    updated = store.update_subnet(subnet_id, **body)
    if not updated:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return updated.model_dump()


@network_router.post("/ipam/subnets")
async def ipam_create_subnet(body: dict):
    """Create a new subnet manually."""
    store = _get_topology_store()
    subnet_id = body.get("id", f"subnet-{uuid.uuid4().hex[:8]}")
    cidr = body.get("cidr", "")
    if not cidr:
        raise HTTPException(status_code=400, detail="cidr is required")
    subnet = Subnet(
        id=subnet_id,
        cidr=cidr,
        vlan_id=int(body.get("vlan_id", 0)),
        zone_id=body.get("zone_id", ""),
        gateway_ip=body.get("gateway_ip", ""),
        description=body.get("description", ""),
        site=body.get("site", ""),
        parent_subnet_id=body.get("parent_subnet_id", ""),
        region=body.get("region", ""),
        environment=body.get("environment", ""),
        ip_version=int(body.get("ip_version", 4)),
        vpc_id=body.get("vpc_id", ""),
        cloud_provider=body.get("cloud_provider", ""),
        vrf_id=body.get("vrf_id", "default"),
        subnet_role=body.get("subnet_role", ""),
        address_block_id=body.get("address_block_id", ""),
        site_id=body.get("site_id", ""),
    )
    # Auto-detect address_block_id and validate subnet fits within a block
    import ipaddress as _ipaddr
    try:
        subnet_net = _ipaddr.ip_network(subnet.cidr, strict=False)
        vrf_blocks = [b for b in store.list_address_blocks() if b.vrf_id == subnet.vrf_id]

        if not subnet.address_block_id and vrf_blocks:
            matched = False
            for blk in vrf_blocks:
                blk_net = _ipaddr.ip_network(blk.cidr, strict=False)
                if subnet_net.subnet_of(blk_net):
                    subnet.address_block_id = blk.id
                    if blk.site_id and not subnet.site_id:
                        subnet.site_id = blk.site_id
                    matched = True
                    break
            if not matched:
                block_cidrs = ", ".join(b.cidr for b in vrf_blocks)
                raise HTTPException(
                    status_code=400,
                    detail=f"Subnet {subnet.cidr} does not fit within any address block "
                           f"in VRF '{subnet.vrf_id}'. Available blocks: {block_cidrs}",
                )
    except HTTPException:
        raise
    except ValueError:
        pass

    store.add_subnet(subnet)
    # Initialize free ranges for lazy allocation
    store.init_free_ranges(subnet.id, subnet.cidr, subnet.gateway_ip)
    # Create gateway IP record if set
    if subnet.gateway_ip:
        from src.network.ipam_ingestion import _sanitize_id
        gw_ip_id = f"ip-{_sanitize_id(subnet.id)}-{_sanitize_id(subnet.gateway_ip)}"
        gw_ip = IPAddress(
            id=gw_ip_id, address=subnet.gateway_ip, subnet_id=subnet.id,
            status="assigned", ip_type="gateway",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        store.add_ip_address(gw_ip)
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "created", "subnet": subnet.model_dump()}


@network_router.post("/ipam/subnets/{subnet_id}/populate")
async def ipam_populate_subnet(subnet_id: str):
    """Auto-create all host IPs for a subnet."""
    store = _get_topology_store()
    subnet = store.get_subnet(subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")
    created = populate_subnet_ips(store, subnet)
    return {"status": "populated", "created": created, "subnet_id": subnet_id}


# ---------------------------------------------------------------------------
# IPAM — IP Address Management
# ---------------------------------------------------------------------------

@network_router.get("/ipam/ips")
async def ipam_list_ips(subnet_id: str = "", status: str = "", search: str = "",
                        offset: int = 0, limit: int = 100):
    """List IP addresses with optional filters and pagination."""
    store = _get_topology_store()
    result = store.list_ip_addresses(
        subnet_id=subnet_id or None,
        status=status or None,
        search=search or None,
        offset=offset,
        limit=limit,
    )
    return {"ips": [ip.model_dump() for ip in result["ips"]], "total": result["total"]}


@network_router.get("/ipam/ips/{ip_id}")
async def ipam_get_ip(ip_id: str):
    """Get a single IP address."""
    store = _get_topology_store()
    ip = store.get_ip_address(ip_id)
    if not ip:
        raise HTTPException(status_code=404, detail="IP not found")
    return ip.model_dump()


@network_router.put("/ipam/ips/{ip_id}")
async def ipam_update_ip(ip_id: str, body: dict):
    """Update IP address fields (status, hostname, description)."""
    store = _get_topology_store()
    updated = store.update_ip_address(ip_id, **body)
    if not updated:
        raise HTTPException(status_code=404, detail="IP not found")
    return updated.model_dump()


@network_router.post("/ipam/ips/{ip_id}/reserve")
async def ipam_reserve_ip(ip_id: str):
    """Set IP status to reserved."""
    store = _get_topology_store()
    updated = store.update_ip_status(ip_id, "reserved")
    if not updated:
        raise HTTPException(status_code=404, detail="IP not found")
    return updated.model_dump()


@network_router.post("/ipam/ips/{ip_id}/assign")
async def ipam_assign_ip(ip_id: str, body: dict):
    """Assign IP to a device."""
    store = _get_topology_store()
    device_id = body.get("device_id", "")
    interface_id = body.get("interface_id", "")
    updated = store.update_ip_status(ip_id, "assigned", device_id=device_id, interface_id=interface_id)
    if not updated:
        raise HTTPException(status_code=404, detail="IP not found")
    return updated.model_dump()


@network_router.post("/ipam/ips/{ip_id}/release")
async def ipam_release_ip(ip_id: str):
    """Release IP back to available."""
    store = _get_topology_store()
    updated = store.update_ip_status(ip_id, "available")
    if not updated:
        raise HTTPException(status_code=404, detail="IP not found")
    return updated.model_dump()


# ---------------------------------------------------------------------------
# IPAM — Hierarchy & Utilization
# ---------------------------------------------------------------------------

@network_router.get("/ipam/tree")
async def ipam_tree():
    """Full hierarchy tree (regions → zones → subnets)."""
    store = _get_topology_store()
    return {"tree": store.get_subnet_tree()}


@network_router.get("/ipam/utilization")
async def ipam_utilization():
    """All subnets with utilization stats."""
    store = _get_topology_store()
    subnets = store.list_subnets()
    result = []
    for s in subnets:
        data = s.model_dump()
        data.update(store.get_subnet_utilization(s.id))
        result.append(data)
    return {"subnets": result}


@network_router.get("/ipam/utilization/{subnet_id}")
async def ipam_subnet_utilization(subnet_id: str):
    """Single subnet utilization detail."""
    store = _get_topology_store()
    subnet = store.get_subnet(subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")
    data = subnet.model_dump()
    data.update(store.get_subnet_utilization(subnet_id))
    return data


@network_router.get("/ipam/stats")
async def ipam_stats():
    """Global IPAM stats."""
    store = _get_topology_store()
    return store.get_ipam_stats()


@network_router.post("/ipam/ips/bulk-status")
async def ipam_bulk_status(body: dict):
    """Bulk update IP status for multiple IPs at once."""
    store = _get_topology_store()
    ip_ids = body.get("ip_ids", [])
    status = body.get("status", "")
    device_id = body.get("device_id", "")
    if not ip_ids or not status:
        raise HTTPException(status_code=400, detail="ip_ids and status required")
    valid_statuses = {s.value for s in IPStatus}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status '{status}'. Must be one of: {', '.join(sorted(valid_statuses))}")
    count = store.bulk_update_ip_status(ip_ids, status, device_id=device_id)
    return {"updated": count}


@network_router.get("/ipam/search")
async def ipam_global_search(q: str = ""):
    """Global search across all IPs by address, hostname, MAC, or description."""
    store = _get_topology_store()
    if not q or len(q) < 2:
        return {"results": []}
    results = store.search_ips_global(q)
    return {"results": results}


@network_router.get("/ipam/conflicts")
async def ipam_conflicts():
    """Detect IP address conflicts (same address in multiple subnets)."""
    store = _get_topology_store()
    conflicts = store.detect_ip_conflicts()
    return {"conflicts": conflicts, "count": len(conflicts)}


@network_router.get("/ipam/subnets/{subnet_id}/next-available")
async def ipam_next_available(subnet_id: str):
    """Find the next available IP in a subnet."""
    store = _get_topology_store()
    ip_addr = store.get_next_available_ip(subnet_id)
    if not ip_addr:
        raise HTTPException(status_code=404, detail="No available IPs in this subnet")
    return {"address": ip_addr, "subnet_id": subnet_id}


@network_router.get("/ipam/audit-log")
async def ipam_audit_log(ip_id: str = "", limit: int = 50):
    """Get IP audit log entries."""
    store = _get_topology_store()
    events = store.get_ip_audit_log(ip_id=ip_id, limit=limit)
    return {"events": events}


@network_router.delete("/ipam/subnets/{subnet_id}")
async def ipam_delete_subnet(subnet_id: str):
    """Delete a subnet and all its IPs (cascade)."""
    store = _get_topology_store()
    subnet = store.get_subnet(subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")
    store.delete_subnet(subnet_id)
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "deleted", "subnet_id": subnet_id}


@network_router.delete("/ipam/ips/{ip_id}")
async def ipam_delete_ip(ip_id: str):
    """Delete a single IP address."""
    store = _get_topology_store()
    ip = store.get_ip_address(ip_id)
    if not ip:
        raise HTTPException(status_code=404, detail="IP not found")
    store.delete_ip_address(ip_id)
    return {"status": "deleted", "ip_id": ip_id}


@network_router.get("/ipam/ips/by-address")
async def ipam_get_ip_by_address(address: str = ""):
    """Lookup an IP by its address string."""
    if not address:
        raise HTTPException(status_code=400, detail="address parameter required")
    store = _get_topology_store()
    ip = store.get_ip_by_address(address)
    if not ip:
        raise HTTPException(status_code=404, detail="IP not found")
    return ip.model_dump()


@network_router.post("/ipam/subnets/{subnet_id}/split")
async def ipam_split_subnet(subnet_id: str, body: dict):
    """Split a subnet into smaller subnets."""
    store = _get_topology_store()
    new_prefix = body.get("new_prefix")
    if new_prefix is None:
        raise HTTPException(status_code=400, detail="new_prefix is required")
    try:
        new_prefix = int(new_prefix)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"new_prefix must be an integer, got: {body.get('new_prefix')}")
    if new_prefix < 1 or new_prefix > 128:
        raise HTTPException(status_code=400, detail=f"new_prefix must be between 1 and 128, got: {new_prefix}")
    created = store.split_subnet(subnet_id, new_prefix)
    if not created:
        raise HTTPException(status_code=400, detail="Cannot split: invalid prefix or subnet not found")
    # Populate IPs for each new subnet
    for s in created:
        populate_subnet_ips(store, s)
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {
        "status": "split",
        "parent_id": subnet_id,
        "children": [s.model_dump() for s in created],
        "count": len(created),
    }


@network_router.post("/ipam/subnets/merge")
async def ipam_merge_subnets(body: dict):
    """Merge subnets into their supernet."""
    store = _get_topology_store()
    subnet_ids = body.get("subnet_ids", [])
    if len(subnet_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 subnet_ids required")
    # Pre-validate all subnet IDs exist
    missing = []
    for sid in subnet_ids:
        if not store.get_subnet(sid):
            missing.append(sid)
    if missing:
        raise HTTPException(status_code=404, detail=f"Subnet(s) not found: {', '.join(missing)}")
    merged = store.merge_subnets(subnet_ids)
    if not merged:
        raise HTTPException(status_code=400, detail="Cannot merge: subnets don't form a valid supernet")
    kg = _get_knowledge_graph()
    kg.load_from_store()
    return {"status": "merged", "subnet": merged.model_dump()}


@network_router.get("/ipam/export")
async def ipam_export_csv():
    """Export all IPAM data as CSV."""
    from starlette.responses import Response
    store = _get_topology_store()
    csv_data = store.export_ipam_csv()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ipam_export.csv"},
    )


@network_router.get("/ipam/dns-mismatches")
async def ipam_dns_mismatches():
    """Detect DNS/hostname mismatches in IPAM data."""
    store = _get_topology_store()
    mismatches = store.detect_dns_mismatches()
    return {"mismatches": mismatches, "count": len(mismatches)}


@network_router.get("/ipam/capacity-forecast")
async def ipam_capacity_forecast():
    """Get subnet capacity forecast data."""
    store = _get_topology_store()
    forecast = store.get_capacity_forecast()
    return {"subnets": forecast}


# ---------------------------------------------------------------------------
# IPAM ↔ Monitoring Integration (Phase C)
# ---------------------------------------------------------------------------


@network_router.post("/ipam/subnets/{subnet_id}/scan")
async def ipam_scan_subnet(subnet_id: str, background_tasks: BackgroundTasks):
    """Trigger an active ping scan of a subnet, updating IPAM with results."""
    store = _get_topology_store()
    subnet = store.get_subnet(subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    kg = _get_knowledge_graph()
    engine = DiscoveryEngine(store, kg)

    results = await engine.scan_subnet_for_ipam(subnet.cidr)
    updated = 0
    now = datetime.now(timezone.utc).isoformat()
    for r in results:
        if r["alive"]:
            ip_rec = store.get_ip_by_address(r["ip"])
            if ip_rec:
                updates = {"last_seen": now}
                if r["hostname"] and not ip_rec.hostname:
                    updates["hostname"] = r["hostname"]
                store.update_ip_address(ip_rec.id, **updates)
                updated += 1

    return {
        "status": "completed",
        "subnet_id": subnet_id,
        "cidr": subnet.cidr,
        "total_scanned": len(results),
        "alive_count": sum(1 for r in results if r["alive"]),
        "updated_ips": updated,
        "results": results[:100],  # Limit response size
    }


@network_router.get("/ipam/ips/{ip_id}/dns")
async def ipam_ip_dns_lookup(ip_id: str):
    """Forward and reverse DNS lookup for an IP address."""
    import socket
    store = _get_topology_store()
    ip = store.get_ip_address(ip_id)
    if not ip:
        raise HTTPException(status_code=404, detail="IP not found")

    result = {"address": ip.address, "hostname": ip.hostname, "forward": None, "reverse": None, "mismatch": False}

    # Reverse DNS (IP -> hostname)
    try:
        hostname, _, _ = socket.gethostbyaddr(ip.address)
        result["reverse"] = hostname
    except (socket.herror, socket.gaierror, OSError):
        result["reverse"] = None

    # Forward DNS (hostname -> IP) if we have a hostname
    lookup_hostname = result["reverse"] or ip.hostname
    if lookup_hostname:
        try:
            _, _, addrs = socket.gethostbyname_ex(lookup_hostname)
            result["forward"] = addrs
            # Check mismatch: forward resolution doesn't include the original IP
            if ip.address not in addrs:
                result["mismatch"] = True
        except (socket.herror, socket.gaierror, OSError):
            result["forward"] = None

    return result


@network_router.get("/ipam/subnets/{subnet_id}/utilization-history")
async def ipam_utilization_history(subnet_id: str, range: str = "7d"):
    """Get historical utilization data for a subnet from InfluxDB."""
    store = _get_topology_store()
    subnet = store.get_subnet(subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    # Try InfluxDB metrics store
    try:
        from src.network.metrics_store import MetricsStore
        import os
        url = os.environ.get("INFLUXDB_URL", "")
        token = os.environ.get("INFLUXDB_TOKEN", "")
        org = os.environ.get("INFLUXDB_ORG", "")
        bucket = os.environ.get("INFLUXDB_BUCKET", "network")
        if url and token:
            ms = MetricsStore(url=url, token=token, org=org, bucket=bucket)
            try:
                data = await ms.query_ipam_utilization(subnet_id, range_str=range)
                return {"subnet_id": subnet_id, "range": range, "data": data}
            finally:
                await ms.close()
    except Exception:
        pass

    # Fallback: return current snapshot only
    util = store.get_subnet_utilization(subnet_id)
    return {
        "subnet_id": subnet_id,
        "range": range,
        "data": [{"time": datetime.now(timezone.utc).isoformat(), "value": util.get("utilization_pct", 0)}],
    }


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


@network_router.get("/topology/diff")
async def topology_diff(v1: int, v2: int):
    """Compare two topology snapshots and show added, removed, and changed devices."""
    import json as _json

    store = _get_topology_store()
    snap1 = store.load_diagram_snapshot_by_id(v1)
    snap2 = store.load_diagram_snapshot_by_id(v2)
    if not snap1 or not snap2:
        raise HTTPException(404, "One or both snapshots not found")

    data1 = _json.loads(snap1.get("snapshot_json", "{}"))
    data2 = _json.loads(snap2.get("snapshot_json", "{}"))

    nodes1 = {n["id"]: n for n in data1.get("nodes", [])}
    nodes2 = {n["id"]: n for n in data2.get("nodes", [])}

    added = [nodes2[nid] for nid in nodes2 if nid not in nodes1]
    removed = [nodes1[nid] for nid in nodes1 if nid not in nodes2]
    changed = []
    for nid in nodes1:
        if nid in nodes2 and nodes1[nid] != nodes2[nid]:
            changed.append({"id": nid, "before": nodes1[nid], "after": nodes2[nid]})

    return {"v1": v1, "v2": v2, "added": added, "removed": removed, "changed": changed}


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


@network_router.get("/ipam/subnets/{subnet_id}/available-ranges")
async def ipam_available_ranges(subnet_id: str):
    """Get available (unallocated) ranges within a parent subnet."""
    store = _get_topology_store()
    subnet = store.get_subnet(subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")
    ranges = store.get_available_ranges(subnet_id)
    return {"subnet_id": subnet_id, "cidr": subnet.cidr, "available_ranges": ranges}


@network_router.get("/ipam/dhcp-scopes")
async def ipam_list_dhcp_scopes(subnet_id: str = ""):
    """List DHCP scopes, optionally filtered by subnet."""
    store = _get_topology_store()
    scopes = store.list_dhcp_scopes(subnet_id=subnet_id)
    return {"scopes": scopes}


@network_router.post("/ipam/dhcp-scopes")
async def ipam_create_dhcp_scope(body: dict):
    """Create or update a DHCP scope."""
    store = _get_topology_store()
    scope_id = body.get("id", f"dhcp-{uuid.uuid4().hex[:8]}")
    name = body.get("name", "")
    scope_cidr = body.get("scope_cidr", "")
    if not name or not scope_cidr:
        raise HTTPException(status_code=400, detail="name and scope_cidr are required")
    scope = {
        "id": scope_id,
        "name": name,
        "scope_cidr": scope_cidr,
        "server_ip": body.get("server_ip", ""),
        "subnet_id": body.get("subnet_id", ""),
        "total_leases": body.get("total_leases", 0),
        "active_leases": body.get("active_leases", 0),
        "free_count": body.get("free_count", 0),
        "source": body.get("source", "manual"),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    store.add_dhcp_scope(scope)
    return {"status": "created", "scope": scope}


@network_router.delete("/ipam/dhcp-scopes/{scope_id}")
async def ipam_delete_dhcp_scope(scope_id: str):
    """Delete a DHCP scope."""
    store = _get_topology_store()
    store.delete_dhcp_scope(scope_id)
    return {"status": "deleted", "scope_id": scope_id}


# ---------------------------------------------------------------------------
# IPAM — Reserved Ranges
# ---------------------------------------------------------------------------

@network_router.get("/ipam/subnets/{subnet_id}/reserved-ranges")
async def ipam_list_reserved_ranges(subnet_id: str):
    store = _get_topology_store()
    return {"ranges": store.list_reserved_ranges(subnet_id)}


@network_router.post("/ipam/subnets/{subnet_id}/reserved-ranges")
async def ipam_create_reserved_range(subnet_id: str, body: dict):
    store = _get_topology_store()
    subnet = store.get_subnet(subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")
    start_ip = body.get("start_ip", "")
    end_ip = body.get("end_ip", "")
    if not start_ip or not end_ip:
        raise HTTPException(status_code=400, detail="start_ip and end_ip are required")
    result = store.add_reserved_range(
        subnet_id, start_ip, end_ip,
        reason=body.get("reason", ""),
        owner_team=body.get("owner_team", ""),
    )
    return {"status": "created", "range": result}


@network_router.delete("/ipam/reserved-ranges/{range_id}")
async def ipam_delete_reserved_range(range_id: str):
    store = _get_topology_store()
    store.delete_reserved_range(range_id)
    return {"status": "deleted", "range_id": range_id}


# ---------------------------------------------------------------------------
# IPAM — VRF Management
# ---------------------------------------------------------------------------

@network_router.get("/ipam/vrfs")
async def ipam_list_vrfs():
    store = _get_topology_store()
    vrfs = store.list_vrfs()
    return {"vrfs": [v.model_dump() for v in vrfs]}


@network_router.post("/ipam/vrfs")
async def ipam_create_vrf(body: dict):
    from src.network.models import VRF
    store = _get_topology_store()
    vrf_id = body.get("id", f"vrf-{uuid.uuid4().hex[:8]}")
    vrf = VRF(
        id=vrf_id,
        name=body.get("name", vrf_id),
        rd=body.get("rd", ""),
        rt_import=body.get("rt_import", []),
        rt_export=body.get("rt_export", []),
        description=body.get("description", ""),
        device_ids=body.get("device_ids", []),
    )
    store.add_vrf(vrf)
    return {"status": "created", "vrf": vrf.model_dump()}


@network_router.get("/ipam/vrfs/{vrf_id}")
async def ipam_get_vrf(vrf_id: str):
    store = _get_topology_store()
    vrf = store.get_vrf(vrf_id)
    if not vrf:
        raise HTTPException(status_code=404, detail="VRF not found")
    return vrf.model_dump()


@network_router.put("/ipam/vrfs/{vrf_id}")
async def ipam_update_vrf(vrf_id: str, body: dict):
    store = _get_topology_store()
    updated = store.update_vrf(vrf_id, **body)
    if not updated:
        raise HTTPException(status_code=404, detail="VRF not found")
    return updated.model_dump()


@network_router.delete("/ipam/vrfs/{vrf_id}")
async def ipam_delete_vrf(vrf_id: str):
    store = _get_topology_store()
    vrf = store.get_vrf(vrf_id)
    if not vrf:
        raise HTTPException(status_code=404, detail="VRF not found")
    if vrf.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default VRF")
    store.delete_vrf(vrf_id)
    return {"status": "deleted", "vrf_id": vrf_id}


# ---------------------------------------------------------------------------
# IPAM — Region, Site, AddressBlock Management
# ---------------------------------------------------------------------------

@network_router.get("/ipam/regions")
async def ipam_list_regions():
    store = _get_topology_store()
    regions = store.list_regions()
    return {"regions": [r.model_dump() for r in regions]}


@network_router.post("/ipam/regions")
async def ipam_create_region(body: dict):
    from src.network.models import Region
    store = _get_topology_store()
    region = Region(
        id=body.get("id", f"region-{uuid.uuid4().hex[:8]}"),
        name=body.get("name", ""),
        description=body.get("description", ""),
    )
    store.add_region(region)
    return {"status": "created", "region": region.model_dump()}


@network_router.get("/ipam/regions/{region_id}")
async def ipam_get_region(region_id: str):
    store = _get_topology_store()
    region = store.get_region(region_id)
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    return region.model_dump()


@network_router.put("/ipam/regions/{region_id}")
async def ipam_update_region(region_id: str, body: dict):
    store = _get_topology_store()
    updated = store.update_region(region_id, **body)
    if not updated:
        raise HTTPException(status_code=404, detail="Region not found")
    return updated.model_dump()


@network_router.delete("/ipam/regions/{region_id}")
async def ipam_delete_region(region_id: str):
    store = _get_topology_store()
    store.delete_region(region_id)
    return {"status": "deleted", "region_id": region_id}


@network_router.get("/ipam/sites")
async def ipam_list_sites():
    store = _get_topology_store()
    sites = store.list_sites()
    return {"sites": [s.model_dump() for s in sites]}


@network_router.post("/ipam/sites")
async def ipam_create_site(body: dict):
    from src.network.models import Site
    store = _get_topology_store()
    site = Site(
        id=body.get("id", f"site-{uuid.uuid4().hex[:8]}"),
        name=body.get("name", ""),
        region_id=body.get("region_id", ""),
        site_type=body.get("site_type", ""),
        address=body.get("address", ""),
        description=body.get("description", ""),
    )
    store.add_site(site)
    return {"status": "created", "site": site.model_dump()}


@network_router.get("/ipam/sites/{site_id}")
async def ipam_get_site(site_id: str):
    store = _get_topology_store()
    site = store.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site.model_dump()


@network_router.put("/ipam/sites/{site_id}")
async def ipam_update_site(site_id: str, body: dict):
    store = _get_topology_store()
    updated = store.update_site(site_id, **body)
    if not updated:
        raise HTTPException(status_code=404, detail="Site not found")
    return updated.model_dump()


@network_router.delete("/ipam/sites/{site_id}")
async def ipam_delete_site(site_id: str):
    store = _get_topology_store()
    store.delete_site(site_id)
    return {"status": "deleted", "site_id": site_id}


@network_router.get("/ipam/address-blocks")
async def ipam_list_address_blocks():
    store = _get_topology_store()
    blocks = store.list_address_blocks()
    return {"blocks": [b.model_dump() for b in blocks]}


@network_router.post("/ipam/address-blocks")
async def ipam_create_address_block(body: dict):
    from src.network.models import AddressBlock
    store = _get_topology_store()
    block = AddressBlock(
        id=body.get("id", f"block-{uuid.uuid4().hex[:8]}"),
        cidr=body.get("cidr", ""),
        name=body.get("name", ""),
        vrf_id=body.get("vrf_id", "default"),
        site_id=body.get("site_id", ""),
        description=body.get("description", ""),
        rir=body.get("rir", "private"),
    )
    store.add_address_block(block)
    return {"status": "created", "block": block.model_dump()}


@network_router.get("/ipam/address-blocks/{block_id}")
async def ipam_get_address_block(block_id: str):
    store = _get_topology_store()
    block = store.get_address_block(block_id)
    if not block:
        raise HTTPException(status_code=404, detail="Address block not found")
    return block.model_dump()


@network_router.delete("/ipam/address-blocks/{block_id}")
async def ipam_delete_address_block(block_id: str):
    store = _get_topology_store()
    store.delete_address_block(block_id)
    return {"status": "deleted", "block_id": block_id}


@network_router.get("/ipam/address-blocks/{block_id}/utilization")
async def ipam_address_block_utilization(block_id: str):
    store = _get_topology_store()
    util = store.get_address_block_utilization(block_id)
    if util["total"] == 0:
        raise HTTPException(status_code=404, detail="Address block not found")
    return util


@network_router.post("/ipam/address-blocks/{block_id}/allocate")
async def ipam_allocate_subnet_from_block(block_id: str, body: dict):
    store = _get_topology_store()
    prefix = body.get("prefix")
    if prefix is None:
        raise HTTPException(status_code=400, detail="prefix is required")
    subnet = store.allocate_subnet_from_block(block_id, int(prefix))
    if not subnet:
        raise HTTPException(status_code=400, detail="No space available in block")
    return {"status": "allocated", "subnet": subnet.model_dump()}


# ---------------------------------------------------------------------------
# IPAM — VLAN Management
# ---------------------------------------------------------------------------

@network_router.get("/ipam/vlans")
async def ipam_list_vlans():
    store = _get_topology_store()
    vlans = store.list_vlans()
    return {"vlans": [v.model_dump() for v in vlans]}


@network_router.post("/ipam/vlans")
async def ipam_create_vlan(body: dict):
    from src.network.models import VLAN
    store = _get_topology_store()
    vlan = VLAN(
        id=body.get("id", f"vlan-{uuid.uuid4().hex[:8]}"),
        vlan_number=int(body.get("vlan_number", 1)),
        name=body.get("name", ""),
        site=body.get("site", ""),
        description=body.get("description", ""),
        vrf_id=body.get("vrf_id", "default"),
        site_id=body.get("site_id", ""),
        subnet_ids=body.get("subnet_ids", []),
    )
    store.add_vlan(vlan)
    return {"status": "created", "vlan": vlan.model_dump()}


@network_router.get("/ipam/vlans/{vlan_id}")
async def ipam_get_vlan(vlan_id: str):
    store = _get_topology_store()
    vlan = store.get_vlan(vlan_id)
    if not vlan:
        raise HTTPException(status_code=404, detail="VLAN not found")
    return vlan.model_dump()


@network_router.put("/ipam/vlans/{vlan_id}")
async def ipam_update_vlan(vlan_id: str, body: dict):
    store = _get_topology_store()
    updated = store.update_vlan(vlan_id, **body)
    if not updated:
        raise HTTPException(status_code=404, detail="VLAN not found")
    return updated.model_dump()


@network_router.delete("/ipam/vlans/{vlan_id}")
async def ipam_delete_vlan(vlan_id: str):
    store = _get_topology_store()
    store.delete_vlan(vlan_id)
    return {"status": "deleted", "vlan_id": vlan_id}


@network_router.get("/ipam/vlans/{vlan_id}/interfaces")
async def ipam_vlan_interfaces(vlan_id: str):
    store = _get_topology_store()
    ifaces = store.get_vlan_interfaces(vlan_id)
    return {"interfaces": [i.model_dump() for i in ifaces]}


# ---------------------------------------------------------------------------
# IPAM — IP Correlation
# ---------------------------------------------------------------------------

@network_router.get("/ipam/ips/{ip_id}/correlation")
async def ipam_ip_correlation(ip_id: str):
    store = _get_topology_store()
    chain = store.get_ip_correlation_chain(ip_id)
    if not chain:
        raise HTTPException(status_code=404, detail="IP not found")
    return chain


# ---------------------------------------------------------------------------
# IPAM — Cloud Accounts
# ---------------------------------------------------------------------------

@network_router.get("/ipam/cloud-accounts")
async def ipam_list_cloud_accounts():
    store = _get_topology_store()
    accounts = store.list_cloud_accounts()
    return {"accounts": [a.model_dump() for a in accounts]}


@network_router.post("/ipam/cloud-accounts")
async def ipam_create_cloud_account(body: dict):
    from src.network.models import CloudAccount, CloudProvider
    store = _get_topology_store()
    account = CloudAccount(
        id=body.get("id", f"cloud-{uuid.uuid4().hex[:8]}"),
        name=body.get("name", ""),
        provider=CloudProvider(body.get("provider", "aws")),
        account_id=body.get("account_id", ""),
        region=body.get("region", ""),
        credentials_ref=body.get("credentials_ref", ""),
        sync_enabled=body.get("sync_enabled", False),
    )
    store.add_cloud_account(account)
    return {"status": "created", "account": account.model_dump()}


@network_router.get("/ipam/cloud-accounts/{account_id}")
async def ipam_get_cloud_account(account_id: str):
    store = _get_topology_store()
    account = store.get_cloud_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Cloud account not found")
    return account.model_dump()


@network_router.put("/ipam/cloud-accounts/{account_id}")
async def ipam_update_cloud_account(account_id: str, body: dict):
    store = _get_topology_store()
    updated = store.update_cloud_account(account_id, **body)
    if not updated:
        raise HTTPException(status_code=404, detail="Cloud account not found")
    return updated.model_dump()


@network_router.delete("/ipam/cloud-accounts/{account_id}")
async def ipam_delete_cloud_account(account_id: str):
    store = _get_topology_store()
    store.delete_cloud_account(account_id)
    return {"status": "deleted", "account_id": account_id}


@network_router.post("/ipam/cloud-accounts/{account_id}/sync")
async def ipam_sync_cloud_account(account_id: str):
    """Trigger VPC/subnet sync for a cloud account (stub — requires cloud SDK)."""
    store = _get_topology_store()
    account = store.get_cloud_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Cloud account not found")
    now = datetime.now(timezone.utc).isoformat()
    store.update_cloud_account(account_id, last_sync=now)
    return {"status": "sync_triggered", "account_id": account_id, "last_sync": now}


# ---------------------------------------------------------------------------
# IPAM — Reports
# ---------------------------------------------------------------------------

@network_router.get("/ipam/reports/{report_type}")
async def ipam_report(report_type: str, format: str = "json", subnet_id: str = "", status: str = ""):
    """Generate IPAM report. Types: subnet_inventory, ip_allocation, conflict_report, capacity_forecast."""
    from src.network.ipam_reports import (
        generate_subnet_report, generate_ip_allocation_report,
        generate_conflict_report, generate_capacity_report, report_to_csv,
    )
    store = _get_topology_store()

    if report_type == "subnet_inventory":
        data = generate_subnet_report(store)
    elif report_type == "ip_allocation":
        data = generate_ip_allocation_report(store, subnet_id=subnet_id, status=status)
    elif report_type == "conflict_report":
        result = generate_conflict_report(store)
        if format == "json":
            return result
        data = result.get("duplicate_ips", []) + result.get("dns_mismatches", [])
    elif report_type == "capacity_forecast":
        data = generate_capacity_report(store)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown report type: {report_type}. Use: subnet_inventory, ip_allocation, conflict_report, capacity_forecast")

    if format == "csv":
        from starlette.responses import Response
        csv_data = report_to_csv(data)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=ipam_{report_type}.csv"},
        )

    return {"report_type": report_type, "generated_at": datetime.now(timezone.utc).isoformat(), "data": data, "count": len(data)}


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

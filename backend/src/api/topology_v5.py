"""V5 Topology API — semantic export with radial layout positions.

Exports topology data from the repository with group classification,
rank computation, and radial hub-spoke layout positions for ReactFlow.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository

router = APIRouter(prefix="/api/v5", tags=["topology-v5"])

# ── Group metadata ────────────────────────────────────────────────────────

GROUP_META: dict[str, dict] = {
    "onprem": {"label": "On-Premises DC", "accent": "#e09f3e"},
    "aws":    {"label": "AWS",            "accent": "#f59e0b"},
    "azure":  {"label": "Azure",          "accent": "#3b82f6"},
    "oci":    {"label": "Oracle Cloud",   "accent": "#ef4444"},
    "gcp":    {"label": "GCP",            "accent": "#10b981"},
    "branch": {"label": "Branch Offices", "accent": "#8b5cf6"},
}

# ── Pure helper functions (no FastAPI dependency) ─────────────────────────


def classify_group(device_data: dict) -> str:
    """Classify a device into a site/cloud group for visual grouping.

    ``device_data`` must contain at least ``site_id`` and ``hostname``.
    Optional keys: ``cloud_provider``, ``location``, ``region``.
    """
    site_id = (device_data.get("site_id") or "").lower()
    hostname = (device_data.get("hostname") or "").lower()
    cloud = (device_data.get("cloud_provider") or "").lower()
    location = (device_data.get("location") or "").lower()
    region = (device_data.get("region") or "").lower()
    combined = f"{site_id} {hostname} {location} {region}"

    # AWS
    if cloud == "aws" or "aws" in combined or "vpc-" in hostname or "tgw-" in hostname or "natgw-" in hostname or "igw-" in hostname or "csr-aws" in hostname:
        return "aws"
    # Azure
    if cloud == "azure" or "azure" in combined or "vwan-" in hostname or "vnet-" in hostname or "nva-azure" in hostname or "er-gw" in hostname:
        return "azure"
    # OCI
    if cloud == "oci" or "oci" in combined or "oracle" in combined or "vcn-" in hostname or "drg-" in hostname:
        return "oci"
    # GCP
    if cloud == "gcp" or "gcp" in combined:
        return "gcp"
    # Branch
    if "branch" in combined:
        return "branch"
    return "onprem"


def compute_rank(device_type: str, role: str) -> int:
    """Compute a hierarchical rank for layout ordering.

    Lower rank = higher in the visual hierarchy.
    """
    role_lower = (role or "").lower()
    if role_lower in ("core", "perimeter"):
        return 1
    if role_lower == "distribution":
        return 2
    if role_lower in ("edge", "access"):
        return 3

    # Fall back to device_type heuristics
    dt = (device_type or "").lower()
    if dt in ("router", "firewall", "vpn_gateway", "transit_gateway"):
        return 1
    if dt in ("switch", "load_balancer"):
        return 2
    if dt in ("host", "lambda", "access_point"):
        return 4
    return 3


def recommend_algorithm(node_count: int) -> str:
    """Recommend a layout algorithm based on graph size."""
    if node_count < 50:
        return "force_directed"
    return "hierarchical"


def _compute_topology_version(node_ids: list[str], edge_ids: list[str]) -> str:
    """Deterministic short hash from sorted node + edge IDs."""
    payload = json.dumps({"n": sorted(node_ids), "e": sorted(edge_ids)}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_topology_export(repo: SQLiteRepository, site_id: str | None = None, kg=None) -> dict:
    """Build the full v5 topology export from a repository instance.

    Returns a dict with nodes, edges, groups, layout_hints, and summary counts.
    Node and edge data shapes match V4 (LiveDeviceNode.tsx expectations).
    Radial layout positions (x, y, parentId) are computed and applied to each device node.

    If *kg* (NetworkKnowledgeGraph) is provided, edges are read from the
    knowledge graph (which has L2, L3, HA, tunnel, route, MPLS edges).
    Otherwise falls back to neighbor_links table.
    """
    # Access the underlying TopologyStore for Pydantic models (which have
    # role, cloud_provider, location, region, ha_role — fields absent from
    # the domain Device dataclass).
    store: TopologyStore = repo._store

    pydantic_devices = store.list_devices()
    if site_id:
        pydantic_devices = [d for d in pydantic_devices if (d.site_id or "") == site_id]

    # ── Optional metrics store ────────────────────────────────────────────
    metrics_store = None
    try:
        from src.network.sqlite_metrics_store import SQLiteMetricsStore
        metrics_store = SQLiteMetricsStore()
    except Exception:
        pass

    # ── Build nodes (V4-compatible data shape) ────────────────────────────
    nodes: list[dict] = []
    node_ids: list[str] = []
    group_counts: dict[str, int] = {}

    for pdev in pydantic_devices:
        dt_val = pdev.device_type.value if hasattr(pdev.device_type, "value") else str(pdev.device_type)

        device_data = {
            "site_id": pdev.site_id or "",
            "hostname": pdev.name or "",
            "cloud_provider": pdev.cloud_provider or "",
            "location": pdev.location or "",
            "region": pdev.region or "",
        }
        group = classify_group(device_data)
        rank = compute_rank(dt_val, pdev.role or "")

        # Interfaces from store
        device_ifaces = store.list_interfaces(device_id=pdev.id)
        interfaces_data = [
            {
                "id": iface.id,
                "name": iface.name,
                "ip": iface.ip,
                "role": iface.role,
                "zone": iface.zone_id,
                "operStatus": iface.oper_status,
                "adminStatus": iface.admin_status,
            }
            for iface in device_ifaces
        ]

        node_data = {
            "label": pdev.name or pdev.id,
            "entityId": pdev.id,
            "deviceType": dt_val.upper(),
            "ip": pdev.management_ip or "",
            "vendor": pdev.vendor or "",
            "role": pdev.role or "",
            "group": group,
            "status": "initializing",
            "haRole": pdev.ha_role or "",
            "location": pdev.location or "",
            "osVersion": pdev.os_version or "",
            "interfaces": interfaces_data,
            # Metrics placeholders
            "cpuPct": None,
            "memoryPct": None,
            "sessionCount": None,
            "sessionMax": None,
            "threatHits": None,
            "sslTps": None,
            "poolHealth": None,
            "bgpPeers": None,
            "routeCount": None,
        }

        # Enrich from metrics store if available
        if metrics_store is not None:
            try:
                cpu = metrics_store.get_latest_device_metric(pdev.id, "cpu_pct")
                memory = metrics_store.get_latest_device_metric(pdev.id, "memory_pct")
                node_data["cpuPct"] = round(cpu, 1) if cpu is not None else None
                node_data["memoryPct"] = round(memory, 1) if memory is not None else None

                dt_lower = dt_val.lower()
                if dt_lower == "firewall":
                    sc = metrics_store.get_latest_device_metric(pdev.id, "session_count")
                    sm = metrics_store.get_latest_device_metric(pdev.id, "session_max")
                    th = metrics_store.get_latest_device_metric(pdev.id, "threat_hits")
                    node_data["sessionCount"] = int(sc) if sc is not None else None
                    node_data["sessionMax"] = int(sm) if sm is not None else None
                    node_data["threatHits"] = int(th) if th is not None else None
                elif dt_lower == "load_balancer":
                    st = metrics_store.get_latest_device_metric(pdev.id, "ssl_tps")
                    ph = metrics_store.get_latest_device_metric(pdev.id, "pool_health")
                    node_data["sslTps"] = int(st) if st is not None else None
                    node_data["poolHealth"] = round(ph, 1) if ph is not None else None
                elif dt_lower == "router":
                    bp = metrics_store.get_latest_device_metric(pdev.id, "bgp_peers")
                    rc = metrics_store.get_latest_device_metric(pdev.id, "route_count")
                    node_data["bgpPeers"] = int(bp) if bp is not None else None
                    node_data["routeCount"] = int(rc) if rc is not None else None

                # Derive status from metrics
                if cpu is not None or memory is not None:
                    node_data["status"] = "healthy"
                    if (cpu is not None and cpu > 90) or (memory is not None and memory > 90):
                        node_data["status"] = "critical"
                    elif (cpu is not None and cpu > 70) or (memory is not None and memory > 70):
                        node_data["status"] = "warning"
            except Exception:
                pass

        node = {
            "id": pdev.id,
            "type": "device",
            "data": node_data,
            # Preserved for layout engine (Task 3/4)
            "rank": rank,
        }
        nodes.append(node)
        node_ids.append(pdev.id)
        group_counts[group] = group_counts.get(group, 0) + 1

    # ── Edge style constants ──────────────────────────────────────────────
    EDGE_STYLES = {
        "physical":      {"stroke": "#22c55e", "strokeWidth": 3},
        "ha_peer":       {"stroke": "#f59e0b", "strokeWidth": 2, "strokeDasharray": "6,4"},
        "tunnel":        {"stroke": "#06b6d4", "strokeWidth": 3, "strokeDasharray": "10,5"},
        "route":         {"stroke": "#64748b", "strokeWidth": 1, "opacity": 0.3},
        "cloud_attach":  {"stroke": "#06b6d4", "strokeWidth": 3},
        "load_balancer": {"stroke": "#a855f7", "strokeWidth": 2},
        "mpls":          {"stroke": "#f59e0b", "strokeWidth": 4},
    }

    # Map edge_type protocols to frontend edge categories
    EDGE_TYPE_MAP = {
        "layer2_link": "physical",
        "layer3_link": "physical",
        "LLDP": "physical",
        "CDP": "physical",
        "lldp": "physical",
        "cdp": "physical",
        "l3_p2p": "physical",
        "ha_peer": "ha_peer",
        "active_passive": "ha_peer",
        "active_active": "ha_peer",
        "vrrp": "ha_peer",
        "cluster": "ha_peer",
        "tunnel_link": "tunnel",
        "ipsec": "tunnel",
        "gre": "tunnel",
        "vxlan": "tunnel",
        "mpls_path": "mpls",
        "MPLS": "mpls",
        "routes_via": "route",
        "bgp": "route",
        "BGP": "route",
        "ospf": "route",
        "OSPF": "route",
        "eigrp": "route",
        "static": "route",
        "is-is": "route",
        "attached_to": "cloud_attach",
        "tgw": "cloud_attach",
        "load_balances": "load_balancer",
        "lb": "load_balancer",
    }

    # ── Build edges (V4-compatible data shape) ────────────────────────────
    from src.network.repository.edge_builder import EdgeBuilderService
    edge_builder = EdgeBuilderService(store)
    all_neighbor_links = edge_builder.build_all()

    # Persist edges to neighbor_links table (so subsequent reads are fast)
    for link in all_neighbor_links:
        try:
            repo.upsert_neighbor_link(link)
        except Exception:
            pass  # Best-effort persist

    node_id_set = set(node_ids)
    edges: list[dict] = []
    edge_ids: list[str] = []
    seen_edges: set[str] = set()

    for link in all_neighbor_links:
        if link.device_id not in node_id_set or link.remote_device not in node_id_set:
            continue

        pair = tuple(sorted([link.device_id, link.remote_device]))
        dedup_key = f"{pair[0]}--{pair[1]}--{link.protocol}"
        if dedup_key in seen_edges:
            continue
        seen_edges.add(dedup_key)

        edge_type = EDGE_TYPE_MAP.get(link.protocol, "physical")
        style = dict(EDGE_STYLES.get(edge_type, EDGE_STYLES["physical"]))

        # Extract interface names from link IDs (device_id:iface_name -> iface_name)
        src_iface_name = link.local_interface.split(":", 1)[1] if ":" in link.local_interface else link.local_interface
        dst_iface_name = link.remote_interface.split(":", 1)[1] if ":" in link.remote_interface else link.remote_interface

        # Get interface speed from store
        speed_str = ""
        try:
            ifaces = store.list_interfaces(device_id=link.device_id)
            for iface in ifaces:
                if iface.name == src_iface_name:
                    speed_str = iface.speed or ""
                    break
        except Exception:
            pass

        # WAN edges get larger labels
        is_wan = edge_type in ("mpls", "tunnel", "cloud_attach")
        label_size = 10 if is_wan else 8
        label_fill = "#94a3b8" if is_wan else "#64748b"

        edge = {
            "id": link.id,
            "source": link.device_id,
            "target": link.remote_device,
            "type": "smoothstep",
            "label": speed_str,
            "labelStyle": {"fontSize": label_size, "fill": label_fill, "fontWeight": 600 if is_wan else 400},
            "labelBgStyle": {"fill": "#1a1814", "fillOpacity": 0.8},
            "labelBgPadding": [4, 2],
            "data": {
                "edgeType": edge_type,
                "srcInterface": src_iface_name,
                "dstInterface": dst_iface_name,
                "protocol": link.protocol,
                "status": "up",
                "utilization": None,
                "speed": speed_str,
            },
            "style": style,
            "animated": edge_type == "tunnel",
        }
        edges.append(edge)
        edge_ids.append(link.id)

    # Groups summary
    groups: list[dict] = []
    for group_id, count in sorted(group_counts.items()):
        meta = GROUP_META.get(group_id, {"label": group_id.title(), "accent": "#6b7280"})
        groups.append({
            "id": group_id,
            "label": meta["label"],
            "accent": meta["accent"],
            "device_count": count,
        })

    # ── Radial layout: compute positions + group containers ───────────
    from src.network.repository.radial_layout import compute_radial_layout

    # Prepare device data for layout computation
    layout_devices = []
    for node in nodes:
        d = node["data"]
        layout_devices.append({
            "id": node["id"],
            "group": d.get("group", "onprem"),
            "role": d.get("role", ""),
            "deviceType": d.get("deviceType", "HOST"),
            "label": d.get("label", node["id"]),
        })

    # Compute layout
    layout = compute_radial_layout(layout_devices)

    # Apply positions and parentId to device nodes
    device_nodes = nodes  # alias for clarity
    for node in device_nodes:
        pos_info = layout["device_positions"].get(node["id"])
        if pos_info:
            node["position"] = {"x": pos_info["x"], "y": pos_info["y"]}
            if "parentId" in pos_info:
                node["parentId"] = pos_info["parentId"]
        else:
            node["position"] = {"x": 0, "y": 0}

    # Build final node list: groups first, then env labels, then devices
    # (ReactFlow requires parent nodes before children in the array)
    all_nodes = layout["group_nodes"] + layout["env_labels"] + device_nodes

    topology_version = _compute_topology_version(node_ids, edge_ids)

    return {
        "nodes": all_nodes,
        "edges": edges,
        "groups": groups,
        "layout_hints": {
            "algorithm": recommend_algorithm(len(device_nodes)),
            "grouping": "site",
        },
        "topology_version": topology_version,
        "device_count": len(device_nodes),
        "edge_count": len(edges),
    }


# ── Repository dependency ─────────────────────────────────────────────────


def _get_repo() -> SQLiteRepository:
    """Create a SQLiteRepository backed by the default TopologyStore."""
    store = TopologyStore()  # uses default DB path
    return SQLiteRepository(store)


# ── Endpoint ──────────────────────────────────────────────────────────────


# ── Module-level WebSocket publisher singleton ────────────────────────────

_ws_publisher = None


def get_ws_publisher():
    """Return (or lazily create) the singleton WebSocketTopologyPublisher."""
    global _ws_publisher
    if _ws_publisher is None:
        from src.network.event_bus.websocket_publisher import WebSocketTopologyPublisher
        _ws_publisher = WebSocketTopologyPublisher()
    return _ws_publisher


@router.websocket("/topology/stream")
async def topology_stream(websocket: WebSocket):
    """Real-time topology delta stream over WebSocket."""
    await websocket.accept()
    client_id = str(uuid.uuid4())
    publisher = get_ws_publisher()
    publisher.register(client_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep-alive
    except WebSocketDisconnect:
        publisher.unregister(client_id)
    except Exception:
        publisher.unregister(client_id)


@router.get("/topology")
def get_topology_v5(site_id: Optional[str] = Query(default=None)):
    """Export the full topology graph with radial layout positions.

    Each device node includes ``position: {x, y}`` and ``parentId`` for
    ReactFlow group nesting.  Group containers and env labels are prepended.
    """
    repo = _get_repo()
    return build_topology_export(repo, site_id=site_id)

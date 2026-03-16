"""V5 Topology API — semantic export with layout hints, no pixel coordinates.

Exports topology data from the repository with group classification,
rank computation, and algorithm recommendations so the frontend layout
engine can make its own positioning decisions.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Query

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


def build_topology_export(repo: SQLiteRepository, site_id: str | None = None) -> dict:
    """Build the full v5 topology export from a repository instance.

    Returns a dict with nodes, edges, groups, layout_hints, and summary counts.
    No pixel positions are included.
    """
    # Access the underlying TopologyStore for Pydantic models (which have
    # role, cloud_provider, location, region, ha_role — fields absent from
    # the domain Device dataclass).
    store: TopologyStore = repo._store

    pydantic_devices = store.list_devices()
    if site_id:
        pydantic_devices = [d for d in pydantic_devices if (d.site_id or "") == site_id]

    # Build nodes
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

        node = {
            "id": pdev.id,
            "hostname": pdev.name or pdev.id,
            "vendor": pdev.vendor or "",
            "device_type": dt_val.upper(),
            "site_id": pdev.site_id or "",
            "group": group,
            "rank": rank,
            "status": "healthy",
            "confidence": 0.9,
            "ha_role": pdev.ha_role if pdev.ha_role else None,
            "metrics": {},
        }
        nodes.append(node)
        node_ids.append(pdev.id)
        group_counts[group] = group_counts.get(group, 0) + 1

    # Build edges from neighbor links
    all_links = store.list_neighbor_links()
    # Filter to only links whose both endpoints are in the current node set
    node_id_set = set(node_ids)
    edges: list[dict] = []
    edge_ids: list[str] = []
    seen_edges: set[str] = set()

    for link in all_links:
        device_id = link["device_id"]
        remote_device = link["remote_device"]

        # Both endpoints must be in scope
        if device_id not in node_id_set or remote_device not in node_id_set:
            continue

        # Dedup: normalise edge key so A→B and B→A collapse
        pair = tuple(sorted([device_id, remote_device]))
        local_iface = link.get("local_interface", "")
        remote_iface = link.get("remote_interface", "")
        dedup_key = f"{pair[0]}:{local_iface}--{pair[1]}:{remote_iface}" if pair[0] == device_id else f"{pair[0]}:{remote_iface}--{pair[1]}:{local_iface}"

        if dedup_key in seen_edges:
            continue
        seen_edges.add(dedup_key)

        edge_id = f"e-{device_id}:{local_iface}--{remote_device}:{remote_iface}"
        edge = {
            "id": edge_id,
            "source": device_id,
            "target": remote_device,
            "source_interface": f"{device_id}:{local_iface}" if local_iface else device_id,
            "target_interface": f"{remote_device}:{remote_iface}" if remote_iface else remote_device,
            "edge_type": "physical",
            "protocol": link.get("protocol", "lldp"),
            "confidence": link.get("confidence", 0.5),
        }
        edges.append(edge)
        edge_ids.append(edge_id)

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

    topology_version = _compute_topology_version(node_ids, edge_ids)

    return {
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
        "layout_hints": {
            "algorithm": recommend_algorithm(len(nodes)),
            "grouping": "site",
        },
        "topology_version": topology_version,
        "device_count": len(nodes),
        "edge_count": len(edges),
    }


# ── Repository dependency ─────────────────────────────────────────────────


def _get_repo() -> SQLiteRepository:
    """Create a SQLiteRepository backed by the default TopologyStore."""
    store = TopologyStore()  # uses default DB path
    return SQLiteRepository(store)


# ── Endpoint ──────────────────────────────────────────────────────────────


@router.get("/topology")
def get_topology_v5(site_id: Optional[str] = Query(default=None)):
    """Export the full topology graph with semantic data and layout hints.

    NO pixel positions are included — the frontend layout engine decides
    coordinates using the ``layout_hints.algorithm`` recommendation and
    per-node ``rank`` / ``group`` metadata.
    """
    repo = _get_repo()
    return build_topology_export(repo, site_id=site_id)

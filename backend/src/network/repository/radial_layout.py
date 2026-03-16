"""
Semantic force-directed layout for enterprise network topology.

Uses NetworkX spring_layout with edge weights derived from connection
semantics. Connected devices attract each other — physical links pull
strongly, WAN links pull weakly. Devices in the same cloud group have
a gentle clustering force.

Result: devices position themselves naturally based on connectivity.
On-prem core clusters in the center (most connections). Cloud groups
orbit based on their actual WAN connection points. No hardcoded
columns or tiers.
"""

from __future__ import annotations

import logging
import networkx as nx

logger = logging.getLogger(__name__)

# ── Visual constants ─────────────────────────────────────────────────

NODE_W = 170
NODE_H = 80
CANVAS_SCALE = 260     # multiplier for spring_layout coordinates → pixels
CANVAS_OFFSET_X = 1800  # shift so nothing is at negative coords
CANVAS_OFFSET_Y = 1000

GROUP_LABELS: dict[str, str] = {
    "onprem": "ON-PREMISES DC",
    "aws": "AWS",
    "azure": "AZURE",
    "oci": "ORACLE CLOUD",
    "gcp": "GCP",
    "branch": "BRANCH",
}

GROUP_ACCENTS: dict[str, str] = {
    "onprem": "#e09f3e",
    "aws": "#f59e0b",
    "azure": "#3b82f6",
    "oci": "#ef4444",
    "gcp": "#10b981",
    "branch": "#8b5cf6",
}

# ── Edge weight by connection type ───────────────────────────────────
# Lower weight = stronger attraction = closer together.
# Physical links pull strongly (devices are in same rack/room).
# WAN links pull weakly (devices are geographically distant).

EDGE_WEIGHT: dict[str, float] = {
    # Physical / L2 / L3 — very close
    "LLDP": 0.8,
    "CDP": 0.8,
    "l3_p2p": 0.9,
    "layer2_link": 0.8,
    "layer3_link": 0.9,
    # HA pairs — extremely close (same chassis/rack)
    "active_passive": 0.3,
    "active_active": 0.3,
    "vrrp": 0.3,
    "cluster": 0.3,
    # LB → backend — close
    "lb": 1.0,
    "load_balances": 1.0,
    # Cloud attachment (TGW→VPC) — medium
    "tgw": 1.5,
    "attached_to": 1.5,
    "cloud_gw": 1.5,
    "vnet_peering": 1.5,
    "nva": 1.2,
    "drg": 1.5,
    # Inferred link — medium
    "inferred": 1.5,
    # Routing adjacency — weak (logical, not physical)
    "bgp": 2.5,
    "BGP": 2.5,
    "ospf": 2.0,
    "static": 2.0,
    # WAN links — very weak (long distance)
    "MPLS": 3.5,
    "mpls_path": 3.5,
    "gre": 3.0,
    "ipsec": 3.0,
    "vxlan": 2.5,
}

# Group attraction — devices in same group get a gentle pull
GROUP_ATTRACTION = 1.8


def compute_radial_layout(
    devices: list[dict],
    group_classify_fn=None,
    edges: list = None,
) -> dict:
    """
    Compute force-directed layout using semantic edge weights.

    Despite the function name (kept for backward compat), this now uses
    NetworkX spring_layout, not a radial algorithm.
    """
    if not devices:
        return {"device_positions": {}, "group_nodes": [], "env_labels": [], "groups_found": {}}

    # 1. Build device lookup
    dev_map = {d["id"]: d for d in devices}
    groups_found: dict[str, list[dict]] = {}
    for dev in devices:
        g = group_classify_fn(dev) if group_classify_fn else dev.get("group", "onprem")
        groups_found.setdefault(g, []).append(dev)

    # 2. Build NetworkX graph with semantic weights
    G = nx.Graph()

    for dev in devices:
        G.add_node(dev["id"], group=dev.get("group", "onprem"))

    # Add real edges from EdgeBuilder (passed in or empty)
    if edges:
        for e in edges:
            src = e.device_id if hasattr(e, 'device_id') else e.get("device_id", "")
            dst = e.remote_device if hasattr(e, 'remote_device') else e.get("remote_device", "")
            proto = e.protocol if hasattr(e, 'protocol') else e.get("protocol", "")
            if src in dev_map and dst in dev_map:
                w = EDGE_WEIGHT.get(proto, 1.5)
                # If edge already exists, use minimum weight (strongest pull wins)
                if G.has_edge(src, dst):
                    existing_w = G[src][dst].get("weight", 99)
                    w = min(w, existing_w)
                G.add_edge(src, dst, weight=w)

    # Add soft group clustering edges (invisible, just for layout force)
    for gid, group_devs in groups_found.items():
        for i in range(len(group_devs)):
            for j in range(i + 1, len(group_devs)):
                a = group_devs[i]["id"]
                b = group_devs[j]["id"]
                if not G.has_edge(a, b):
                    G.add_edge(a, b, weight=GROUP_ATTRACTION)

    # 3. Run spring layout
    # k = optimal distance between nodes. Higher = more spread.
    # iterations = more = better convergence.
    k_value = 3.0 if len(devices) < 20 else 4.0 if len(devices) < 50 else 5.0
    pos = nx.spring_layout(
        G,
        k=k_value,
        iterations=200,
        weight="weight",
        seed=42,  # deterministic
    )

    # 4. Scale to pixel coordinates
    device_positions: dict[str, dict] = {}
    for dev_id, (x, y) in pos.items():
        device_positions[dev_id] = {
            "x": int(x * CANVAS_SCALE * len(devices) / 8 + CANVAS_OFFSET_X),
            "y": int(y * CANVAS_SCALE * len(devices) / 8 + CANVAS_OFFSET_Y),
        }

    # 5. Prevent overlap: push apart any nodes that are too close
    _resolve_overlaps(device_positions, min_dx=NODE_W + 15, min_dy=NODE_H + 10)

    # 6. Create group backgrounds + env labels from actual device positions
    group_nodes: list[dict] = []
    env_labels: list[dict] = []

    for gid, group_devs in groups_found.items():
        member_ids = [d["id"] for d in group_devs]
        member_positions = [device_positions[mid] for mid in member_ids if mid in device_positions]
        if not member_positions:
            continue

        accent = GROUP_ACCENTS.get(gid, "#64748b")
        pad = 35

        # Bounding box from actual positions (after force-directed + overlap resolution)
        min_x = min(p["x"] for p in member_positions) - pad
        min_y = min(p["y"] for p in member_positions) - pad
        max_x = max(p["x"] for p in member_positions) + NODE_W + pad
        max_y = max(p["y"] for p in member_positions) + NODE_H + pad

        gw = max_x - min_x
        gh = max_y - min_y

        group_nodes.append({
            "id": f"group-{gid}",
            "type": "group",
            "data": {"label": GROUP_LABELS.get(gid, gid)},
            "position": {"x": min_x, "y": min_y},
            "style": {
                "width": gw,
                "height": gh,
                "backgroundColor": f"{accent}08",
                "border": f"1px solid {accent}20",
                "borderRadius": 10,
                "padding": 0,
                "pointerEvents": "none",
            },
            "selectable": False,
            "draggable": False,
            "zIndex": -1,
        })

        # Env label above group
        env_labels.append({
            "id": f"env-label-{gid}",
            "type": "envLabel",
            "data": {
                "label": GROUP_LABELS.get(gid, gid),
                "envType": gid,
                "accent": accent,
                "deviceCount": len(group_devs),
            },
            "position": {"x": min_x + gw // 2 - 80, "y": min_y - 55},
            "selectable": False,
            "draggable": False,
        })

    return {
        "device_positions": device_positions,
        "group_nodes": group_nodes,
        "env_labels": env_labels,
        "groups_found": groups_found,
    }


def _resolve_overlaps(positions: dict[str, dict], min_dx: int, min_dy: int,
                       max_iterations: int = 50) -> None:
    """Push overlapping nodes apart iteratively."""
    ids = list(positions.keys())
    for _ in range(max_iterations):
        moved = False
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a = positions[ids[i]]
                b = positions[ids[j]]
                dx = abs(a["x"] - b["x"])
                dy = abs(a["y"] - b["y"])
                if dx < min_dx and dy < min_dy:
                    # Push apart
                    push_x = (min_dx - dx) // 2 + 1
                    push_y = (min_dy - dy) // 2 + 1
                    if a["x"] <= b["x"]:
                        a["x"] -= push_x
                        b["x"] += push_x
                    else:
                        a["x"] += push_x
                        b["x"] -= push_x
                    if a["y"] <= b["y"]:
                        a["y"] -= push_y
                        b["y"] += push_y
                    else:
                        a["y"] += push_y
                        b["y"] -= push_y
                    moved = True
        if not moved:
            break

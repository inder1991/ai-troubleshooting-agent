"""
Two-phase semantic layout for enterprise network topology.

Phase 1: Position GROUP CENTROIDS using force-directed layout.
  Only 5 nodes (one per group). Edge weight = number of cross-group
  connections. Result: groups with more interconnections are closer.

Phase 2: Within each group's region, arrange devices in a CLEAN GRID
  sorted by tier (perimeter → core → distribution → access, top to bottom).

Result: clean separation between groups + clean tiers within groups +
cross-group positioning driven by actual connectivity.
"""

from __future__ import annotations

import logging
import math
import networkx as nx

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

NODE_W = 170
NODE_H = 80
H_GAP = 25           # between nodes in same tier row
V_GAP = 35           # between tier rows
GROUP_PAD = 45        # padding inside group box
GROUP_GAP = 100       # minimum gap between group boxes
LABEL_HEIGHT = 55     # space for env label above group

# ── Tier assignment ──────────────────────────────────────────────────

ROLE_TO_TIER: dict[str, int] = {
    "perimeter": 0,
    "cloud_gateway": 0,
    "core": 1,
    "distribution": 2,
    "edge": 2,
    "access": 3,
}

TYPE_TO_TIER: dict[str, int] = {
    "TRANSIT_GATEWAY": 0, "CLOUD_GATEWAY": 0, "NAT_GATEWAY": 0,
    "FIREWALL": 1, "ROUTER": 1, "VPN_CONCENTRATOR": 1,
    "LOAD_BALANCER": 2, "PROXY": 2, "VIRTUAL_APPLIANCE": 2, "SDWAN_EDGE": 2,
    "SWITCH": 3, "HOST": 3,
}

# ── Group metadata ───────────────────────────────────────────────────

GROUP_LABELS: dict[str, str] = {
    "onprem": "ON-PREMISES DC", "aws": "AWS", "azure": "AZURE",
    "oci": "ORACLE CLOUD", "gcp": "GCP", "branch": "BRANCH",
}

GROUP_ACCENTS: dict[str, str] = {
    "onprem": "#e09f3e", "aws": "#f59e0b", "azure": "#3b82f6",
    "oci": "#ef4444", "gcp": "#10b981", "branch": "#8b5cf6",
}


def _get_tier(dev: dict) -> int:
    role = (dev.get("role") or "").lower()
    if role in ROLE_TO_TIER:
        return ROLE_TO_TIER[role]
    dt = (dev.get("deviceType") or "HOST").upper()
    return TYPE_TO_TIER.get(dt, 3)


# ── Main entry point ────────────────────────────────────────────────

def compute_radial_layout(
    devices: list[dict],
    group_classify_fn=None,
    edges: list = None,
) -> dict:
    if not devices:
        return {"device_positions": {}, "group_nodes": [], "env_labels": [], "groups_found": {}}

    # ── Classify devices into groups ─────────────────────────────────
    groups_found: dict[str, list[dict]] = {}
    for dev in devices:
        g = group_classify_fn(dev) if group_classify_fn else dev.get("group", "onprem")
        groups_found.setdefault(g, []).append(dev)

    # ── PHASE 1: Position group centroids ────────────────────────────
    # Build a graph of groups where edge weight = cross-group connection count
    group_graph = nx.Graph()
    for gid in groups_found:
        group_graph.add_node(gid)

    if edges:
        dev_to_group = {}
        for dev in devices:
            g = group_classify_fn(dev) if group_classify_fn else dev.get("group", "onprem")
            dev_to_group[dev["id"]] = g

        # Count cross-group edges
        cross_counts: dict[tuple, int] = {}
        for e in edges:
            src = e.device_id if hasattr(e, 'device_id') else e.get("device_id", "")
            dst = e.remote_device if hasattr(e, 'remote_device') else e.get("remote_device", "")
            g1 = dev_to_group.get(src)
            g2 = dev_to_group.get(dst)
            if g1 and g2 and g1 != g2:
                pair = tuple(sorted([g1, g2]))
                cross_counts[pair] = cross_counts.get(pair, 0) + 1

        for (g1, g2), count in cross_counts.items():
            # More connections = smaller weight = closer together
            weight = max(0.3, 2.0 / count)
            group_graph.add_edge(g1, g2, weight=weight)

    # Run spring layout on group graph
    if len(groups_found) == 1:
        gid = list(groups_found.keys())[0]
        group_centers = {gid: (0.0, 0.0)}
    else:
        group_pos = nx.spring_layout(
            group_graph, k=3.0, iterations=100, weight="weight", seed=42
        )
        group_centers = {gid: (x, y) for gid, (x, y) in group_pos.items()}

    # ── PHASE 2: Compute group dimensions from device tiers ──────────
    # For each group, assign tiers and compute the grid dimensions

    group_dims: dict[str, dict] = {}  # gid → {width, height, tiers: {tier: [devs]}}

    for gid, group_devs in groups_found.items():
        tiers: dict[int, list[dict]] = {}
        for dev in group_devs:
            t = _get_tier(dev)
            tiers.setdefault(t, []).append(dev)
        # Sort within tiers
        for t in tiers:
            tiers[t].sort(key=lambda d: d.get("label", d.get("id", "")))

        # Compute grid dimensions
        max_tier_width = 0
        total_height = 0
        tier_info: list[tuple[int, int, int]] = []  # (tier_num, cols, rows)

        for t in sorted(tiers.keys()):
            n = len(tiers[t])
            cols = min(n, 2)  # max 2 per row for readability
            rows = math.ceil(n / max(cols, 1))
            tw = cols * (NODE_W + H_GAP) - H_GAP
            th = rows * (NODE_H + 12) - 12
            max_tier_width = max(max_tier_width, tw)
            tier_info.append((t, tw, th))
            total_height += th + V_GAP

        total_height = max(total_height - V_GAP, NODE_H)
        inner_w = max(max_tier_width, NODE_W)
        inner_h = total_height

        group_dims[gid] = {
            "inner_w": inner_w,
            "inner_h": inner_h,
            "outer_w": inner_w + 2 * GROUP_PAD,
            "outer_h": inner_h + 2 * GROUP_PAD,
            "tiers": tiers,
            "tier_info": tier_info,
        }

    # ── Scale group centers to pixel positions with separation ────────
    # Find scale factor that separates groups enough
    max_dim = max(
        max(d["outer_w"] for d in group_dims.values()),
        max(d["outer_h"] for d in group_dims.values()),
    )
    scale = (max_dim + GROUP_GAP) * 1.2

    group_pixel_centers: dict[str, tuple[int, int]] = {}
    for gid, (cx, cy) in group_centers.items():
        px = int(cx * scale + 1500)  # offset to keep positive coords
        py = int(cy * scale + 1000)
        group_pixel_centers[gid] = (px, py)

    # ── Resolve group overlaps ───────────────────────────────────────
    _resolve_group_overlaps(group_pixel_centers, group_dims, min_gap=GROUP_GAP)

    # ── Place devices within each group ──────────────────────────────
    device_positions: dict[str, dict] = {}

    for gid, (gcx, gcy) in group_pixel_centers.items():
        dims = group_dims[gid]
        tiers = dims["tiers"]

        # Group box top-left
        box_x = gcx - dims["outer_w"] // 2
        box_y = gcy - dims["outer_h"] // 2

        # Inner content area
        content_x = box_x + GROUP_PAD
        content_y = box_y + GROUP_PAD

        # Place devices tier by tier, top to bottom
        y_cursor = content_y
        for t in sorted(tiers.keys()):
            tier_devs = tiers[t]
            n = len(tier_devs)
            cols = min(n, 2)
            rows = math.ceil(n / max(cols, 1))
            tier_w = cols * (NODE_W + H_GAP) - H_GAP

            # Center tier within group width
            tier_x = content_x + (dims["inner_w"] - tier_w) // 2

            for idx, dev in enumerate(tier_devs):
                col = idx % cols
                row = idx // cols
                device_positions[dev["id"]] = {
                    "x": tier_x + col * (NODE_W + H_GAP),
                    "y": y_cursor + row * (NODE_H + 12),
                }

            row_count = math.ceil(n / max(cols, 1))
            y_cursor += row_count * (NODE_H + 12) - 12 + V_GAP

    # ── Build group container nodes ──────────────────────────────────
    group_nodes: list[dict] = []
    env_labels: list[dict] = []

    for gid, (gcx, gcy) in group_pixel_centers.items():
        dims = group_dims[gid]
        accent = GROUP_ACCENTS.get(gid, "#64748b")

        box_x = gcx - dims["outer_w"] // 2
        box_y = gcy - dims["outer_h"] // 2

        group_nodes.append({
            "id": f"group-{gid}",
            "type": "group",
            "data": {"label": GROUP_LABELS.get(gid, gid)},
            "position": {"x": box_x, "y": box_y},
            "style": {
                "width": dims["outer_w"],
                "height": dims["outer_h"],
                "backgroundColor": f"{accent}08",
                "border": f"1.5px solid {accent}25",
                "borderRadius": 10,
                "padding": 0,
                "pointerEvents": "none",
            },
            "selectable": False,
            "draggable": False,
            "zIndex": -1,
        })

        env_labels.append({
            "id": f"env-label-{gid}",
            "type": "envLabel",
            "data": {
                "label": GROUP_LABELS.get(gid, gid),
                "envType": gid,
                "accent": accent,
                "deviceCount": len(groups_found[gid]),
            },
            "position": {
                "x": box_x + dims["outer_w"] // 2 - 80,
                "y": box_y - LABEL_HEIGHT,
            },
            "selectable": False,
            "draggable": False,
        })

    return {
        "device_positions": device_positions,
        "group_nodes": group_nodes,
        "env_labels": env_labels,
        "groups_found": groups_found,
    }


def _resolve_group_overlaps(
    centers: dict[str, tuple[int, int]],
    dims: dict[str, dict],
    min_gap: int,
    max_iter: int = 80,
) -> None:
    """Push overlapping group bounding boxes apart."""
    ids = list(centers.keys())
    for _ in range(max_iter):
        moved = False
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                ax, ay = centers[a]
                bx, by = centers[b]
                aw = dims[a]["outer_w"] + min_gap
                ah = dims[a]["outer_h"] + min_gap
                bw = dims[b]["outer_w"] + min_gap
                bh = dims[b]["outer_h"] + min_gap

                # Check overlap
                half_w = (aw + bw) / 2
                half_h = (ah + bh) / 2
                dx = abs(ax - bx)
                dy = abs(ay - by)

                if dx < half_w and dy < half_h:
                    # Push apart along the axis with less overlap
                    overlap_x = half_w - dx
                    overlap_y = half_h - dy
                    push = max(overlap_x, overlap_y) // 2 + 5

                    if overlap_x < overlap_y:
                        # Push horizontally
                        if ax <= bx:
                            centers[a] = (ax - push, ay)
                            centers[b] = (bx + push, by)
                        else:
                            centers[a] = (ax + push, ay)
                            centers[b] = (bx - push, by)
                    else:
                        # Push vertically
                        if ay <= by:
                            centers[a] = (ax, ay - push)
                            centers[b] = (ax, by + push)
                        else:
                            centers[a] = (ax, ay + push)
                            centers[b] = (ax, by - push)
                    moved = True
        if not moved:
            break

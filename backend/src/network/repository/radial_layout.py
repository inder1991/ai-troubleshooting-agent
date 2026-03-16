"""
Radial hub-spoke layout algorithm for network topology visualization.

Extracted from KnowledgeGraph.export_react_flow_graph() so it can be
reused by any API that needs to produce ReactFlow-compatible positions.
"""

from __future__ import annotations

import math

# ── Canvas constants ──────────────────────────────────────────────────
CENTER_X = 1200
CENTER_Y = 800
INNER_RADIUS = 350
OUTER_RADIUS = 900
NODE_W = 180
NODE_H = 80

# Angles for outer groups (degrees, math convention: 0=right, 90=up).
# Y is negated in code to convert to screen coords (Y-down).
OUTER_ANGLES: dict[str, int] = {
    "aws": 0,
    "azure": 180,
    "oci": 240,
    "gcp": 60,
    "branch": 310,
}

GROUP_LABELS: dict[str, str] = {
    "onprem": "On-Premises DC",
    "aws": "AWS",
    "azure": "Azure",
    "oci": "Oracle Cloud",
    "gcp": "GCP",
    "branch": "Branch Offices",
}

GROUP_ACCENTS: dict[str, str] = {
    "onprem": "#e09f3e",
    "aws": "#f59e0b",
    "azure": "#3b82f6",
    "oci": "#ef4444",
    "gcp": "#10b981",
    "branch": "#8b5cf6",
}

ROLE_RANK: dict[str, int] = {
    "perimeter": 1, "core": 2, "distribution": 3,
    "access": 4, "edge": 3, "cloud_gateway": 5,
}

DEVICE_TYPE_RANK: dict[str, int] = {
    "FIREWALL": 2, "ROUTER": 3, "LOAD_BALANCER": 3, "SWITCH": 4,
    "PROXY": 3, "HOST": 6, "TRANSIT_GATEWAY": 5, "CLOUD_GATEWAY": 5,
    "NAT_GATEWAY": 5, "VIRTUAL_APPLIANCE": 4, "VPN_CONCENTRATOR": 3,
}

CLOUD_RANK: dict[str, int] = {
    "cloud_gateway": 0, "core": 1, "distribution": 2,
    "edge": 3, "access": 4,
}


# ── Helpers ───────────────────────────────────────────────────────────

def _get_rank(device: dict, group: str = "") -> int:
    """Return sort rank for a device within its group."""
    role = device.get("role", "")
    if group in ("aws", "azure", "oci", "gcp"):
        if role and role in CLOUD_RANK:
            return CLOUD_RANK[role]
    if role and role in ROLE_RANK:
        return ROLE_RANK[role]
    dt = device.get("deviceType", "HOST")
    return DEVICE_TYPE_RANK.get(dt, 5)


def _make_group_style(accent: str, width: int, height: int) -> dict:
    """Build the ReactFlow style dict for a group container node."""
    return {
        "width": width,
        "height": height,
        "backgroundColor": f"{accent}0A",
        "border": f"2px solid {accent}50",
        "borderRadius": 16,
        "padding": 10,
        "fontSize": 18,
        "fontWeight": 800,
        "color": f"{accent}CC",
        "letterSpacing": "0.06em",
        "textTransform": "uppercase",
    }


# ── Main entry point ─────────────────────────────────────────────────

def compute_radial_layout(
    devices: list[dict],
    group_classify_fn=None,
) -> dict:
    """
    Compute radial hub-spoke layout for topology visualization.

    Args:
        devices: list of dicts, each with keys: id, group, role, deviceType, label, ...
        group_classify_fn: optional function(device) -> group_id string

    Returns:
        {
            "device_positions": {device_id: {"x": int, "y": int, "parentId": str}},
            "group_nodes": [ReactFlow group container node dicts],
            "env_labels": [ReactFlow envLabel node dicts],
            "groups_found": {group_id: [device_dicts]},
        }
    """
    if not devices:
        return {
            "device_positions": {},
            "group_nodes": [],
            "env_labels": [],
            "groups_found": {},
        }

    # ── Classify devices into groups ──────────────────────────────────
    groups_found: dict[str, list[dict]] = {}
    for dev in devices:
        if group_classify_fn:
            g = group_classify_fn(dev)
        else:
            g = dev.get("group", "onprem")
        groups_found.setdefault(g, []).append(dev)

    # Absolute positions — keyed by device id.
    abs_positions: dict[str, dict] = {}

    # ── Step 1: Classify on-prem devices into core / inner rings ─────
    core_devices: list[dict] = []
    inner_devices: list[dict] = []

    for dev in groups_found.get("onprem", []):
        role = dev.get("role", "")
        if role in ("core", "perimeter"):
            core_devices.append(dev)
        else:
            inner_devices.append(dev)

    # ── Step 2: Position CORE devices in a tight cluster at center ───
    core_cols = min(len(core_devices), 4)
    core_rows = math.ceil(len(core_devices) / max(core_cols, 1))
    for idx, dev in enumerate(core_devices):
        col = idx % core_cols
        row = idx // core_cols
        abs_positions[dev["id"]] = {
            "x": int(CENTER_X - (core_cols * NODE_W) / 2 + col * (NODE_W + 20)),
            "y": int(CENTER_Y - (core_rows * NODE_H) / 2 + row * (NODE_H + 30)),
        }

    # ── Step 3: Position INNER ring devices around core ──────────────
    if inner_devices:
        angle_step = 360 / len(inner_devices)
        for idx, dev in enumerate(inner_devices):
            angle_rad = math.radians(idx * angle_step + 45)
            abs_positions[dev["id"]] = {
                "x": int(CENTER_X + INNER_RADIUS * math.cos(angle_rad) - NODE_W / 2),
                "y": int(CENTER_Y - INNER_RADIUS * math.sin(angle_rad) - NODE_H / 2),
            }

    # ── Step 4: Position OUTER groups (clouds + branches) ────────────
    outer_group_positions: dict[str, tuple[int, int]] = {}

    for group_id, group_devs in groups_found.items():
        if group_id == "onprem":
            continue

        angle_deg = OUTER_ANGLES.get(group_id, 45)
        angle_rad = math.radians(angle_deg)

        gx = int(CENTER_X + OUTER_RADIUS * math.cos(angle_rad))
        gy = int(CENTER_Y - OUTER_RADIUS * math.sin(angle_rad))
        outer_group_positions[group_id] = (gx, gy)

        n = len(group_devs)
        cols = min(n, 3)
        rows = math.ceil(n / max(cols, 1))
        cluster_w = cols * (NODE_W + 20)
        cluster_h = rows * (NODE_H + 30)

        # Sort by rank within cloud group
        group_devs.sort(key=lambda d: (_get_rank(d, group_id), d.get("label", "")))

        for idx, dev in enumerate(group_devs):
            col = idx % cols
            row = idx // cols
            abs_positions[dev["id"]] = {
                "x": int(gx - cluster_w / 2 + col * (NODE_W + 20)),
                "y": int(gy - cluster_h / 2 + row * (NODE_H + 30)),
            }

    # ── Step 5: Create group container nodes ─────────────────────────
    group_nodes: list[dict] = []

    # On-prem group container
    if "onprem" in groups_found:
        onprem_accent = GROUP_ACCENTS.get("onprem", "#e09f3e")
        onprem_group_x = CENTER_X - 300
        onprem_group_y = CENTER_Y - 280
        group_nodes.append({
            "id": "group-onprem",
            "type": "group",
            "data": {"label": GROUP_LABELS.get("onprem", "On-Premises DC")},
            "position": {"x": onprem_group_x, "y": onprem_group_y},
            "style": _make_group_style(onprem_accent, 600, 560),
            "selectable": False,
            "draggable": False,
        })

        # Convert on-prem device positions to relative
        for dev in core_devices + inner_devices:
            pos = abs_positions[dev["id"]]
            pos["x"] -= onprem_group_x
            pos["y"] -= onprem_group_y

    # Outer group containers
    for group_id, (gx, gy) in outer_group_positions.items():
        group_devs = groups_found.get(group_id, [])
        if not group_devs:
            continue
        accent = GROUP_ACCENTS.get(group_id, "#3d3528")

        n = len(group_devs)
        cols = min(n, 3)
        rows = math.ceil(n / max(cols, 1))
        cluster_w = max(cols * (NODE_W + 20) + 60, 300)
        cluster_h = max(rows * (NODE_H + 30) + 60, 200)

        group_offset_x = int(gx - cluster_w / 2)
        group_offset_y = int(gy - cluster_h / 2)

        group_nodes.append({
            "id": f"group-{group_id}",
            "type": "group",
            "data": {"label": GROUP_LABELS.get(group_id, group_id)},
            "position": {"x": group_offset_x, "y": group_offset_y},
            "style": _make_group_style(accent, cluster_w, cluster_h),
            "selectable": False,
            "draggable": False,
        })

        # Convert outer device positions to relative
        for dev in group_devs:
            pos = abs_positions[dev["id"]]
            pos["x"] -= group_offset_x
            pos["y"] -= group_offset_y

    # ── Build device_positions with parentId ─────────────────────────
    device_positions: dict[str, dict] = {}
    for dev in devices:
        did = dev["id"]
        g = dev.get("group", "onprem")
        if group_classify_fn:
            g = group_classify_fn(dev)
        if did in abs_positions:
            device_positions[did] = {
                **abs_positions[did],
                "parentId": f"group-{g}",
            }

    # ── Step 6: Environment label nodes above each group ─────────────
    env_labels: list[dict] = []

    if "onprem" in groups_found:
        onprem_accent = GROUP_ACCENTS.get("onprem", "#e09f3e")
        env_labels.append({
            "id": "env-label-onprem",
            "type": "envLabel",
            "data": {
                "label": "On-Premises DC",
                "envType": "onprem",
                "accent": onprem_accent,
                "deviceCount": len(core_devices) + len(inner_devices),
            },
            "position": {"x": CENTER_X - 120, "y": CENTER_Y - 320},
            "selectable": False,
            "draggable": False,
        })

    for group_id, (gx, gy) in outer_group_positions.items():
        group_devs = groups_found.get(group_id, [])
        if not group_devs:
            continue
        accent = GROUP_ACCENTS.get(group_id, "#3d3528")
        n = len(group_devs)
        cols = min(n, 3)
        rows_count = math.ceil(n / max(cols, 1))
        cluster_h_val = max(rows_count * (NODE_H + 30) + 60, 200)

        env_labels.append({
            "id": f"env-label-{group_id}",
            "type": "envLabel",
            "data": {
                "label": GROUP_LABELS.get(group_id, group_id),
                "envType": group_id,
                "accent": accent,
                "deviceCount": n,
            },
            "position": {"x": gx - 100, "y": int(gy - cluster_h_val / 2 - 50)},
            "selectable": False,
            "draggable": False,
        })

    return {
        "device_positions": device_positions,
        "group_nodes": group_nodes,
        "env_labels": env_labels,
        "groups_found": groups_found,
    }

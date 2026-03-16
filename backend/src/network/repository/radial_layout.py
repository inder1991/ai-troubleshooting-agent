"""
Multi-column tiered layout for enterprise network topology.

Each environment (on-prem, AWS, Azure, OCI, branch) gets its own vertical
column.  Within each column devices are arranged top-to-bottom by network
tier: perimeter → core → distribution → access.

WAN links (MPLS, DirectConnect, ExpressRoute) run horizontally between
columns at the edge tier — no crossing through the center.

    BRANCH      ON-PREMISES        AWS           AZURE         OCI
    ──────      ───────────        ───           ─────         ───
   Tier 0       Perimeter FW     IGW/NAT       Azure FW       DRG
   Tier 1       Core FW/RTR      CSR/TGW       VWAN Hub       VCN
   Tier 2       Distrib/LB       Cloud FW      NVA/ER-GW      LB
   Tier 3       Access/Switch    VPC/LB        VNet           Workloads
   Tier 4       Servers          Workloads     Workloads
"""

from __future__ import annotations

import math

# ── Layout constants ─────────────────────────────────────────────────

NODE_W = 180
NODE_H = 90
H_GAP = 30          # horizontal gap between nodes in same tier
V_GAP = 40          # vertical gap between tiers
COL_GAP = 120       # gap between column containers
CONTAINER_PAD = 50   # padding inside group container
LABEL_H = 50        # height reserved for env label above container

# ── Tier assignment by role / device type ────────────────────────────

# Lower tier number = higher on screen (closer to internet/WAN edge)
ROLE_TO_TIER: dict[str, int] = {
    "perimeter": 0,
    "core": 1,
    "distribution": 2,
    "edge": 2,
    "access": 3,
    "cloud_gateway": 0,
}

DEVICE_TYPE_TO_TIER: dict[str, int] = {
    "FIREWALL": 1,
    "ROUTER": 1,
    "LOAD_BALANCER": 2,
    "SWITCH": 3,
    "PROXY": 2,
    "HOST": 4,
    "TRANSIT_GATEWAY": 1,
    "CLOUD_GATEWAY": 0,
    "NAT_GATEWAY": 0,
    "VIRTUAL_APPLIANCE": 2,
    "VPN_CONCENTRATOR": 1,
    "SDWAN_EDGE": 2,
}

# ── Column ordering (left to right) ─────────────────────────────────

COLUMN_ORDER = ["branch", "onprem", "aws", "azure", "oci", "gcp"]

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


# ── Helpers ──────────────────────────────────────────────────────────

def _get_tier(device: dict, group: str = "") -> int:
    """Assign a tier (row) to a device. Lower = higher on screen."""
    role = (device.get("role") or "").lower()
    if role in ROLE_TO_TIER:
        return ROLE_TO_TIER[role]
    dt = (device.get("deviceType") or "HOST").upper()
    return DEVICE_TYPE_TO_TIER.get(dt, 3)


def _make_group_style(accent: str, width: int, height: int) -> dict:
    return {
        "width": width,
        "height": height,
        "backgroundColor": f"{accent}08",
        "border": f"1.5px solid {accent}30",
        "borderRadius": 12,
        "padding": 0,
    }


# ── Main entry point ────────────────────────────────────────────────

def compute_radial_layout(
    devices: list[dict],
    group_classify_fn=None,
) -> dict:
    """
    Compute multi-column tiered layout for topology visualization.

    Despite the function name (kept for backward compatibility), this
    now produces a tiered column layout, not a radial one.
    """
    if not devices:
        return {
            "device_positions": {},
            "group_nodes": [],
            "env_labels": [],
            "groups_found": {},
        }

    # ── 1. Classify devices into groups ──────────────────────────────
    groups_found: dict[str, list[dict]] = {}
    for dev in devices:
        g = group_classify_fn(dev) if group_classify_fn else dev.get("group", "onprem")
        groups_found.setdefault(g, []).append(dev)

    # ── 2. For each group, assign tiers and sort ─────────────────────
    # group_tiers[group_id] = {tier_num: [devices]}
    group_tiers: dict[str, dict[int, list[dict]]] = {}
    for gid, devs in groups_found.items():
        tiers: dict[int, list[dict]] = {}
        for dev in devs:
            t = _get_tier(dev, gid)
            tiers.setdefault(t, []).append(dev)
        # Sort devices within each tier alphabetically
        for t in tiers:
            tiers[t].sort(key=lambda d: d.get("label", d.get("id", "")))
        group_tiers[gid] = tiers

    # ── 3. Compute column widths and heights ─────────────────────────
    # Each column's width = max(tier_width) across all its tiers
    # Each column's height = sum of tier heights + gaps

    col_metrics: dict[str, dict] = {}  # gid -> {width, height, tier_y_offsets, tier_widths}

    for gid in COLUMN_ORDER:
        if gid not in group_tiers:
            continue
        tiers = group_tiers[gid]
        tier_nums = sorted(tiers.keys())

        max_width = 0
        total_height = 0
        tier_y: dict[int, int] = {}     # tier -> y offset within column
        tier_w: dict[int, int] = {}     # tier -> width

        for i, t in enumerate(tier_nums):
            n = len(tiers[t])
            # Arrange tier devices in a single row (or wrap to 2 rows if > 3)
            cols = min(n, 3)
            rows = math.ceil(n / max(cols, 1))
            w = cols * (NODE_W + H_GAP) - H_GAP
            h = rows * (NODE_H + V_GAP) - V_GAP

            tier_y[t] = total_height
            tier_w[t] = w
            max_width = max(max_width, w)
            total_height += h
            if i < len(tier_nums) - 1:
                total_height += V_GAP * 2  # extra gap between tiers

        col_metrics[gid] = {
            "width": max_width,
            "height": total_height,
            "tier_y": tier_y,
            "tier_w": tier_w,
        }

    # ── 4. Position columns left to right ────────────────────────────
    ordered_groups = [g for g in COLUMN_ORDER if g in col_metrics]
    col_x: dict[str, int] = {}
    current_x = CONTAINER_PAD

    for gid in ordered_groups:
        col_x[gid] = current_x
        current_x += col_metrics[gid]["width"] + 2 * CONTAINER_PAD + COL_GAP

    # Vertically align all columns so tier 1 (core) is roughly at the same Y
    # Find the max height and center shorter columns
    max_height = max((m["height"] for m in col_metrics.values()), default=400)
    col_y: dict[str, int] = {}
    for gid in ordered_groups:
        # Center column vertically
        col_y[gid] = LABEL_H + CONTAINER_PAD + (max_height - col_metrics[gid]["height"]) // 2

    # ── 5. Compute absolute device positions ─────────────────────────
    abs_positions: dict[str, dict] = {}

    for gid in ordered_groups:
        tiers = group_tiers[gid]
        metrics = col_metrics[gid]
        base_x = col_x[gid]
        base_y = col_y[gid]

        for t, devs in tiers.items():
            tier_y_offset = metrics["tier_y"].get(t, 0)
            tier_width = metrics["tier_w"].get(t, 0)
            # Center this tier within the column
            x_offset = (metrics["width"] - tier_width) // 2

            n = len(devs)
            cols = min(n, 3)
            for idx, dev in enumerate(devs):
                col = idx % cols
                row = idx // cols
                abs_positions[dev["id"]] = {
                    "x": base_x + x_offset + col * (NODE_W + H_GAP),
                    "y": base_y + tier_y_offset + row * (NODE_H + V_GAP),
                }

    # ── 6. Create group container nodes ──────────────────────────────
    group_nodes: list[dict] = []

    for gid in ordered_groups:
        accent = GROUP_ACCENTS.get(gid, "#64748b")
        metrics = col_metrics[gid]
        container_w = metrics["width"] + 2 * CONTAINER_PAD
        container_h = metrics["height"] + 2 * CONTAINER_PAD
        gx = col_x[gid] - CONTAINER_PAD
        gy = col_y[gid] - CONTAINER_PAD

        group_nodes.append({
            "id": f"group-{gid}",
            "type": "group",
            "data": {"label": GROUP_LABELS.get(gid, gid)},
            "position": {"x": gx, "y": gy},
            "style": _make_group_style(accent, container_w, container_h),
            "selectable": False,
            "draggable": False,
        })

        # Convert device positions to relative (within group container)
        for dev in groups_found[gid]:
            pos = abs_positions.get(dev["id"])
            if pos:
                pos["x"] -= gx
                pos["y"] -= gy

    # ── 7. Build device_positions with parentId ──────────────────────
    device_positions: dict[str, dict] = {}
    for dev in devices:
        did = dev["id"]
        g = group_classify_fn(dev) if group_classify_fn else dev.get("group", "onprem")
        if did in abs_positions:
            device_positions[did] = {
                **abs_positions[did],
                "parentId": f"group-{g}",
            }

    # ── 8. Environment label nodes above each group ──────────────────
    env_labels: list[dict] = []

    for gid in ordered_groups:
        accent = GROUP_ACCENTS.get(gid, "#64748b")
        metrics = col_metrics[gid]
        gx = col_x[gid] - CONTAINER_PAD
        gy = col_y[gid] - CONTAINER_PAD
        container_w = metrics["width"] + 2 * CONTAINER_PAD

        env_labels.append({
            "id": f"env-label-{gid}",
            "type": "envLabel",
            "data": {
                "label": GROUP_LABELS.get(gid, gid),
                "envType": gid,
                "accent": accent,
                "deviceCount": len(groups_found[gid]),
            },
            "position": {"x": gx + container_w // 2 - 80, "y": gy - LABEL_H},
            "selectable": False,
            "draggable": False,
        })

    return {
        "device_positions": device_positions,
        "group_nodes": group_nodes,
        "env_labels": env_labels,
        "groups_found": groups_found,
    }

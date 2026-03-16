"""
Multi-column tiered layout for enterprise network topology.

Each environment gets a vertical column. Within each column, devices
are arranged top-down by network tier. All devices are positioned at
the TOP LEVEL (no parentId) so cross-group edges render freely.
Group containers are visual-only backgrounds.

    BRANCH      ON-PREMISES        AWS           AZURE         OCI
    ──────      ───────────        ───           ─────         ───
   Tier 0       Perimeter FW     IGW/NAT       Azure FW       DRG
   Tier 1       Core FW/RTR      CSR/TGW       VWAN Hub       VCN
   Tier 2       Distrib/LB       Cloud FW      NVA/ER-GW      LB
   Tier 3       Access/Switch    VPC/LB        VNet           Workloads
"""

from __future__ import annotations

import math

# ── Layout constants ─────────────────────────────────────────────────

NODE_W = 170
NODE_H = 80
H_GAP = 30          # horizontal gap between nodes in same tier
V_GAP = 50          # vertical gap between tiers
COL_GAP = 80        # gap between columns
CONTAINER_PAD = 30   # padding inside group background
TOP_MARGIN = 80      # space for env label above container

# ── Tier assignment ──────────────────────────────────────────────────

ROLE_TO_TIER: dict[str, int] = {
    "perimeter": 0,
    "core": 1,
    "cloud_gateway": 0,
    "distribution": 2,
    "edge": 2,
    "access": 3,
}

DEVICE_TYPE_TO_TIER: dict[str, int] = {
    "FIREWALL": 1,
    "ROUTER": 1,
    "LOAD_BALANCER": 2,
    "SWITCH": 3,
    "PROXY": 2,
    "HOST": 3,
    "TRANSIT_GATEWAY": 0,
    "CLOUD_GATEWAY": 0,
    "NAT_GATEWAY": 0,
    "VIRTUAL_APPLIANCE": 2,
    "VPN_CONCENTRATOR": 1,
    "SDWAN_EDGE": 2,
}

# ── Column ordering ──────────────────────────────────────────────────

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


def _get_tier(device: dict, group: str = "") -> int:
    role = (device.get("role") or "").lower()
    if role in ROLE_TO_TIER:
        return ROLE_TO_TIER[role]
    dt = (device.get("deviceType") or "HOST").upper()
    return DEVICE_TYPE_TO_TIER.get(dt, 3)


# ── Main layout ─────────────────────────────────────────────────────

def compute_radial_layout(
    devices: list[dict],
    group_classify_fn=None,
) -> dict:
    if not devices:
        return {"device_positions": {}, "group_nodes": [], "env_labels": [], "groups_found": {}}

    # 1. Classify into groups
    groups_found: dict[str, list[dict]] = {}
    for dev in devices:
        g = group_classify_fn(dev) if group_classify_fn else dev.get("group", "onprem")
        groups_found.setdefault(g, []).append(dev)

    # 2. Assign tiers within each group
    group_tiers: dict[str, dict[int, list[dict]]] = {}
    for gid, devs in groups_found.items():
        tiers: dict[int, list[dict]] = {}
        for dev in devs:
            t = _get_tier(dev, gid)
            tiers.setdefault(t, []).append(dev)
        for t in tiers:
            tiers[t].sort(key=lambda d: d.get("label", d.get("id", "")))
        group_tiers[gid] = tiers

    # 3. Compute column dimensions
    ordered_groups = [g for g in COLUMN_ORDER if g in group_tiers]

    col_info: dict[str, dict] = {}
    for gid in ordered_groups:
        tiers = group_tiers[gid]
        tier_nums = sorted(tiers.keys())
        max_w = 0
        tier_y_offsets: dict[int, int] = {}
        y_cursor = CONTAINER_PAD

        for t in tier_nums:
            n = len(tiers[t])
            cols = min(n, 2) if n <= 4 else min(n, 3)
            rows = math.ceil(n / max(cols, 1))
            w = cols * (NODE_W + H_GAP) - H_GAP
            h = rows * (NODE_H + 10) - 10  # tighter within a tier

            tier_y_offsets[t] = y_cursor
            max_w = max(max_w, w)
            y_cursor += h + V_GAP

        total_h = y_cursor - V_GAP + CONTAINER_PAD
        col_info[gid] = {
            "width": max_w,
            "height": total_h,
            "tier_y": tier_y_offsets,
        }

    # 4. Position columns left to right
    col_x: dict[str, int] = {}
    x_cursor = COL_GAP
    for gid in ordered_groups:
        col_x[gid] = x_cursor
        col_w = col_info[gid]["width"] + 2 * CONTAINER_PAD
        x_cursor += col_w + COL_GAP

    # Vertically align — all columns start at same Y
    base_y = TOP_MARGIN + 10

    # 5. Compute ABSOLUTE device positions (no parentId)
    device_positions: dict[str, dict] = {}

    for gid in ordered_groups:
        tiers = group_tiers[gid]
        info = col_info[gid]
        cx = col_x[gid]

        for t, devs in tiers.items():
            ty = base_y + info["tier_y"].get(t, 0)
            n = len(devs)
            cols = min(n, 2) if n <= 4 else min(n, 3)
            tier_w = cols * (NODE_W + H_GAP) - H_GAP
            # Center tier within column
            x_offset = cx + CONTAINER_PAD + (info["width"] - tier_w) // 2

            for idx, dev in enumerate(devs):
                col = idx % cols
                row = idx // cols
                device_positions[dev["id"]] = {
                    "x": x_offset + col * (NODE_W + H_GAP),
                    "y": ty + row * (NODE_H + 10),
                }

    # 6. Group background containers (visual only, no parentId on devices)
    group_nodes: list[dict] = []
    for gid in ordered_groups:
        accent = GROUP_ACCENTS.get(gid, "#64748b")
        info = col_info[gid]
        gx = col_x[gid]
        gy = base_y - 5
        gw = info["width"] + 2 * CONTAINER_PAD
        gh = info["height"] + 10

        group_nodes.append({
            "id": f"group-{gid}",
            "type": "group",
            "data": {"label": GROUP_LABELS.get(gid, gid)},
            "position": {"x": gx, "y": gy},
            "style": {
                "width": gw,
                "height": gh,
                "backgroundColor": f"{accent}06",
                "border": f"1px dashed {accent}25",
                "borderRadius": 8,
                "padding": 0,
                "pointerEvents": "none",
            },
            "selectable": False,
            "draggable": False,
        })

    # 7. Environment labels above each column
    env_labels: list[dict] = []
    for gid in ordered_groups:
        accent = GROUP_ACCENTS.get(gid, "#64748b")
        info = col_info[gid]
        gx = col_x[gid]
        gw = info["width"] + 2 * CONTAINER_PAD

        env_labels.append({
            "id": f"env-label-{gid}",
            "type": "envLabel",
            "data": {
                "label": GROUP_LABELS.get(gid, gid),
                "envType": gid,
                "accent": accent,
                "deviceCount": len(groups_found[gid]),
            },
            "position": {"x": gx + gw // 2 - 80, "y": base_y - TOP_MARGIN + 5},
            "selectable": False,
            "draggable": False,
        })

    return {
        "device_positions": device_positions,
        "group_nodes": group_nodes,
        "env_labels": env_labels,
        "groups_found": groups_found,
    }

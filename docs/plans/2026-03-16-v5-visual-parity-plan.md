# V5 Visual Parity Plan — Make V5 Render Identically to V4, Then Improve

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the V5 topology pipeline produce identical visual output to V4, then retire V4. No visual regression at any step.

**Architecture:** V5 API uses EdgeBuilderService for edges + TopologyStore for node data + the exact same radial layout algorithm (ported to a shared module) + the exact same metrics enrichment. Frontend receives the same data shape as V4 and renders identically.

---

## The Gap Analysis

### V4 node data (what LiveDeviceNode expects):
```
label, entityId, deviceType, ip, vendor, role, group, status,
haRole, location, osVersion, interfaces[], cpuPct?, memoryPct?,
sessionCount?, sessionMax?, threatHits?, sslTps?, poolHealth?,
bgpPeers?, routeCount?
```

### V5 node data (what V5 API currently returns):
```
id, hostname, vendor, device_type, site_id, group, rank, status,
confidence, ha_role, metrics: {}
```

### Missing from V5 nodes:
- `label` (V5 has `hostname`)
- `entityId` (V5 has `id`)
- `ip` (management IP — V5 doesn't include it)
- `role` (V5 doesn't include it)
- `location` (V5 doesn't include it)
- `osVersion` (V5 doesn't include it)
- `interfaces[]` (V5 doesn't include them)
- `haRole` (V5 has `ha_role` — different casing)
- All operational metrics (cpuPct, memoryPct, sessionCount, etc.)

### V4 edge data (what rendering expects):
```
id, source, target, type: "smoothstep", label: "10Gbps",
labelStyle, labelBgStyle, labelBgPadding,
data: { edgeType, srcInterface, dstInterface, protocol, status, utilization, speed },
style: { stroke, strokeWidth, strokeDasharray? },
animated: boolean
```

### V5 edge data (what V5 API currently returns):
```
id, source, target, edge_type, protocol, confidence,
source_interface, target_interface
```

### Missing from V5 edges:
- `type: "smoothstep"` (ReactFlow edge type)
- `label` (speed + utilization)
- `labelStyle`, `labelBgStyle`, `labelBgPadding`
- `data.edgeType` (V5 has `edge_type` — different key)
- `data.srcInterface`, `data.dstInterface`
- `data.status`, `data.utilization`, `data.speed`
- `style` (stroke color, width, dash pattern)
- `animated` (for tunnels)

### V4 has positions, V5 doesn't:
- V4: `position: {x, y}` on every node
- V4: `parentId` on device nodes (for group containment)
- V4: Group container nodes with `style: {width, height}`
- V4: envLabel nodes positioned above groups

---

## The Plan: 5 Tasks

### Task 1: V5 Node Data Parity

**File:** `backend/src/api/topology_v5.py`

Update `build_topology_export()` to include every field LiveDeviceNode needs.

The node dict must exactly match V4's shape:
```python
node = {
    "id": device_id,
    "type": "device",
    "data": {
        "label": pdev.name,
        "entityId": pdev.id,
        "deviceType": dt_val,           # e.g. "FIREWALL"
        "ip": pdev.management_ip or "",
        "vendor": pdev.vendor or "",
        "role": pdev.role or "",
        "group": group,
        "status": "initializing",       # enriched from metrics if available
        "haRole": pdev.ha_role or "",
        "location": pdev.location or "",
        "osVersion": pdev.os_version or "",
        "interfaces": [                 # full interface list
            {
                "id": iface.id,
                "name": iface.name,
                "ip": iface.ip,
                "role": iface.role,
                "zone": iface.zone_id,
                "operStatus": iface.oper_status,
                "adminStatus": iface.admin_status,
            }
            for iface in store.list_interfaces(device_id=pdev.id)
        ],
        # Operational metrics (from SQLiteMetricsStore if available)
        "cpuPct": ...,
        "memoryPct": ...,
        # Device-type-specific metrics...
    },
}
```

Read the existing `export_react_flow_graph()` lines 934-1008 for the exact metrics enrichment logic (CPU, memory, firewall sessions/threats, LB SSL/pool health, router BGP/routes). Port that logic into the V5 export function.

**Test:** Verify V5 node has all keys that V4 node has.

---

### Task 2: V5 Edge Data Parity

**File:** `backend/src/api/topology_v5.py`

The EdgeBuilderService produces NeighborLink objects. Transform them into the exact V4 edge format:

```python
EDGE_STYLES = {
    "physical":      {"stroke": "#22c55e", "strokeWidth": 3},
    "ha_peer":       {"stroke": "#f59e0b", "strokeWidth": 2, "strokeDasharray": "6,4"},
    "tunnel":        {"stroke": "#06b6d4", "strokeWidth": 3, "strokeDasharray": "10,5"},
    "route":         {"stroke": "#64748b", "strokeWidth": 1, "opacity": 0.3},
    "cloud_attach":  {"stroke": "#06b6d4", "strokeWidth": 3},
    "load_balancer": {"stroke": "#a855f7", "strokeWidth": 2},
    "mpls":          {"stroke": "#f59e0b", "strokeWidth": 4},
}

edge = {
    "id": edge_id,
    "source": link.device_id,
    "target": link.remote_device,
    "type": "smoothstep",
    "label": edge_label,          # speed + utilization
    "labelStyle": {"fontSize": 8, "fill": "#64748b", "fontWeight": 400},
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
    "style": EDGE_STYLES.get(edge_type, EDGE_STYLES["physical"]),
    "animated": edge_type == "tunnel",
}
```

Also need to resolve interface names from the NeighborLink's `local_interface` (which is `device_id:iface_name`) back to just `iface_name` for the edge label.

Enrich with interface speed from TopologyStore (same logic as KG lines 1294-1300).

**Test:** Verify V5 edge has all keys that V4 edge has.

---

### Task 3: Port Radial Layout to Shared Module

**File:** `backend/src/network/repository/radial_layout.py`

Extract the radial hub-spoke layout algorithm from `knowledge_graph.py` lines 1048-1248 into a standalone function:

```python
def compute_radial_layout(
    devices: list[dict],    # [{id, group, role, deviceType}]
    groups: list[str],      # ["onprem", "aws", "azure", ...]
) -> dict:
    """
    Returns {
        "device_positions": {device_id: {x, y, parentId}},
        "group_nodes": [group container nodes],
        "env_labels": [environment label nodes],
    }
    """
```

Use the **exact same constants** from the KG:
- CENTER_X = 1200, CENTER_Y = 800
- INNER_RADIUS = 350, OUTER_RADIUS = 900
- NODE_W = 180, NODE_H = 80
- OUTER_ANGLES = {aws: 0, azure: 180, oci: 240, gcp: 60, branch: 310}
- ROLE_RANK, DEVICE_TYPE_RANK, CLOUD_RANK
- GROUP_LABELS, GROUP_ACCENTS

This function produces identical positions to the KG. The KG can also be refactored to call this function instead of having its own copy.

**Test:** Given the same 35 devices, output positions match KG positions.

---

### Task 4: Wire Layout + Edges + Nodes Into V5 API

**File:** `backend/src/api/topology_v5.py`

The V5 endpoint now:
1. Reads devices from TopologyStore (same as V4)
2. Builds edges via EdgeBuilderService (same edges as KG)
3. Computes positions via `compute_radial_layout()` (same positions as KG)
4. Enriches with metrics (same metrics as KG)
5. Returns the complete V4-format response

```python
@router.get("/topology")
def get_topology_v5():
    store = TopologyStore()
    repo = SQLiteRepository(store)

    # 1. Build enriched nodes (Task 1)
    nodes = build_enriched_nodes(store, metrics_store)

    # 2. Build edges (Task 2)
    edge_builder = EdgeBuilderService(store)
    edges = build_enriched_edges(edge_builder.build_all(), store, metrics_store)

    # 3. Compute layout (Task 3)
    layout = compute_radial_layout(nodes, groups)

    # 4. Apply positions to nodes
    for node in nodes:
        pos = layout["device_positions"].get(node["id"])
        if pos:
            node["position"] = {"x": pos["x"], "y": pos["y"]}
            node["parentId"] = pos.get("parentId")

    # 5. Add group containers + env labels
    all_nodes = layout["group_nodes"] + layout["env_labels"] + nodes

    return {
        "nodes": all_nodes,
        "edges": edges,
        "groups": ...,
        "topology_version": ...,
        "device_count": ...,
        "edge_count": ...,
    }
```

**Test:** `curl /api/v5/topology` returns same node count, edge count, and data shape as `curl /api/v4/network/topology`.

---

### Task 5: Update Frontend to Use V5 Directly (No Layout Engine)

**File:** `frontend/src/components/Observatory/topology/LiveTopologyViewV2.tsx`

Since V5 now returns positions (same as V4), the frontend just applies them — no `computeLayout()` needed. The frontend layout engine becomes an optional enhancement, not the primary path.

```typescript
// Remove: import { computeLayout } from './layout/LayoutEngine';

// In useEffect:
const newNodes = topoData.nodes.map((n: any) => ({
    ...n,
    position: savedPositions[n.id] || n.position || { x: 0, y: 0 },
}));
setNodes(newNodes);
setEdges(topoData.edges);
```

This makes V2 render identically to V1 but using V5 data source. WebSocket real-time, edge filters, hover, blast radius, path trace — all preserved.

**Test:** Visual comparison — V2 looks identical to V1.

---

## After Parity Is Achieved

Once V5 renders identically to V4:
1. Delete V1 (`LiveTopologyView.legacy.tsx`)
2. The frontend layout engine (`layout/`) becomes an optional "alternative layout" feature — user can switch between "backend radial" and "dagre" or "force-directed" via a dropdown
3. Gradually improve the frontend layouts through visual iteration
4. Eventually the backend stops computing positions — frontend handles it all
5. But that's a future enhancement, not a blocker

## Key Principle

**Never break what works. Achieve parity first, then improve.**

# Live Topology Rendering — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Observatory topology tab render a real network diagram from KG data — devices grouped by site/cloud, connected by links, styled by type and status.

**Architecture:** Fix KG edge generation to create device-to-device links. Enhance ReactFlow export with grouping/layout metadata. Update Observatory topology rendering with auto-layout, proper icons, link styling, and honest status.

**Tech Stack:** Python/NetworkX (backend KG), React/ReactFlow (frontend canvas)

---

## Task 1: KG Edge Generation — Device-to-Device Links

**Files:**
- Modify: `backend/src/network/knowledge_graph.py`

The `load_from_store()` method currently only creates device→subnet edges. Add 5 new edge types after the existing interface loop (line ~91):

**1a. Shared subnet edges (P2P links)**

After loading all interfaces, find device pairs sharing the same subnet and create direct device↔device edges:

```python
# Build subnet→devices index
subnet_devices: dict[str, list[tuple[str, str, str]]] = {}  # subnet_id → [(device_id, iface_name, ip)]
for d in self.store.list_devices():
    for iface in self.store.list_interfaces(device_id=d.id):
        if iface.ip:
            subnet_meta = self.ip_resolver.resolve(iface.ip)
            if subnet_meta:
                sid = subnet_meta.get("id", "")
                subnet_devices.setdefault(sid, []).append((d.id, iface.name, iface.ip))

# Create device↔device edges for devices sharing a subnet
for sid, members in subnet_devices.items():
    if len(members) < 2:
        continue
    # For P2P subnets (/30, /31) or small subnets, connect all pairs
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            d1_id, d1_iface, d1_ip = members[i]
            d2_id, d2_iface, d2_ip = members[j]
            self.graph.add_edge(d1_id, d2_id,
                edge_type="layer3_link",
                src_interface=d1_iface, dst_interface=d2_iface,
                src_ip=d1_ip, dst_ip=d2_ip,
                subnet_id=sid,
                confidence=0.9, source=EdgeSource.API.value)
            self.graph.add_edge(d2_id, d1_id,
                edge_type="layer3_link",
                src_interface=d2_iface, dst_interface=d1_iface,
                src_ip=d2_ip, dst_ip=d1_ip,
                subnet_id=sid,
                confidence=0.9, source=EdgeSource.API.value)
```

**1b. Route-based forwarding edges**

```python
# Create forwarding edges from routes
for route in self.store.list_routes():
    src_device = route.device_id
    # Resolve next_hop IP to a device
    next_hop_device = self._device_index.get(route.next_hop)
    if next_hop_device and next_hop_device != src_device:
        self.graph.add_edge(src_device, next_hop_device,
            edge_type="routes_via",
            destination=route.destination_cidr,
            protocol=route.protocol,
            metric=route.metric,
            confidence=0.85, source=EdgeSource.API.value)
```

**1c. HA peer edges**

```python
# Create HA edges
for ha in self.store.list_ha_groups():
    members = ha.member_ids
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            self.graph.add_edge(members[i], members[j],
                edge_type="ha_peer",
                ha_group=ha.id, ha_mode=ha.ha_mode.value,
                confidence=1.0, source=EdgeSource.API.value)
            self.graph.add_edge(members[j], members[i],
                edge_type="ha_peer",
                ha_group=ha.id, ha_mode=ha.ha_mode.value,
                confidence=1.0, source=EdgeSource.API.value)
```

**1d. Direct Connect edges (link on-prem router to cloud)**

The DX/ER/FC models don't have device_id fields directly. We need to match them via interface IPs. Add edges based on VPN tunnel local_gateway_id which IS a device ID:

```python
# VPN tunnel edges already exist (lines 128-134) but only tunnel→device.
# Add device↔device via tunnel:
for vpn in self.store.list_vpn_tunnels():
    if vpn.local_gateway_id and vpn.remote_gateway_ip:
        remote_device = self._device_index.get(vpn.remote_gateway_ip)
        if remote_device:
            self.graph.add_edge(vpn.local_gateway_id, remote_device,
                edge_type="tunnel_link",
                tunnel_id=vpn.id, tunnel_type=vpn.tunnel_type.value,
                status=vpn.status.value,
                confidence=0.9, source=EdgeSource.API.value)
            self.graph.add_edge(remote_device, vpn.local_gateway_id,
                edge_type="tunnel_link",
                tunnel_id=vpn.id, tunnel_type=vpn.tunnel_type.value,
                status=vpn.status.value,
                confidence=0.9, source=EdgeSource.API.value)
```

**1e. Load balancer to backend device edges**

Already exists (lines 148-154) but target_ids may be IPs not device IDs. Add IP resolution:

```python
# In the existing LB loop, resolve target IPs to device IDs:
for target_id in tg.target_ids:
    resolved = target_id
    if target_id not in self.graph:
        # Try resolving as IP
        device_from_ip = self._device_index.get(target_id)
        if device_from_ip:
            resolved = device_from_ip
    if resolved in self.graph:
        self.graph.add_edge(lb.id, resolved, ...)
```

**Commit:** `feat(kg): add device-to-device edges (shared subnet, routes, HA, tunnels)`

---

## Task 2: ReactFlow Export — Grouping and Layout Metadata

**Files:**
- Modify: `backend/src/network/knowledge_graph.py` (export_react_flow_graph method)

The current export positions nodes in a flat grid. Add site/cloud grouping:

**2a. Device grouping by location/cloud**

```python
# Determine group for each device
def _get_device_group(data: dict) -> str:
    location = data.get("location", "")
    vendor = data.get("vendor", "")
    # Cloud detection
    if "us-east" in location or "AWS" in vendor:
        return "aws"
    if "westeurope" in location or "Azure" in vendor:
        return "azure"
    if "ashburn" in location or "OCI" in vendor or "Oracle" in location:
        return "oci"
    if "Branch" in location:
        return "branch"
    return "onprem"
```

**2b. Group-based layout**

Position groups in distinct regions of the canvas:

```python
GROUP_POSITIONS = {
    "onprem": {"x": 100, "y": 100, "cols": 4},
    "aws": {"x": 800, "y": 100, "cols": 3},
    "azure": {"x": 800, "y": 500, "cols": 3},
    "oci": {"x": 800, "y": 800, "cols": 2},
    "branch": {"x": 100, "y": 800, "cols": 2},
}
```

Within each group, position devices by role (firewalls at top, routers middle, switches/LBs bottom).

**2c. Add group/container nodes**

Export group containers as ReactFlow parent nodes:

```python
# Add group containers
for group_id, config in GROUP_POSITIONS.items():
    rf_nodes.append({
        "id": f"group-{group_id}",
        "type": "group",
        "data": {"label": group_id.upper().replace("_", " ")},
        "position": {"x": config["x"], "y": config["y"]},
        "style": {"width": config["cols"] * ROW_WIDTH + 100, "height": 400},
    })

# Set parentNode for each device
for node in device_nodes:
    group = _get_device_group(node["data"])
    node["parentNode"] = f"group-{group}"
    node["extent"] = "parent"
```

**2d. Edge styling metadata**

```python
# Add edge type styling hints
EDGE_STYLES = {
    "layer3_link": {"stroke": "#3d3528", "strokeWidth": 2},
    "ha_peer": {"stroke": "#f59e0b", "strokeWidth": 2, "strokeDasharray": "5,5"},
    "tunnel_link": {"stroke": "#0ea5e9", "strokeWidth": 2, "strokeDasharray": "8,4"},
    "routes_via": {"stroke": "#3d3528", "strokeWidth": 1, "opacity": 0.5},
    "attached_to": {"stroke": "#10b981", "strokeWidth": 2},
    "load_balances": {"stroke": "#8b5cf6", "strokeWidth": 2},
    "mpls_path": {"stroke": "#e09f3e", "strokeWidth": 3},
    "vpc_contains": {"stroke": "#3d3528", "strokeWidth": 1, "strokeDasharray": "3,3"},
}
```

For each exported edge, include the style:
```python
for src, dst, data in self.graph.edges(data=True):
    edge_type = data.get("edge_type", "layer3_link")
    style = EDGE_STYLES.get(edge_type, EDGE_STYLES["layer3_link"])
    rf_edges.append({
        "id": f"{src}-{dst}-{edge_type}",
        "source": src,
        "target": dst,
        "type": "smoothstep",
        "data": {"edgeType": edge_type, **data},
        "style": style,
        "animated": edge_type == "tunnel_link",
    })
```

**2e. Filter non-visual nodes**

Don't export zones, subnets, NACLs, compliance zones as visible nodes — they clutter the diagram. Only export: devices, VPCs (as containers), load balancers, transit gateways.

```python
VISUAL_NODE_TYPES = {"device", "vpc", "load_balancer", "transit_gateway", "direct_connect", "vpn_tunnel"}

# Skip non-visual nodes
if ntype not in VISUAL_NODE_TYPES:
    continue
```

**2f. Filter duplicate/reverse edges**

The KG has bidirectional edges (A→B and B→A). ReactFlow only needs one edge per link:

```python
seen_edges = set()
for src, dst, data in self.graph.edges(data=True):
    edge_key = tuple(sorted([src, dst])) + (data.get("edge_type", ""),)
    if edge_key in seen_edges:
        continue
    seen_edges.add(edge_key)
    # ... add to rf_edges
```

**Commit:** `feat(kg): group-based layout, edge styling, filtered export for topology canvas`

---

## Task 3: Device Status — Honest Unknown State

**Files:**
- Modify: `backend/src/network/knowledge_graph.py` (export_react_flow_graph)
- Modify: `backend/src/api/network_metrics_endpoints.py` (add batch health endpoint)

**3a. Status determination**

Currently hardcoded to `"healthy"` (line 677). Replace with metric-based status:

```python
def _get_device_status(device_id: str, metrics_store) -> str:
    """Determine device status from latest SNMP metrics."""
    if not metrics_store:
        return "unknown"  # No metrics store → gray/unknown

    cpu = metrics_store.get_latest_device_metric(device_id, "cpu_pct")
    if cpu is None:
        return "unknown"  # Never polled → gray

    memory = metrics_store.get_latest_device_metric(device_id, "memory_pct")

    if cpu and cpu > 95:
        return "critical"
    if cpu and cpu > 80:
        return "degraded"
    if memory and memory > 90:
        return "degraded"
    return "healthy"
```

Pass metrics_store to export_react_flow_graph:
```python
def export_react_flow_graph(self, metrics_store=None) -> dict:
    ...
    data_dict["status"] = _get_device_status(node_id, metrics_store)
```

**3b. Add batch health endpoint**

```python
@router.get("/devices/health/batch")
async def get_batch_device_health():
    """Get health status for all devices (for topology canvas coloring)."""
    if not _metrics_store:
        return {"devices": {}}

    # Get all device IDs from SNMP scheduler
    result = {}
    for device in _snmp_scheduler._devices:
        device_id = device["id"]
        cpu = _metrics_store.get_latest_device_metric(device_id, "cpu_pct")
        result[device_id] = {
            "status": "unknown" if cpu is None else "healthy" if cpu < 80 else "degraded" if cpu < 95 else "critical",
            "cpu_pct": cpu,
            "memory_pct": _metrics_store.get_latest_device_metric(device_id, "memory_pct"),
        }
    return {"devices": result}
```

**Commit:** `feat(monitoring): metric-based device status (unknown/healthy/degraded/critical)`

---

## Task 4: Frontend — Observatory Topology Tab Rendering

**Files:**
- Modify: `frontend/src/components/Observatory/` (topology tab component)

Read the current Observatory topology tab to understand what it renders. The fixes:

**4a. Status colors**

```typescript
const STATUS_COLORS = {
  healthy: '#10b981',    // Emerald
  degraded: '#f59e0b',   // Amber
  critical: '#ef4444',   // Red
  unknown: '#64748b',    // Slate gray (NOT red)
};
```

"Unknown" = gray, not red. This is the most important visual fix.

**4b. Device icons by type**

```typescript
const DEVICE_ICONS: Record<string, string> = {
  ROUTER: 'router',
  SWITCH: 'switch',
  FIREWALL: 'security',
  LOAD_BALANCER: 'dns',  // or 'mediation'
  HOST: 'dns',
};
```

**4c. Edge styling from backend metadata**

The backend now includes `style` on each edge. The frontend should apply it:

```typescript
// ReactFlow edge with backend-provided style
{
  id: edge.id,
  source: edge.source,
  target: edge.target,
  type: edge.type || 'smoothstep',
  style: edge.style,  // { stroke, strokeWidth, strokeDasharray }
  animated: edge.animated || false,
  label: edge.data?.edgeType === 'tunnel_link' ? 'GRE' : undefined,
}
```

**4d. Group containers**

ReactFlow supports parent nodes. The backend exports `group-onprem`, `group-aws`, etc. as parent nodes. The frontend renders these as labeled rectangles:

```typescript
// Custom group node
const GroupNode = ({ data }) => (
  <div style={{
    background: 'rgba(26, 24, 20, 0.5)',
    border: '1px dashed #3d3528',
    borderRadius: 8,
    padding: 16,
    width: '100%',
    height: '100%',
  }}>
    <span style={{ color: '#64748b', fontSize: 10, fontWeight: 600 }}>
      {data.label}
    </span>
  </div>
);
```

**4e. Poll device status periodically**

Call `GET /monitoring/devices/health/batch` every 30s and update node colors:

```typescript
const { data: healthData } = useQuery({
  queryKey: ['device-health-batch'],
  queryFn: fetchBatchDeviceHealth,
  refetchInterval: 30000,
});

// Merge health into nodes
const nodesWithHealth = nodes.map(node => ({
  ...node,
  data: {
    ...node.data,
    status: healthData?.devices?.[node.id]?.status || node.data.status || 'unknown',
  },
}));
```

**Commit:** `feat(observatory): live topology with status colors, edge styling, grouping`

---

## Task 5: Frontend — Device Node Component

**Files:**
- Create or modify: topology device node component in Observatory

A proper device node for the live topology (different from the editor's design-focused node):

```typescript
const LiveDeviceNode = ({ data }) => {
  const statusColor = STATUS_COLORS[data.status] || STATUS_COLORS.unknown;
  const icon = DEVICE_ICONS[data.deviceType] || 'dns';

  return (
    <div style={{
      background: '#1e1b15',
      border: `2px solid ${statusColor}`,
      borderRadius: 8,
      padding: '8px 12px',
      minWidth: 140,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="material-symbols-outlined" style={{ color: statusColor, fontSize: 18 }}>
          {icon}
        </span>
        <div>
          <div style={{ color: 'white', fontSize: 12, fontWeight: 600 }}>{data.label}</div>
          <div style={{ color: '#8a7e6b', fontSize: 10 }}>{data.vendor}</div>
        </div>
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          background: statusColor, marginLeft: 'auto',
        }} />
      </div>
      {data.ip && (
        <div style={{ color: '#64748b', fontSize: 10, marginTop: 4 }}>{data.ip}</div>
      )}
    </div>
  );
};
```

**Commit:** `feat(observatory): LiveDeviceNode component with status border and icon`

---

## Task 6: Frontend — Link Legend and Topology Controls

**Files:**
- Modify: Observatory topology tab

Add a small legend showing what link colors/styles mean:

```
─── Layer 3 Link    ┄┄┄ HA Peer    ━━━ MPLS
╌╌╌ GRE Tunnel      ─── TGW Attach  ─── LB Target
```

Add controls:
- Zoom to fit button
- Toggle: show/hide subnet nodes
- Toggle: show/hide route edges (can be noisy)
- Filter by group (on-prem only, AWS only, etc.)

**Commit:** `feat(observatory): topology legend and view controls`

---

## Task 7: Topology Data Refresh

**Files:**
- Modify: Observatory topology tab
- Modify: `backend/src/api/network_endpoints.py` or topology query endpoints

The topology canvas should:
- Load from `GET /topology/current` on mount
- Refresh from `GET /monitoring/devices/health/batch` every 30s for status
- Full topology refresh on button click or every 5 minutes

The existing `GET /topology/current` calls `kg.export_react_flow_graph()`. Update it to pass the metrics store:

```python
@router.get("/topology/current")
async def get_current_topology():
    return kg.export_react_flow_graph(metrics_store=_sqlite_metrics)
```

**Commit:** `feat(topology): pass metrics store for live status in topology export`

---

## Implementation Order

```
Task 1: KG edge generation (backend, foundation)
  ↓
Task 2: ReactFlow export enhancement (backend, depends on Task 1)
  ↓
Task 3: Device status from metrics (backend, independent)
  ↓
Tasks 4, 5, 6 in parallel: Frontend rendering (depends on Tasks 1-3)
  ↓
Task 7: Data refresh wiring (depends on all above)
```

**Total: 7 tasks. Observatory topology tab becomes a real live network diagram.**

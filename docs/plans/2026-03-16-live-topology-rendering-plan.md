# Live Topology Rendering — Implementation Plan (Revised)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Observatory topology tab render a production-grade network diagram — L2+L3 links, grouped by site/cloud, auto-layout via dagre, link utilization, path highlighting, node clustering, topology change detection.

**Architecture:** Fix KG edge generation (L2 + filtered L3 + tunnels + HA). Dagre auto-layout. Cached topology export with versioning. Frontend with status colors, link utilization width, collapsible clusters, and click-to-trace path highlighting.

**Tech Stack:** Python/NetworkX (backend KG), dagre-d3 or elkjs (layout), React/ReactFlow (frontend canvas)

---

## Task 1: KG Edge Generation — L2 + Filtered L3 + Tunnel Links

**Files:**
- Modify: `backend/src/network/knowledge_graph.py`

### 1a. Layer-2 links from LLDP/CDP discovery data

Real topology requires L2 links that don't share a subnet (switch-to-switch trunks).

```python
# Layer-2 edges from discovery/LLDP/CDP neighbor tables
# The discovery_scheduler stores neighbors — load them if available
try:
    from src.network.discovery_scheduler import MOCK_NEIGHBORS
    for device_id, neighbors in MOCK_NEIGHBORS.items():
        if device_id not in self.graph:
            continue
        for n in neighbors:
            remote_id = n.get("remote_device", "")
            if remote_id in self.graph:
                edge_key = tuple(sorted([device_id, remote_id]))
                if not self.graph.has_edge(device_id, remote_id) or \
                   not any(d.get("edge_type") == "layer2_link" for _, _, d in self.graph.edges(device_id, data=True) if _ == remote_id):
                    self.graph.add_edge(device_id, remote_id,
                        edge_type="layer2_link",
                        local_port=n.get("local_port", ""),
                        remote_port=n.get("remote_port", ""),
                        protocol=n.get("protocol", "LLDP"),
                        confidence=1.0,
                        source=EdgeSource.API.value)
except Exception:
    pass
```

### 1b. Shared subnet edges — P2P only (/30, /31)

Only create device↔device edges for small subnets. Large subnets (/24 and bigger) connect to the subnet node — not all-pairs mesh.

```python
# Shared subnet → device-to-device ONLY for P2P (/30, /31)
import ipaddress

subnet_devices: dict[str, list[tuple[str, str, str]]] = {}
for d in self.store.list_devices():
    for iface in self.store.list_interfaces(device_id=d.id):
        if iface.ip:
            subnet_meta = self.ip_resolver.resolve(iface.ip)
            if subnet_meta:
                sid = subnet_meta.get("id", "")
                subnet_devices.setdefault(sid, []).append((d.id, iface.name, iface.ip))

for sid, members in subnet_devices.items():
    if len(members) < 2:
        continue
    # Only P2P subnets get device↔device edges
    subnet_obj = next((s for s in subnets if s.id == sid), None)
    if subnet_obj:
        try:
            net = ipaddress.ip_network(subnet_obj.cidr, strict=False)
            if net.prefixlen < 30:
                continue  # Skip — large subnets connect via subnet node
        except ValueError:
            continue

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
```

### 1c. Route edges — filtered (default + summary only)

Only create edges for default routes and summarized prefixes (≤/24), not the full routing table:

```python
import ipaddress as _ipaddress

for route in self.store.list_routes():
    src_device = route.device_id
    next_hop_device = self._device_index.get(route.next_hop)
    if not next_hop_device or next_hop_device == src_device:
        continue

    # Filter: only default route, summary routes, and BGP/OSPF learned
    try:
        net = _ipaddress.ip_network(route.destination_cidr, strict=False)
        is_default = route.destination_cidr == "0.0.0.0/0"
        is_summary = net.prefixlen <= 24
        is_dynamic = route.protocol.upper() in ("BGP", "OSPF", "EIGRP")
    except ValueError:
        continue

    if not (is_default or (is_summary and is_dynamic)):
        continue

    # Avoid duplicate route edges
    existing = [d for _, _, d in self.graph.edges(src_device, data=True)
                if d.get("edge_type") == "routes_via" and _ == next_hop_device]
    if not existing:
        self.graph.add_edge(src_device, next_hop_device,
            edge_type="routes_via",
            destination=route.destination_cidr,
            protocol=route.protocol,
            metric=route.metric,
            confidence=0.85, source=EdgeSource.API.value)
```

### 1d. HA peer edges

```python
for ha in self.store.list_ha_groups():
    members = ha.member_ids
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            if members[i] in self.graph and members[j] in self.graph:
                self.graph.add_edge(members[i], members[j],
                    edge_type="ha_peer",
                    ha_group=ha.id, ha_mode=ha.ha_mode.value,
                    confidence=1.0, source=EdgeSource.API.value)
```

### 1e. VPN tunnel device↔device edges

```python
for vpn in self.store.list_vpn_tunnels():
    if vpn.local_gateway_id and vpn.remote_gateway_ip:
        remote_device = self._device_index.get(vpn.remote_gateway_ip)
        if remote_device and vpn.local_gateway_id in self.graph and remote_device in self.graph:
            self.graph.add_edge(vpn.local_gateway_id, remote_device,
                edge_type="tunnel_link",
                tunnel_id=vpn.id,
                tunnel_type=vpn.tunnel_type.value,
                status=vpn.status.value,
                confidence=0.9, source=EdgeSource.API.value)
```

**Commit:** `feat(kg): L2 + filtered L3 + tunnel + HA edge generation`

---

## Task 2: Topology Versioning + Cached Export

**Files:**
- Modify: `backend/src/network/knowledge_graph.py`

### 2a. Topology hash for change detection

```python
import hashlib, json

def _compute_topology_hash(self) -> str:
    """Compute hash of current topology for change detection."""
    nodes = sorted(self.graph.nodes())
    edges = sorted((s, d, data.get("edge_type", "")) for s, d, data in self.graph.edges(data=True))
    content = json.dumps({"nodes": nodes, "edges": edges}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]
```

### 2b. Cached export with TTL

```python
import time

_topology_cache: dict | None = None
_topology_cache_ts: float = 0
_topology_cache_hash: str = ""
TOPOLOGY_CACHE_TTL = 60  # seconds

def export_react_flow_graph(self, metrics_store=None) -> dict:
    global _topology_cache, _topology_cache_ts, _topology_cache_hash

    now = time.time()
    current_hash = self._compute_topology_hash()

    # Return cache if valid
    if (_topology_cache
        and (now - _topology_cache_ts) < TOPOLOGY_CACHE_TTL
        and current_hash == _topology_cache_hash):
        # Update status from metrics even if topology unchanged
        if metrics_store:
            _update_cached_status(_topology_cache, metrics_store)
        return _topology_cache

    # Rebuild
    result = self._build_react_flow_export(metrics_store)
    result["topology_version"] = current_hash
    result["exported_at"] = now

    _topology_cache = result
    _topology_cache_ts = now
    _topology_cache_hash = current_hash

    return result
```

**Commit:** `feat(kg): topology versioning + 60s cached export`

---

## Task 3: ReactFlow Export — Grouping, Filtering, Edge Styling

**Files:**
- Modify: `backend/src/network/knowledge_graph.py` (`_build_react_flow_export` method)

### 3a. Device grouping by site/cloud (robust, not vendor-based)

```python
def _get_device_group(self, data: dict) -> str:
    """Determine visual group from device metadata."""
    location = (data.get("location", "") or "").lower()
    device_type = data.get("device_type", "")

    # Use location field first (most reliable)
    if "dc-east" in location or "dc-west" in location or "datacenter" in location:
        return "onprem"
    if "us-east" in location or "us-west" in location or "eu-west" in location:
        # Cloud — which one?
        vendor = (data.get("vendor", "") or "").lower()
        if "aws" in location or "amazon" in vendor:
            return "aws"
        if "azure" in location or "microsoft" in vendor:
            return "azure"
        if "oci" in location or "oracle" in vendor or "ashburn" in location:
            return "oci"
        if "gcp" in location or "google" in vendor:
            return "gcp"
        return "cloud"
    if "branch" in location:
        return "branch"

    # Fallback: check if device is a cloud resource type
    if device_type in ("VPC", "TRANSIT_GATEWAY"):
        return "aws"  # Default cloud resources to AWS

    return "onprem"  # Default
```

### 3b. Filter non-visual nodes

Only export nodes that belong on a network diagram:

```python
VISUAL_NODE_TYPES = {
    "device", "vpc", "transit_gateway", "direct_connect", "vlan",
}
# Skip: zone, subnet, nacl, compliance_zone, route_table
```

### 3c. Deduplicate bidirectional edges

```python
seen_edges = set()
for src, dst, key, data in self.graph.edges(data=True, keys=True):
    edge_type = data.get("edge_type", "link")
    dedup_key = (min(src, dst), max(src, dst), edge_type)
    if dedup_key in seen_edges:
        continue
    seen_edges.add(dedup_key)
    # ... export edge
```

### 3d. Edge styling by type

```python
EDGE_STYLES = {
    "layer2_link":   {"stroke": "#64748b", "strokeWidth": 2},
    "layer3_link":   {"stroke": "#3d3528", "strokeWidth": 2},
    "ha_peer":       {"stroke": "#f59e0b", "strokeWidth": 2, "strokeDasharray": "5,5"},
    "tunnel_link":   {"stroke": "#0ea5e9", "strokeWidth": 2, "strokeDasharray": "8,4"},
    "routes_via":    {"stroke": "#3d3528", "strokeWidth": 1, "opacity": 0.4},
    "attached_to":   {"stroke": "#10b981", "strokeWidth": 2},
    "load_balances": {"stroke": "#8b5cf6", "strokeWidth": 2},
    "mpls_path":     {"stroke": "#e09f3e", "strokeWidth": 3},
}
```

### 3e. Link status from interface operational state

```python
def _get_link_status(self, data: dict, metrics_store) -> str:
    """Determine link health from tunnel status or interface metrics."""
    if data.get("status") == "DOWN":
        return "down"
    if data.get("edge_type") == "tunnel_link" and data.get("status") != "UP":
        return "down"
    return "up"
```

Edge includes status for frontend coloring:
```python
edge_status = self._get_link_status(data, metrics_store)
rf_edge["data"]["status"] = edge_status
if edge_status == "down":
    rf_edge["style"]["stroke"] = "#ef4444"
    rf_edge["style"]["strokeDasharray"] = "4,4"
```

### 3f. Link utilization width (from interface metrics)

```python
def _get_link_utilization(self, data: dict, metrics_store) -> float:
    """Get link utilization percentage from SNMP interface metrics."""
    if not metrics_store:
        return 0
    device_id = data.get("src_device", "")
    iface = data.get("src_interface", "")
    if device_id and iface:
        util = metrics_store.get_latest_device_metric(device_id, f"iface_{iface}_utilization_pct")
        return util or 0
    return 0

# In edge export:
util = self._get_link_utilization(data, metrics_store)
if util > 0:
    rf_edge["style"]["strokeWidth"] = max(1, min(6, 1 + util / 20))
    rf_edge["data"]["utilization_pct"] = round(util, 1)
```

**Commit:** `feat(kg): grouped export with edge styling, link status, utilization width`

---

## Task 4: Device Status — Metric-Based with Unknown State

**Files:**
- Modify: `backend/src/network/knowledge_graph.py`
- Modify: `backend/src/api/network_metrics_endpoints.py`

### 4a. Status from SNMP metrics

```python
def _get_device_status(self, device_id: str, metrics_store) -> str:
    if not metrics_store:
        return "unknown"
    cpu = metrics_store.get_latest_device_metric(device_id, "cpu_pct")
    if cpu is None:
        return "unknown"  # Never polled = gray, NOT red
    memory = metrics_store.get_latest_device_metric(device_id, "memory_pct")
    if (cpu and cpu > 95) or (memory and memory > 95):
        return "critical"
    if (cpu and cpu > 80) or (memory and memory > 85):
        return "degraded"
    return "healthy"
```

### 4b. Batch health endpoint

```python
@router.get("/devices/health/batch")
async def get_batch_device_health():
    """All devices' health for topology canvas — polled by frontend every 30s."""
```

**Commit:** `feat(monitoring): metric-based device status with batch endpoint`

---

## Task 5: Frontend — Dagre Auto-Layout

**Files:**
- Modify: Observatory topology tab component
- Add: dagre layout utility

### 5a. Install dagre

```bash
npm install dagre @types/dagre
```

### 5b. Layout function

```typescript
import dagre from 'dagre';

function layoutTopology(nodes: Node[], edges: Edge[]): Node[] {
    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 120 });

    // Set node dimensions
    nodes.forEach(node => {
        g.setNode(node.id, { width: 160, height: 60 });
    });

    // Set edges
    edges.forEach(edge => {
        g.setEdge(edge.source, edge.target);
    });

    dagre.layout(g);

    // Apply positions
    return nodes.map(node => {
        const pos = g.node(node.id);
        return { ...node, position: { x: pos.x - 80, y: pos.y - 30 } };
    });
}
```

### 5c. Group-based dagre

Run dagre per group, then offset groups:

```typescript
const GROUP_OFFSETS = {
    onprem: { x: 0, y: 0 },
    aws: { x: 900, y: 0 },
    azure: { x: 900, y: 600 },
    oci: { x: 900, y: 1000 },
    branch: { x: 0, y: 900 },
};

// Layout each group separately, then offset
for (const [group, offset] of Object.entries(GROUP_OFFSETS)) {
    const groupNodes = nodes.filter(n => n.data.group === group);
    const groupEdges = edges.filter(e =>
        groupNodes.some(n => n.id === e.source) &&
        groupNodes.some(n => n.id === e.target)
    );
    const laid = layoutTopology(groupNodes, groupEdges);
    laid.forEach(n => {
        n.position.x += offset.x;
        n.position.y += offset.y;
    });
}
```

**Commit:** `feat(observatory): dagre auto-layout with group-based positioning`

---

## Task 6: Frontend — LiveDeviceNode + Edge Components

**Files:**
- Create: `frontend/src/components/Observatory/topology/LiveDeviceNode.tsx`
- Create: `frontend/src/components/Observatory/topology/TopologyLegend.tsx`

### 6a. LiveDeviceNode

```typescript
const STATUS_COLORS = {
    healthy: '#10b981',
    degraded: '#f59e0b',
    critical: '#ef4444',
    unknown: '#64748b',  // Gray, NOT red
};

const DEVICE_ICONS: Record<string, string> = {
    ROUTER: 'router',
    SWITCH: 'switch',
    FIREWALL: 'security',
    LOAD_BALANCER: 'dns',
    HOST: 'cloud',
};
```

Node shows: icon, name, vendor, management IP, status dot with border color.

### 6b. TopologyLegend

```
─── L2 Link (LLDP/CDP)    ┈┈┈ HA Peer
─── L3 Link (P2P)          ╌╌╌ GRE/IPsec Tunnel
━━━ MPLS Circuit           ─── TGW/VPC Attach
● Healthy  ● Degraded  ● Critical  ● Unknown
```

### 6c. Link utilization tooltip

On edge hover, show: "rtr-core-01 Te1/0/1 → pa-core-fw-01 eth1/5 | 67% utilization"

**Commit:** `feat(observatory): LiveDeviceNode, edge tooltip, topology legend`

---

## Task 7: Frontend — Node Clustering for Large Networks

**Files:**
- Modify: Observatory topology tab

### 7a. Collapsible group nodes

Each group (onprem, aws, etc.) renders as a container. Click to collapse → shows single node with device count:

```
[DC-East (13 devices)] ←→ [AWS us-east-1 (12 devices)]
```

Click to expand → shows individual devices.

### 7b. Branch clustering

If >5 branch routers exist, collapse into a single "Branches (N)" cluster node.

```typescript
const shouldCluster = (group: string, count: number) => {
    if (group === 'branch' && count > 5) return true;
    if (count > 20) return true;
    return false;
};
```

**Commit:** `feat(observatory): collapsible group clustering for large networks`

---

## Task 8: Path Highlighting (click-to-trace)

**Files:**
- Modify: Observatory topology tab
- Modify: `backend/src/api/network_endpoints.py` (or topology query endpoints)

### 8a. Backend — shortest path endpoint

Already exists in the KG: `find_k_shortest_paths(src_ip, dst_ip)`.

Expose via API if not already:

```python
@router.post("/topology/path")
async def compute_path(src_ip: str, dst_ip: str):
    """Compute shortest path between two IPs for topology highlighting."""
    paths = kg.find_k_shortest_paths(src_ip, dst_ip, k=3)
    return {"paths": paths}
```

### 8b. Frontend — click two devices, highlight path

```typescript
const [pathMode, setPathMode] = useState(false);
const [pathSource, setPathSource] = useState<string | null>(null);
const [highlightedPath, setHighlightedPath] = useState<string[]>([]);

// On device click in path mode:
if (pathMode && !pathSource) {
    setPathSource(node.id);
} else if (pathMode && pathSource) {
    const result = await fetchPath(pathSource, node.id);
    setHighlightedPath(result.paths[0]?.nodes || []);
    setPathMode(false);
    setPathSource(null);
}

// Highlight path nodes and edges
const isOnPath = (nodeId: string) => highlightedPath.includes(nodeId);
// Path nodes get amber border, path edges get amber + animated
```

### 8c. Path mode button in toolbar

```
[Zoom Fit] [Filter ▾] [Trace Path 🔍] [Legend]
```

"Trace Path" enters path mode — user clicks source, then destination.

**Commit:** `feat(observatory): click-to-trace path highlighting`

---

## Task 9: Topology Change Detection + Auto-Refresh

**Files:**
- Modify: Observatory topology tab

### 9a. Poll topology version

```typescript
const { data: topoData } = useQuery({
    queryKey: ['topology-current'],
    queryFn: fetchTopology,
    refetchInterval: 60000,  // Full topology every 60s
});

const { data: healthData } = useQuery({
    queryKey: ['device-health-batch'],
    queryFn: fetchBatchHealth,
    refetchInterval: 30000,  // Status every 30s
});
```

### 9b. Detect changes via version hash

```typescript
const [lastVersion, setLastVersion] = useState('');

useEffect(() => {
    if (topoData?.topology_version && topoData.topology_version !== lastVersion) {
        setLastVersion(topoData.topology_version);
        // Topology changed — show notification
        if (lastVersion) {  // Skip first load
            showToast('Topology updated — new devices or links detected');
        }
    }
}, [topoData?.topology_version]);
```

**Commit:** `feat(observatory): topology change detection with auto-refresh`

---

## Task 10: View Controls + Filters

**Files:**
- Modify: Observatory topology tab

### Toolbar

```
[Zoom Fit] [Zoom In] [Zoom Out] │ [Show: All ▾] │ [Trace Path] │ [Legend ▾]
```

### Show filter dropdown

- All (default)
- On-Prem Only
- AWS Only
- Azure Only
- OCI Only
- Branches Only
- Critical/Degraded Only

### Toggle route edges

Route edges (gray, thin) can be noisy. Toggle to hide:

```
☑ Show L2/L3 Links
☑ Show HA Peers
☑ Show Tunnels
☐ Show Route Edges (off by default — too many)
☑ Show Link Utilization
```

**Commit:** `feat(observatory): topology view controls and edge filters`

---

## Implementation Order

```
Task 1: KG edge generation (L2 + filtered L3 + tunnels + HA)  ← foundation
  ↓
Task 2: Topology versioning + cached export
  ↓
Task 3: ReactFlow export (grouping, edge styling, utilization, link status)
  ↓
Task 4: Device status from metrics + batch endpoint
  ↓
Task 5: Dagre auto-layout with group offsets  ← frontend foundation
  ↓
Tasks 6, 7, 8 in parallel:
  - LiveDeviceNode + legend
  - Node clustering
  - Path highlighting
  ↓
Tasks 9, 10 in parallel:
  - Change detection + auto-refresh
  - View controls + filters
```

**Total: 10 tasks. Transforms "35 red dots" into a production-grade live network diagram.**

---

## What This Enables

| Before | After |
|--------|-------|
| 35 red dots, no connections | Grouped diagram: DC-East left, AWS right, branches bottom |
| No L2 links | LLDP/CDP switch-to-switch trunks visible |
| All routes as edges (noise) | Only default + summary BGP/OSPF routes |
| /24 subnets create 45-edge mesh | Only P2P (/30, /31) create device↔device links |
| Flat grid layout | Dagre hierarchical layout (core top, access bottom) |
| Status always "healthy" or "red" | Gray=unknown, green=healthy, amber=degraded, red=critical |
| No link health | Red dashed links for down tunnels, width by utilization |
| No change detection | Version hash, toast notification on topology change |
| No path visualization | Click source→dest, highlight shortest path (Dynatrace Smartscape-style) |
| No clustering | Collapsible groups, branch clustering for >5 nodes |
| Export every request | 60s cache with version check |

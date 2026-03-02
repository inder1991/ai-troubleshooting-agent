# Enterprise Network Path Troubleshooting System

> Design document for the Network Troubleshooting workflow — a topology-aware reasoning engine that diagnoses firewall, NAT, and routing issues across enterprise networks using a self-improving Network Knowledge Graph, visual diagram editor, and multi-vendor firewall policy simulation.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Two-Layer (Topology + Diagnostic) | Topology layer persists and grows independently. Diagnostic pipeline queries it on-demand. Clean separation. |
| Graph store | NetworkX MultiDiGraph + SQLite | No external graph DB dependency. Routes stored as table, built into graph dynamically. Scales to mid-enterprise (~10k devices). |
| IP resolution | pytricia radix tree | O(log n) longest-prefix match. No brute-force CIDR iteration. Non-negotiable at scale. |
| Diagram editor | React Flow | MIT-licensed, custom node types, grouping, zoom/pan, JSON export. Most popular React node-based editor. |
| Firewall vendors | Palo Alto + Azure NSG + AWS SG + Oracle NSG + Zscaler | All five from day one. Common adapter interface with cached policy snapshots. |
| IPAM ingestion | CSV upload + diagram editor + IPAM API connectors | Three input methods covering enterprises with and without IPAM APIs. |
| Traceroute | Included (TCP/ICMP via icmplib) | Optional and skippable. Pipeline works without it via inference. Rate-limited. |
| LLM usage | Report narrative only | Deterministic control flow. LLM generates human-readable summary from structured JSON. Never invents paths or computes verdicts. |
| Artifact storage | SQLite only (not in graph) | Flows, traces, verdicts stay in DB tables. Only topology entities live in NetworkX. Prevents graph pollution. |
| Confidence model | Multi-source weighted scoring with contradiction detection | Every edge, verdict, and path segment carries confidence + provenance. Inconsistent evidence reduces confidence sharply. |

---

## 1. Network Knowledge Graph (Topology Layer)

### 1.1 Entity Model

Infrastructure entities persist in the graph. Investigation artifacts persist in SQLite only.

**Infrastructure Entities (Graph Nodes):**

| Entity | Key Attributes | Purpose |
|--------|---------------|---------|
| `device` | id, name, vendor, type (router/switch/firewall/proxy), management_ip, model, location | Physical/virtual network device |
| `interface` | id, device_id, name (eth0/ge-0/0/0), ip, mac, zone_id, vrf, speed, status | Device port — connects devices to subnets |
| `subnet` | id, cidr, vlan_id, zone_id, gateway_ip, description, site | IP address space |
| `zone` | id, name, security_level, description, firewall_id | Security zone (DMZ, Corp-LAN, Internet) |
| `workload` | id, name, namespace, cluster, ips[], description | Application/service identity |

**Investigation Artifacts (SQLite tables only — never in NetworkX):**

| Entity | Key Attributes | Purpose |
|--------|---------------|---------|
| `flow` | id, src_ip, dst_ip, port, protocol, timestamp, diagnosis_status, confidence, session_id | Every troubleshooting investigation |
| `trace` | id, flow_id, src, dst, method (traceroute/manual/inferred), timestamp, raw_output, hop_count | Path discovery artifact |
| `trace_hop` | id, trace_id, hop_number, ip, device_id (nullable), rtt_ms, status (responded/timeout/inferred) | Per-hop trace data |
| `flow_verdict` | id, flow_id, firewall_id, rule_id, action, nat_applied, confidence, evidence_type | Per-firewall verdict for a flow |

**Relationship Tables (SQLite, loaded dynamically):**

| Table | Key Fields | Purpose |
|-------|-----------|---------|
| `route` | id, device_id, destination_cidr, next_hop, interface, metric, protocol (static/ospf/bgp/connected), vrf, learned_from, last_updated | Full routing table per device. Edges built dynamically during path computation to prevent graph explosion. |
| `nat_rule` | id, device_id, original_src, original_dst, translated_src, translated_dst, original_port, translated_port, direction (snat/dnat), rule_id, description | Deep NAT modeling. Supports NAT chains across multiple firewalls. |
| `firewall_rule` | id, device_id, rule_name, src_zone, dst_zone, src_ips[], dst_ips[], ports[], protocol, action (allow/deny/drop), logged, order | Cached policy snapshot. Refreshed via adapter on TTL expiry. |

### 1.2 Edge Metadata (All Graph Edges)

Every edge in NetworkX carries provenance and trust:

```python
{
    "confidence": 0.85,           # 0.0–1.0
    "source": "traceroute",       # manual | ipam | traceroute | api | inferred
    "last_verified_at": "2026-03-02T10:30:00Z",
    "edge_type": "connected_to",  # connected_to | routes_to | member_of | policy_allows
}
```

- **Manual diagram edits** start at `confidence=0.5, source="manual"`. Require verification (traceroute or API) to boost.
- **Confidence decay:** Edges not verified in 30+ days lose 0.01/day until re-verified.
- **Multi-source corroboration:** If traceroute AND API both confirm an edge, confidence = max(individual) + 0.05 bonus.

### 1.3 IP Resolution: pytricia Radix Tree

```python
import pytricia
pyt = pytricia.PyTricia()
pyt["10.0.1.0/24"] = {"gateway": "10.0.1.1", "zone": "corp-lan", "device": "core-sw-1"}
# O(log n) longest-prefix match:
result = pyt["10.0.1.55"]  # → returns corp-lan subnet metadata
```

Loaded from `subnet` table on startup. Rebuilt when IPAM data changes.

### 1.4 Graph Construction Rules

1. **Devices, interfaces, subnets, zones, workloads** → permanent graph nodes
2. **Routes** → stored in `route` table, built into `routes_to` edges **only during path computation** (prevents explosion from 50k+ BGP routes)
3. **Traces/flows** → inform the graph (boost edge confidence on verified paths) but **never become graph nodes**
4. **Diagram is visualization layer** → graph is source of truth

### 1.5 Knowledge Graph Growth Cycle

```
Investigation (flow) → Traceroute (trace) → Hop Attribution → Graph Update
                     → Firewall Check (verdict) → NAT Resolution → Graph Update
                     → Confidence Boost on verified edges

Future queries → Hit graph first → Only probe gaps → Faster diagnosis
```

Each investigation makes the graph smarter. After N investigations, common paths have high confidence and produce instant answers without live probes.

---

## 2. IPAM Ingestion

### 2.1 CSV/Excel Upload

Endpoint: `POST /api/v4/network/ipam/upload`

Accepts CSV with columns: `ip, subnet, device, zone, vlan, description`. Parsed with pandas, validated, merged into graph. Duplicate detection by IP/subnet. Conflict resolution: newer upload wins, logged.

### 2.2 Diagram Editor (Manual)

Users define IP/subnet/device mappings directly in the React Flow editor via node property panels. Saved as graph mutations with `source="manual"`.

### 2.3 IPAM API Connectors

Adapter interfaces for:
- **Infoblox** — `GET /wapi/v2.x/network`, `GET /wapi/v2.x/ipv4address`
- **SolarWinds IPAM** — REST API for subnet/IP discovery

Background polling with configurable interval (default: 1 hour). Data merged into graph with `source="ipam"`, `confidence=0.80`.

---

## 3. Firewall Adapters

### 3.1 Common Interface

```python
class FirewallAdapter(ABC):
    # Core troubleshooting
    async def simulate_flow(self, src_ip, dst_ip, port, protocol) -> PolicyVerdict

    # Policy snapshot (cached with TTL)
    async def get_rules(self, zone_src=None, zone_dst=None) -> list[FirewallRule]
    async def get_nat_rules(self) -> list[NATRule]

    # Topology discovery
    async def get_interfaces(self) -> list[DeviceInterface]
    async def get_routes(self) -> list[Route]
    async def get_zones(self) -> list[Zone]
    async def get_vrfs(self) -> list[VRF]
    async def get_virtual_routers(self) -> list[VirtualRouter]

    # Operational
    async def health_check(self) -> AdapterHealth  # connected | auth_failed | stale | unreachable
    async def refresh_snapshot(self) -> None
    def snapshot_age_seconds(self) -> float
```

### 3.2 Vendor Adapters

| Adapter | API Used | Auth | Key Methods |
|---------|----------|------|-------------|
| `PanoramaAdapter` | PAN-OS XML/REST API (pan-os-python) | API key | Rule simulate, zone/VR/VRF discovery, NAT rules |
| `AzureNSGAdapter` | Azure SDK (azure-mgmt-network) | Service principal | NSG rules by NIC/subnet, route tables, VNet topology |
| `AWSSGAdapter` | boto3 (ec2.describe_security_groups) | IAM role/keys | Security groups, NACLs, route tables, VPC peerings |
| `OracleNSGAdapter` | OCI SDK (oci.core.VirtualNetworkClient) | OCI config | NSG rules, route tables, DRG attachments |
| `ZscalerAdapter` | ZIA/ZPA REST API | API key + OAuth | Policy rules, trusted networks, proxy routing |

### 3.3 Caching Strategy

- Every adapter caches its full policy/config snapshot in SQLite (`firewall_rule`, `nat_rule` tables)
- Default TTL = 300 seconds (5 minutes)
- **Diagnostics never hit live API** — always read from cached snapshot
- Manual refresh button in UI forces immediate re-pull
- Adapter health displayed in UI: Connected / Auth Failed / Snapshot Stale / API Unreachable

### 3.4 Verdict Confidence Normalization

Not all policy matches are equal:

| Match Type | Confidence |
|-----------|------------|
| Exact rule match (src+dst+port+zone) | 0.95 |
| Implicit deny (no matching allow rule) | 0.75 |
| Shadowed rule (overridden by higher priority) | 0.60 |
| Adapter inference (partial match) | 0.50 |
| Adapter unavailable | 0.0 (verdict = `ADAPTER_UNAVAILABLE`) |

---

## 4. Diagnostic Pipeline (LangGraph)

### 4.1 Pipeline Architecture

```
User Input (src, dst, port, protocol)
    │
    ▼
┌─────────────────┐
│  input_resolver  │  Resolve IPs → pytricia → subnet/zone/device
│                  │  Handle multi-VRF: AMBIGUOUS_RESOLUTION → ask user
└────────┬────────┘
         ▼
┌─────────────────┐
│  graph_pathfinder│  K-shortest paths (max 3), dual cost model
│                  │  cost = (1-confidence) + topology_penalty
└────────┬────────┘
         ▼
┌─────────────────┐
│  traceroute_probe│  TCP/ICMP via icmplib (OPTIONAL, rate-limited)
│                  │  Loop detection, max 3 concurrent probes
└────────┬────────┘
         ▼
┌─────────────────┐
│  hop_attributor  │  Each hop IP → device via pytricia + device index
│                  │  Probabilistic matching: candidate_devices[] when ambiguous
└────────┬────────┘
         ▼
┌─────────────────────────────────────────────────┐
│  firewall_evaluator  (fan-out, max concurrency=5)│
│  ├── PanoramaAdapter.simulate_flow()             │
│  ├── AzureNSGAdapter.simulate_flow()             │
│  ├── AWSSGAdapter.simulate_flow()                │
│  ├── OracleNSGAdapter.simulate_flow()            │
│  └── ZscalerAdapter.simulate_flow()              │
└────────┬─────────────────────────────────────────┘
         ▼
┌─────────────────┐
│  nat_resolver    │  Apply NAT rules, maintain identity chain (address stack)
│                  │  Re-evaluate downstream rules with translated IPs
└────────┬────────┘
         ▼
┌─────────────────┐
│  path_synthesizer│  Merge all sources, contradiction detection
│                  │  Weighted confidence: traced=3, api=2, graph=1, inferred=0.5
└────────┬────────┘
         ▼
┌─────────────────┐
│  report_generator│  LLM narrative from structured JSON only
└─────────────────┘
```

### 4.2 State Model

```python
class NetworkDiagnosticState(BaseModel):
    # Input
    src_ip: str
    dst_ip: str
    port: int
    protocol: str = "tcp"

    # Resolution
    src_device: Optional[dict] = None
    dst_device: Optional[dict] = None
    src_subnet: Optional[dict] = None
    dst_subnet: Optional[dict] = None
    resolution_status: str = "pending"  # resolved | ambiguous | failed

    # Path discovery
    candidate_paths: list[dict] = []          # K-shortest from graph (max 3)
    traced_path: Optional[dict] = None        # from traceroute
    trace_method: str = "pending"             # tcp | icmp | unavailable
    final_path: Optional[dict] = None         # merged best path

    # Firewalls
    firewalls_in_path: list[dict] = []
    firewall_verdicts: list[dict] = []        # [{device_id, action, rule_id, match_type, confidence}]

    # NAT identity chain
    nat_translations: list[dict] = []
    identity_chain: list[dict] = []           # [{stage, ip, port, device_id}]

    # Trace artifact
    trace_id: Optional[str] = None
    trace_hops: list[dict] = []
    routing_loop_detected: bool = False

    # Diagnosis
    diagnosis_status: str = "running"         # running | complete | no_path_known | ambiguous | error
    confidence: float = 0.0
    evidence: list[dict] = []
    contradictions: list[dict] = []           # [{source_a, source_b, description}]
    next_steps: list[str] = []
    executive_summary: str = ""
```

### 4.3 Node Logic Details

**`input_resolver`** — Deterministic. No LLM.
- pytricia lookup for IP → subnet → zone → device
- If workload name given, resolve via workload table → IPs
- **Multi-VRF handling:** If IP resolves to multiple VRFs/subnets, set `resolution_status="ambiguous"` and return candidates for user selection
- Fail-fast on invalid/unresolvable IPs

**`graph_pathfinder`** — Deterministic. No LLM.
- Yen's K-shortest paths algorithm (max K=3)
- **Dual cost model:**
  ```
  edge_cost = (1 - confidence) + topology_penalty
  ```
  Where topology_penalty includes:
  - VRF boundary crossing: +0.3
  - Inter-site traversal: +0.2
  - Overlay/tunnel: +0.15
  - Low bandwidth link (<100Mbps): +0.1
- If no path exists in graph, returns empty (triggers early exit or inference-only mode)

**`traceroute_probe`** — Deterministic. Optional.
- TCP traceroute on target port (preferred). Falls back to ICMP if TCP fails.
- **Rate limiting:** Max 3 concurrent probes, semaphore-guarded
- **Loop detection:** If same IP appears > 2 times in hops → set `routing_loop_detected=True`
- If traceroute fully blocked → `trace_method="unavailable"`, pipeline continues with graph paths only

**`hop_attributor`** — Deterministic.
- For each traced hop IP: pytricia → subnet → device index → device
- **Probabilistic matching:** When IP is in a known subnet but multiple devices have interfaces there, return `candidate_devices=[...]` with confidence
- Merges traced hops with graph candidate paths (overlapping segments unified)

**`firewall_evaluator`** — Deterministic. Fan-out with bounded concurrency.
- `asyncio.gather(*tasks, limit=5)` — max 5 concurrent adapter calls
- Reads from cached policy snapshot only (never live API)
- Returns `PolicyVerdict(action, rule_id, rule_name, match_type, confidence)` per firewall
- `ADAPTER_UNAVAILABLE` if adapter health check fails
- `INSUFFICIENT_DATA` if no adapter configured for device

**`nat_resolver`** — Deterministic.
- Queries `nat_rule` table for each firewall in path
- Builds **identity chain** (address stack through NAT chain):
  ```python
  identity_chain = [
      {"stage": "original", "ip": "10.1.1.10", "port": 5432, "device_id": None},
      {"stage": "post-snat-fw1", "ip": "203.0.113.5", "port": 5432, "device_id": "fw-prod-01"},
      {"stage": "post-dnat-fw3", "ip": "172.16.5.10", "port": 5432, "device_id": "fw-cloud-01"},
  ]
  ```
- Re-evaluates downstream firewall rules with post-NAT addresses

**`path_synthesizer`** — Deterministic. The brain.
- Merges: traced path + graph candidates + firewall-inferred next-hops
- Marks each segment: `method=traced|graph|inferred|policy`
- **Weighted confidence formula:**
  ```
  segment_weights = {traced: 3.0, api: 2.0, graph: 1.0, inferred: 0.5}
  confidence = Σ(segment_confidence × segment_weight) / Σ(weights)
  ```
- **Contradiction detection:**
  If graph says path A, traceroute shows path B, firewall simulation contradicts trace → set `INCONSISTENT_EVIDENCE`, reduce confidence by 30%, log contradictions with sources
- **Early exit:** If no graph path AND no traceroute → `diagnosis_status="no_path_known"`, skip to report

**`report_generator`** — LLM-assisted (Claude).
- Receives structured JSON only (path, verdicts, NAT chain, evidence, contradictions)
- System prompt: "Only use provided evidence. If insufficient data, say so. Never invent paths or compute verdicts."
- Produces: executive summary, path narrative, firewall citations, NAT explanations, confidence breakdown, actionable next steps

### 4.4 Conditional Routing

```python
# After input_resolver:
if resolution_status == "ambiguous":  → END (return ambiguity to user)
if resolution_status == "failed":     → END (return error)

# After graph_pathfinder:
if no candidate_paths AND traceroute unavailable:
    → report_generator with diagnosis_status="no_path_known" → END

# After traceroute_probe:
if trace_hops exist: → hop_attributor → firewall_evaluator
else:                → firewall_evaluator (use graph paths only)

# After firewall_evaluator:
if any NAT rules in path: → nat_resolver → path_synthesizer
else:                     → path_synthesizer directly

# Always:
path_synthesizer → report_generator → END
```

---

## 5. API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| **Diagnosis** | | |
| `POST` | `/api/v4/network/diagnose` | Start diagnosis (src, dst, port). Idempotent within 60s (same params → existing session_id). |
| `GET` | `/api/v4/network/session/{id}/findings` | Get diagnosis results |
| `WS` | `/api/v4/network/session/{id}/ws` | Live pipeline progress stream |
| **Topology** | | |
| `POST` | `/api/v4/network/topology/save` | Save diagram JSON → update graph |
| `GET` | `/api/v4/network/topology/load` | Load diagram + graph for editor |
| `GET` | `/api/v4/network/topology/stats` | Node/edge counts, coverage metrics |
| **IPAM** | | |
| `POST` | `/api/v4/network/ipam/upload` | Upload CSV/Excel IPAM data |
| `GET` | `/api/v4/network/ipam/subnets` | List known subnets |
| `GET` | `/api/v4/network/ipam/devices` | List known devices |
| **Adapters** | | |
| `POST` | `/api/v4/network/adapters/{vendor}/configure` | Configure firewall adapter credentials |
| `GET` | `/api/v4/network/adapters/status` | Health status of all adapters |
| `POST` | `/api/v4/network/adapters/{vendor}/refresh` | Force snapshot refresh |
| **History** | | |
| `GET` | `/api/v4/network/flows` | List past investigations |
| `GET` | `/api/v4/network/flows/{flow_id}` | Get flow details with trace and verdicts |

### 5.1 WebSocket Event Types

Standardized events for frontend determinism:

```json
{"type": "NODE_STARTED", "node": "input_resolver", "timestamp": "..."}
{"type": "NODE_COMPLETED", "node": "input_resolver", "duration_ms": 45}
{"type": "NODE_STARTED", "node": "traceroute_probe"}
{"type": "EVIDENCE_ADDED", "evidence_type": "traceroute_hop", "data": {...}}
{"type": "NODE_COMPLETED", "node": "firewall_evaluator", "duration_ms": 234}
{"type": "EVIDENCE_ADDED", "evidence_type": "firewall_verdict", "data": {...}}
{"type": "FINAL_RESULT", "confidence": 0.87, "diagnosis_status": "complete"}
```

### 5.2 Idempotent Diagnosis

`POST /api/v4/network/diagnose` with identical `(src, dst, port, protocol)` within 60 seconds returns the existing `session_id` instead of starting a new investigation. Prevents duplicate heavy computations.

---

## 6. Frontend

### 6.1 Network War Room (Investigation View)

New `ViewState`: `'network-troubleshooting'`. Full-screen, sidebar hidden.

**CSS Grid 12-column layout:**

```
┌─────────────────────────────────────────────────────────────────┐
│  NETWORK PATH ANALYZER  ///  src → dst : port  ///  confidence  │
├────────────┬──────────────────────────┬─────────────────────────┤
│            │                          │                         │
│  DIAGNOSIS │   TOPOLOGY CANVAS        │  EVIDENCE STACK         │
│  (col-3)   │   (col-5)               │  (col-4)               │
│            │                          │                         │
│  Executive │   React Flow diagram     │  Traceroute output     │
│  summary   │   with path highlighted  │  Firewall verdicts     │
│            │   Animated flow          │  NAT identity chain    │
│  Path hops │   Firewall nodes red/    │  Rule citations        │
│  list      │   green based on verdict │  Confidence breakdown  │
│            │                          │                         │
│  NAT chain │   Zoom/pan/select        │  Contradictions        │
│  display   │                          │  (if any)              │
│            │                          │                         │
│  Next      │                          │  Raw evidence          │
│  steps     │                          │  (API responses,       │
│            │                          │   trace output)        │
│  Past      │                          │                         │
│  flows     │                          │  Adapter health        │
│            │                          │                         │
└────────────┴──────────────────────────┴─────────────────────────┘
```

### 6.2 Topology Editor (Dedicated Page)

Accessible from sidebar nav. Users can:

**Node Palette (drag-and-drop sidebar):**

| Node Type | Icon (Material Symbol) | Visual | Properties Panel |
|-----------|----------------------|--------|-----------------|
| Router | `router` | Rounded rect, blue border | name, management_ip, vendor, VRFs |
| Switch | `lan` | Rounded rect, green border | name, management_ip, vlans[] |
| Firewall | `shield` | Hexagon, red border | name, vendor (PA/NSG/AWS/Oracle/Zscaler), api_endpoint, api_key |
| Subnet | `hub` | Dashed rect (group node), gray | cidr, vlan_id, zone, gateway_ip |
| Zone | `security` | Large container, colored bg | name, security_level |
| Workload | `dns` | Small circle, cyan | name, namespace, ips[] |
| Cloud Gateway | `cloud` | Cloud shape, purple | provider (aws/azure/oracle), region |
| VPN Tunnel | `vpn_lock` | Dashed line connector | tunnel_type, endpoints |

**Edge Types:**

| Edge Style | Meaning | Properties |
|-----------|---------|------------|
| Solid line | Physical/L3 link | bandwidth, interface_src, interface_dst |
| Dashed line | Logical/overlay | tunnel_type, encapsulation |
| Red line | Policy deny | firewall_id, rule_id |
| Green line | Policy allow | firewall_id, rule_id, ports[] |

**Features:**
- Save/load with versioned snapshots
- Import IPAM CSV directly from editor
- Configure firewall adapters from device property panel
- Enrichment overlays: discovered links, routing data, live health
- Animated flow overlay when replaying investigations

### 6.3 New Frontend Components

```
NetworkTroubleshooting/
├── NetworkWarRoom.tsx          — Main investigation view (3-column grid)
├── DiagnosisPanel.tsx          — Left column: summary, path, NAT chain, next steps
├── NetworkCanvas.tsx           — Center: React Flow with path highlight + animation
├── NetworkEvidenceStack.tsx    — Right column: traceroute, verdicts, rules, raw evidence
├── PathHopList.tsx             — Ordered hop list with status indicators
├── FirewallVerdictCard.tsx     — Per-firewall verdict display (allow/deny/unknown)
├── NATChainDisplay.tsx         — Identity chain visualization
├── AdapterHealthBadge.tsx      — Per-adapter health indicator
└── NetworkDiagnoseForm.tsx     — Quick-launch form (src, dst, port)

TopologyEditor/
├── TopologyEditorView.tsx      — Main editor page
├── NodePalette.tsx             — Drag-and-drop device palette
├── DeviceNode.tsx              — Custom React Flow node (router, switch, firewall)
├── SubnetGroupNode.tsx         — Grouping node for subnets
├── ZoneContainerNode.tsx       — Large container for security zones
├── EdgeConfigPanel.tsx         — Edge type and properties
├── DevicePropertyPanel.tsx     — Node properties side panel
├── IPAMUploadDialog.tsx        — CSV/Excel import dialog
├── AdapterConfigDialog.tsx     — Firewall adapter credential setup
├── TopologyToolbar.tsx         — Save, load, version history, enrichment
└── EnrichmentOverlay.tsx       — Discovered links, health indicators

ActionCenter/forms/
└── NetworkTroubleshootingFields.tsx — Capability form fields (src, dst, port, protocol)
```

### 6.4 Navigation Integration

| Touch Point | Change |
|-------------|--------|
| `types/index.ts` | Add `'network_troubleshooting'` to `CapabilityType`. Add `NetworkTroubleshootingForm` interface. |
| `App.tsx` | Add `'network-troubleshooting'` to `ViewState`. Add form submit handler. Add render block. |
| `SidebarNav.tsx` | Add `'topology'` to `NavView` for the editor page. Icon: `device_hub`. |
| `CapabilityLauncher.tsx` | Add capability card. Icon: `route`. Color: `#f59e0b` (amber). |
| `CapabilityForm.tsx` | Add meta, initial data, validation, form field rendering. |
| `ActionCenter.tsx` | Add to capabilities array. |

---

## 7. Backend Architecture

### 7.1 New Files

```
backend/src/agents/network/
├── __init__.py
├── state.py                    — NetworkDiagnosticState + all Pydantic models
├── graph.py                    — LangGraph pipeline: build_network_diagnostic_graph()
├── input_resolver.py           — IP/workload resolution via pytricia
├── graph_pathfinder.py         — K-shortest paths with dual cost model
├── traceroute_probe.py         — TCP/ICMP traceroute via icmplib
├── hop_attributor.py           — Hop IP → device attribution
├── firewall_evaluator.py       — Fan-out to vendor adapters
├── nat_resolver.py             — NAT rule application + identity chain
├── path_synthesizer.py         — Path merging + contradiction detection + confidence
├── report_generator.py         — LLM narrative generation

backend/src/agents/network/adapters/
├── __init__.py
├── base.py                     — FirewallAdapter ABC + AdapterHealth + PolicyVerdict
├── panorama_adapter.py         — Palo Alto via pan-os-python
├── azure_nsg_adapter.py        — Azure via azure-mgmt-network
├── aws_sg_adapter.py           — AWS via boto3
├── oracle_nsg_adapter.py       — Oracle via oci SDK
├── zscaler_adapter.py          — Zscaler via ZIA/ZPA REST API

backend/src/network/
├── __init__.py
├── knowledge_graph.py          — NetworkX graph manager (load, save, query, merge)
├── ip_resolver.py              — pytricia radix tree wrapper
├── ipam_ingestion.py           — CSV parser + IPAM API connectors
├── topology_store.py           — SQLite persistence for graph entities
├── route_store.py              — Route table storage and dynamic edge building
├── diagram_store.py            — React Flow JSON versioned storage

backend/src/api/
├── network_endpoints.py        — All /api/v4/network/* routes
├── network_models.py           — Request/response Pydantic models

backend/tests/
├── test_network_knowledge_graph.py
├── test_ip_resolver.py
├── test_firewall_adapters.py
├── test_network_pipeline.py
├── test_network_endpoints.py
├── test_path_synthesizer.py
├── test_nat_resolver.py
```

### 7.2 Dependencies (New)

```
networkx          — Graph operations, K-shortest paths
pytricia          — Radix tree for CIDR resolution
icmplib           — TCP/ICMP traceroute
pan-os-python     — Palo Alto Panorama API
azure-mgmt-network — Azure NSG/VNet
boto3             — AWS Security Groups
oci               — Oracle Cloud NSG
pandas            — CSV/Excel IPAM ingestion
openpyxl          — Excel file support
```

---

## 8. Data Flow

```
Topology Editor (React Flow)
  → POST /topology/save → knowledge_graph.py → SQLite + NetworkX

IPAM Upload (CSV/Excel)
  → POST /ipam/upload → ipam_ingestion.py → subnet/device tables → pytricia rebuild

Adapter Config
  → POST /adapters/{vendor}/configure → credentials stored (encrypted)
  → Adapter fetches snapshot → firewall_rule/nat_rule tables

Diagnosis Request
  → POST /network/diagnose → session created → LangGraph pipeline starts
  → WebSocket streams NODE_STARTED/COMPLETED/EVIDENCE_ADDED/FINAL_RESULT
  → GET /network/session/{id}/findings → structured diagnosis

Graph Learning
  → After each diagnosis: verified edges get confidence boost
  → Stale edges decay over time
  → New topology data merged from traces, API snapshots, IPAM updates
```

---

## 9. Error Handling & Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| Traceroute fully blocked | Pipeline continues with graph paths + policy simulation. Confidence reduced. |
| No graph path + no traceroute | Early exit: `NO_PATH_KNOWN`. Report suggests: upload IPAM, draw topology, configure adapters. |
| Adapter unavailable | Verdict = `ADAPTER_UNAVAILABLE`. Report shows which adapter failed and how to fix. |
| Multi-VRF ambiguity | `AMBIGUOUS_RESOLUTION`. Return candidates, user selects. |
| Routing loop detected | Flag in report. Highlight looping segment. Suggest checking routing tables. |
| Contradictory evidence | `INCONSISTENT_EVIDENCE`. Confidence reduced 30%. Both sources shown with explanation. |
| NAT chain across 3+ firewalls | Identity chain tracks all stages. Downstream rules re-evaluated with correct translated IPs. |
| 5k+ devices in graph | NetworkX handles this. Route tables stay in SQLite, loaded on-demand. pytricia unaffected. |
| 100k+ flows/day | Flows stay in SQLite (not graph). Graph stays lean topology-only. |

---

## 10. Worst-Case Scale Limits

| Dimension | Safe Limit | Mitigation If Exceeded |
|-----------|-----------|----------------------|
| Devices in graph | ~10,000 | Partition by site/region. Consider Neo4j migration. |
| Routes per device | Unlimited (in SQLite) | Dynamic edge building prevents graph explosion. |
| Concurrent diagnoses | ~20 | Rate limit + traceroute semaphore (max 3 probes). |
| Flows per day | ~100,000 | SQLite with proper indexing. Archive old flows. |
| Firewall rules per device | ~50,000 | Cached in SQLite. Binary search on priority-ordered rules. |

---

## 11. Component Tree

```
App.tsx
├── CapabilityLauncher → NetworkTroubleshootingFields
├── NetworkWarRoom (viewState = 'network-troubleshooting')
│   ├── DiagnosisPanel
│   │   ├── PathHopList
│   │   ├── NATChainDisplay
│   │   ├── FirewallVerdictCard[]
│   │   └── NextStepsList
│   ├── NetworkCanvas (React Flow)
│   │   ├── DeviceNode (custom)
│   │   ├── SubnetGroupNode (custom)
│   │   └── AnimatedFlowEdge (custom)
│   └── NetworkEvidenceStack
│       ├── TracerouteOutput
│       ├── RuleCitationCard[]
│       ├── ConfidenceBreakdown
│       ├── ContradictionAlert[]
│       └── AdapterHealthBadge[]
├── TopologyEditorView (viewState = 'topology-editor')
│   ├── TopologyToolbar
│   ├── NodePalette
│   ├── React Flow Canvas
│   │   ├── DeviceNode
│   │   ├── SubnetGroupNode
│   │   └── ZoneContainerNode
│   ├── DevicePropertyPanel
│   ├── EdgeConfigPanel
│   ├── IPAMUploadDialog
│   └── AdapterConfigDialog
└── SidebarNav (includes 'topology' entry)
```

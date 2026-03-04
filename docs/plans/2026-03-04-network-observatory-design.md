# Network Observatory: Intent-Driven Network Observability

**Date:** 2026-03-04
**Author:** Claude + Head of Network Architecture
**Status:** Approved for implementation planning

## Problem

The platform has strong per-flow diagnostic capabilities (path analysis, firewall evaluation, traceroute) but lacks always-on network visibility. There is no live view showing what is up, down, or degraded. There is no way to see traffic flow patterns across the network. And there is no mechanism to detect when the actual network state drifts from the intended topology defined in the Knowledge Graph.

A head of network architecture needs to open one dashboard and immediately understand: is the network healthy? What changed? What's new?

## Design Principles

Inspired by [NetBox Observability](https://netboxlabs.com/products/netbox-observability/) and [Aviatrix CoPilot](https://docs.aviatrix.com/documentation/v8.1/release-notices/copilot-software-release-notes/copilot-release-notes.html):

1. **Intent-driven monitoring** — The Knowledge Graph defines how the network *should* work. Monitoring compares actual state against this intent.
2. **Context-aware** — When a device goes down, the system knows its zone, HA group, affected subnets, and impacted traffic paths.
3. **Multi-source collection** — Synthetic probes + firewall adapter APIs + Prometheus metrics. No single point of failure for visibility.
4. **Discovery built in** — Unknown devices found on the wire are surfaced as candidates, not ignored.

## Architecture Overview

Three layers:

```
┌──────────────────────────────────────────────────┐
│              FRONTEND DASHBOARD                   │
│  Live Topology | NOC Wall | Traffic Flows         │
│  30s polling via GET /monitor/snapshot             │
├──────────────────────────────────────────────────┤
│              REST API ENDPOINTS                   │
│  /monitor/snapshot, /monitor/drift,               │
│  /monitor/device/{id}/history,                    │
│  /monitor/discover/{ip}/promote                   │
├──────────────────────────────────────────────────┤
│           COLLECTION ENGINE (30s cycle)           │
│  Probe → Adapter → Prometheus → Drift → Discovery │
├──────────────────────────────────────────────────┤
│              STATE STORE (SQLite)                  │
│  device_status | link_metrics | metric_history    │
│  drift_events  | discovery_candidates             │
└──────────────────────────────────────────────────┘
```

**Scale target:** <50 devices, 30-second refresh, single-instance deployment.

---

## 1. Collection Engine

**File:** `backend/src/network/monitor.py`

A `NetworkMonitor` singleton that runs as a background `asyncio` task, started on FastAPI startup. Each 30-second cycle executes five passes sequentially:

### 1.1 Probe Pass

Pings every device in the KG to determine reachability and latency.

- Uses `icmplib.async_ping` (already a dependency) for ICMP, `asyncio.open_connection` with 5s timeout for TCP.
- All probes run concurrently via `asyncio.gather`, each with a per-device 5s timeout.
- Status derivation:
  - **UP** — responds within 5s, latency < 100ms, packet loss < 10%
  - **DEGRADED** — responds but latency > 100ms or packet loss > 10%
  - **DOWN** — no response within 5s

### 1.2 Adapter Pass

Pulls live state from existing firewall adapters.

- Calls `adapter.get_interfaces()`, `adapter.get_routes()`, `adapter.get_rules()` on each registered adapter.
- Extracts interface counters (bandwidth, errors) where available.
- Collects neighbor/ARP table entries for discovery (Source 1).
- Fault-isolated: if one adapter fails, others still run.

### 1.3 Prometheus Pass

Batch PromQL queries for SNMP-exported metrics.

- Queries: `ifOperStatus`, `ifInOctets`, `ifOutOctets`, `snmp_*` metrics.
- Uses the existing Prometheus URL from settings/configuration.
- Skipped gracefully if Prometheus is not configured or unreachable.

### 1.4 Drift Pass

Compares live adapter state against KG intent. Detailed in Section 4.

### 1.5 Discovery Pass

Finds unknown IPs from adapter neighbors, subnet probes, and Prometheus targets. Detailed in Section 5.

### 1.6 Write Pass

Upserts all collected data into SQLite state tables in a single transaction.

### Error Isolation

Each pass is wrapped in its own try-except. A Prometheus outage does not prevent probes from running. An adapter timeout does not block discovery. Errors are logged, never crash the cycle.

### Lifecycle

```python
class NetworkMonitor:
    def __init__(self, store, kg, adapters, prometheus_url=None):
        self.store = store
        self.kg = kg
        self.adapters = adapters
        self.prometheus_url = prometheus_url
        self._task: asyncio.Task | None = None
        self.cycle_interval = 30  # seconds

    async def start(self):
        """Called from FastAPI startup event."""
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Called from FastAPI shutdown event."""
        if self._task:
            self._task.cancel()

    async def _run_loop(self):
        while True:
            try:
                await self._collect_cycle()
            except Exception as e:
                logger.error("Monitor cycle failed: %s", e)
            await asyncio.sleep(self.cycle_interval)
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v4/network/monitor/snapshot` | GET | Current status for all devices, links, active drifts, discovery candidates |
| `/api/v4/network/monitor/device/{device_id}/history` | GET | Latency/status history for a device. Query param: `period` (1h, 24h, 7d) |
| `/api/v4/network/monitor/drift` | GET | All active drift events |
| `/api/v4/network/monitor/discover/{ip}/promote` | POST | Promote a discovered IP to a KG device |
| `/api/v4/network/monitor/discover/{ip}/dismiss` | POST | Dismiss a discovery candidate |

---

## 2. State Store

Five new tables in `topology_store.py`, following existing patterns (try-finally connection handling, SQLite).

### 2.1 device_status

Current health per device. One row per device, upserted every cycle.

```sql
CREATE TABLE IF NOT EXISTS device_status (
    device_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,              -- 'up', 'down', 'degraded'
    latency_ms REAL DEFAULT 0,
    packet_loss REAL DEFAULT 0,        -- 0.0-1.0
    last_seen TEXT,                     -- ISO timestamp
    last_status_change TEXT,           -- when status last flipped
    probe_method TEXT DEFAULT 'icmp',  -- 'icmp', 'tcp', 'adapter'
    updated_at TEXT
);
```

### 2.2 link_metrics

Current metrics per device-to-device link. Upserted every cycle.

```sql
CREATE TABLE IF NOT EXISTS link_metrics (
    src_device_id TEXT,
    dst_device_id TEXT,
    latency_ms REAL DEFAULT 0,
    bandwidth_bps INTEGER DEFAULT 0,
    error_rate REAL DEFAULT 0,         -- 0.0-1.0
    utilization REAL DEFAULT 0,        -- 0.0-1.0
    updated_at TEXT,
    PRIMARY KEY (src_device_id, dst_device_id)
);
```

### 2.3 metric_history

Append-only time-series for sparklines and historical charts. Pruned to 7 days.

```sql
CREATE TABLE IF NOT EXISTS metric_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,         -- 'device' or 'link'
    entity_id TEXT NOT NULL,           -- device_id or 'src|dst'
    metric TEXT NOT NULL,              -- 'latency_ms', 'packet_loss', 'bandwidth_bps'
    value REAL NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metric_history_entity
    ON metric_history(entity_type, entity_id, recorded_at);
```

At 30s intervals with <50 devices and ~2 metrics each: ~20K rows/day, ~140K rows/week. Trivial for SQLite.

### 2.4 drift_events

Actual-vs-intended mismatches. UNIQUE constraint prevents duplicate events per cycle.

```sql
CREATE TABLE IF NOT EXISTS drift_events (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,         -- 'route', 'firewall_rule', 'interface', 'device'
    entity_id TEXT NOT NULL,
    drift_type TEXT NOT NULL,          -- 'missing', 'added', 'changed'
    field TEXT DEFAULT '',             -- which field drifted
    expected TEXT DEFAULT '',
    actual TEXT DEFAULT '',
    severity TEXT DEFAULT 'warning',   -- 'info', 'warning', 'critical'
    detected_at TEXT,
    resolved_at TEXT,                  -- NULL = still active
    UNIQUE(entity_type, entity_id, drift_type, field)
);
```

### 2.5 discovery_candidates

Unconfirmed devices found on the wire.

```sql
CREATE TABLE IF NOT EXISTS discovery_candidates (
    ip TEXT PRIMARY KEY,
    mac TEXT DEFAULT '',
    hostname TEXT DEFAULT '',          -- reverse DNS
    discovered_via TEXT DEFAULT '',    -- 'adapter_neighbor', 'probe', 'prometheus', 'traceroute'
    source_device_id TEXT DEFAULT '',  -- which adapter reported it
    first_seen TEXT,
    last_seen TEXT,
    promoted_device_id TEXT DEFAULT '',-- set when user promotes to KG
    dismissed INTEGER DEFAULT 0
);
```

### Store Methods

```python
# device_status
upsert_device_status(device_id, status, latency_ms, packet_loss, probe_method)
get_device_status(device_id) -> dict | None
list_device_statuses() -> list[dict]

# link_metrics
upsert_link_metric(src_id, dst_id, latency_ms, bandwidth_bps, error_rate, utilization)
list_link_metrics() -> list[dict]

# metric_history
append_metric(entity_type, entity_id, metric, value)
query_metric_history(entity_type, entity_id, metric, since) -> list[dict]
prune_metric_history(older_than_days=7)

# drift_events
upsert_drift_event(entity_type, entity_id, drift_type, field, expected, actual, severity)
resolve_drift_event(event_id)
list_active_drift_events() -> list[dict]

# discovery_candidates
upsert_discovery_candidate(ip, mac, hostname, discovered_via, source_device_id)
list_discovery_candidates() -> list[dict]
promote_candidate(ip, device_id)
dismiss_candidate(ip)
```

---

## 3. Dashboard

A new top-level page at route `/network/observatory` with three tabs. Built with the existing design system (dark theme `#0f2023`, cyan `#07b6d5`, Material Symbols).

### 3.1 Live Topology Tab (Primary)

Reuses the existing React Flow canvas in **read-only monitoring mode** — no drag-to-create, no editing. Topology is from the KG; overlay is from `/monitor/snapshot`.

**Node rendering:**
- Each device node gets a colored status ring: green (`#22c55e`) = UP, amber (`#f59e0b`) = DEGRADED, red (`#ef4444`) = DOWN.
- Devices with active drift events show an orange warning triangle badge.
- Edge labels show latency in ms. Edge color: green < 20ms, amber 20-100ms, red > 100ms.
- Degraded/down edges get a CSS pulse animation.

**Click a device node → right sidebar shows:**
- Device name, IP, type, zone
- Status with duration ("DOWN since 14:32")
- Latency and packet loss
- 24h sparkline chart (from `metric_history`)
- Active drift events for this device
- Link to launch a full network diagnosis

**Bottom-left panels:**
- Drift event summary: count + top items by severity, expandable
- Discovery candidates: count + list with "Add" and "Dismiss" actions

**Header bar:**
- Tab switcher
- "Last updated: Xs ago" with auto-refresh countdown
- Aggregate health badge: "47/48 UP"

### 3.2 NOC Wall Tab

Severity-sorted device table for operations teams.

**Columns:** Status dot, Device name, IP, Latency (ms), Packet Loss (%), Drift count, "Since" (time of last status change).

**Behavior:**
- Sorted: DOWN first → DEGRADED → UP. Within each group, sorted by latency descending.
- Click a row → switches to Live Topology tab with that device selected.
- Filters: status, zone, device type. Free-text search across name/IP.
- Footer summary bar: "1 DOWN, 1 DEGRADED, 46 UP, 2 active drift events"

### 3.3 Traffic Flows Tab

Sankey diagram showing aggregate traffic between zones or subnets.

**Data source:** Aggregated from `link_metrics` + Prometheus traffic counters, grouped by zone (from KG zone assignments) or by subnet.

**Controls:**
- Group-by selector: Zone, Subnet, VPC
- Period selector: Last 1h, 24h, 7d
- Sankey bands sized by bandwidth, colored by health

**Features:**
- "Top talkers" bar below showing highest-traffic device pairs
- Click a band → drill down to individual device-to-device links

**Library:** `d3-sankey` (lightweight, d3 already a transitive dependency via mermaid).

### Frontend File Structure

```
frontend/src/components/Observatory/
├── ObservatoryView.tsx          # Page shell, 3 tabs, polling orchestration
├── LiveTopologyTab.tsx          # React Flow read-only + status overlay
├── NOCWallTab.tsx               # Severity-sorted table
├── TrafficFlowsTab.tsx          # Sankey diagram (d3-sankey)
├── DeviceStatusSidebar.tsx      # Right panel: detail + sparkline
├── DriftEventsList.tsx          # Drift summary panel
├── DiscoveryCandidates.tsx      # Discovered IPs list + promote/dismiss
└── hooks/
    └── useMonitorSnapshot.ts    # 30s polling hook
```

### Polling Hook

```typescript
// useMonitorSnapshot.ts
// Polls GET /api/v4/network/monitor/snapshot every 30s
// Returns: {
//   devices: DeviceStatus[],
//   links: LinkMetric[],
//   drifts: DriftEvent[],
//   candidates: DiscoveryCandidate[],
//   lastUpdated: Date,
//   loading: boolean,
// }
```

---

## 4. Drift Detection

**File:** `backend/src/network/drift_engine.py`

### What Gets Compared

| Entity | KG Intent (SQLite) | Live Reality (Adapter) |
|--------|-------------------|----------------------|
| Routes | `routes` table | `adapter.get_routes()` |
| Firewall Rules | `firewall_rules` table | `adapter.get_rules()` |
| Interfaces | `interfaces` table | `adapter.get_interfaces()` |
| NAT Rules | `nat_rules` table | `adapter.get_nat_rules()` |
| Zones | `zones` table | `adapter.get_zones()` |

### Drift Types

| Type | Meaning | Default Severity |
|------|---------|-----------------|
| `missing` | In KG, not on device | `critical` |
| `added` | On device, not in KG | `warning` |
| `changed` | In both, fields differ | `warning` |

**Severity auto-escalation:**
- Firewall rule `action` changed (allow↔deny) → `critical`
- Missing default route (0.0.0.0/0) → `critical`
- Firewall rule `src_ips` broadened → `critical` (security risk)
- New zone not in KG → `info`

### Diff Algorithm Pattern

Each entity type follows the same three-step diff:

1. **Load intent** from KG (e.g., `store.list_routes(device_id=...)`)
2. **Load reality** from adapter (e.g., `adapter.get_routes()`)
3. **Compare:**
   - Keys in intent but not reality → `missing`
   - Keys in reality but not intent → `added`
   - Keys in both, fields differ → `changed`

Key fields compared per entity:
- **Routes:** destination_cidr (key), next_hop, metric, protocol
- **Firewall Rules:** rule_name (key), action, src_ips, dst_ips, ports, order
- **Interfaces:** name (key), ip, zone, status
- **NAT Rules:** rule_id (key), original_src, translated_src, direction
- **Zones:** name (key), security_level

### Drift Lifecycle

```
Detected → Active → Resolved
              │
              ├─ Auto-resolved: next cycle sees intent = reality
              │  (someone fixed the device, or KG was updated)
              │
              └─ User-resolved: "Accept as Intended" button
                 (updates KG to match reality)
```

The UNIQUE constraint on `(entity_type, entity_id, drift_type, field)` prevents flapping — same drift stays as one row. Resolution clears `resolved_at` back to NULL if it reappears.

### "Accept as Intended"

When reality is correct and the KG is stale, the user clicks "Accept as Intended" in the drift detail view. This:
1. Updates the KG entity to match the live value
2. Sets `resolved_at` on the drift event
3. Prevents the drift from reappearing next cycle

### Diagnosis Integration

When a user runs a network diagnosis (`POST /diagnose`), the report generator includes active drift events for devices in the path:

> "Traffic is BLOCKED by fw-01. Note: fw-01 has 2 active drift events — rule 'block-external-ssh' action changed from deny→allow (detected 2h ago)."

Lightweight addition to `report_generator.py`.

---

## 5. Auto-Discovery

**File:** `backend/src/network/discovery_engine.py`

### Discovery Sources

| Source | How | When |
|--------|-----|------|
| Adapter neighbors | `adapter.get_interfaces()` → unknown peer IPs | Every cycle |
| Subnet probe scan | ICMP ping sweep of KG-known subnets | Every cycle (sampled) |
| Prometheus targets | `up{}` metric → unknown target IPs | Every cycle (if configured) |
| Traceroute hops | Unknown hops from diagnosis traces | On diagnosis completion |

### Subnet Scanning Safety

- Only scans subnets already in the KG — never arbitrary ranges
- Skips subnets larger than /20 (4096+ hosts)
- Samples max 50 IPs per subnet per cycle (full /24 covered in ~3 cycles)
- 2s timeout per ping, 3s outer timeout
- Full probe pass completes in <10s even with many subnets

### Enrichment

On first discovery, reverse DNS is attempted:
- `socket.gethostbyaddr(ip)` via `run_in_executor`
- Hostname stored in `discovery_candidates.hostname`
- Runs once, not every cycle

### Promotion Flow

Candidates are never auto-added to the KG. The user reviews them in the dashboard:

1. User clicks "Add" on a candidate
2. Small form opens, pre-filled with: IP, hostname, auto-resolved subnet, default type HOST
3. On submit → `POST /monitor/discover/{ip}/promote`
4. Backend creates Device + Interface in the KG
5. Sets `promoted_device_id` on the candidate row
6. Device appears in Live Topology on next probe cycle

"Dismiss" marks the candidate as ignored. Dismissed candidates don't reappear. Pruned after 7 days of no response.

---

## Files Changed / Created

### New Files

| File | Description |
|------|-------------|
| `backend/src/network/monitor.py` | NetworkMonitor — collection engine with 30s cycle |
| `backend/src/network/drift_engine.py` | DriftEngine — intent vs. reality comparison |
| `backend/src/network/discovery_engine.py` | DiscoveryEngine — find unknown devices |
| `backend/src/api/monitor_endpoints.py` | FastAPI router for /monitor/* endpoints |
| `frontend/src/components/Observatory/ObservatoryView.tsx` | Page shell with 3 tabs |
| `frontend/src/components/Observatory/LiveTopologyTab.tsx` | React Flow read-only + status overlay |
| `frontend/src/components/Observatory/NOCWallTab.tsx` | Severity-sorted device table |
| `frontend/src/components/Observatory/TrafficFlowsTab.tsx` | Sankey diagram |
| `frontend/src/components/Observatory/DeviceStatusSidebar.tsx` | Device detail panel + sparkline |
| `frontend/src/components/Observatory/DriftEventsList.tsx` | Drift summary panel |
| `frontend/src/components/Observatory/DiscoveryCandidates.tsx` | Discovered IPs list |
| `frontend/src/components/Observatory/hooks/useMonitorSnapshot.ts` | 30s polling hook |

### Modified Files

| File | Changes |
|------|---------|
| `backend/src/network/topology_store.py` | 5 new tables + store methods |
| `backend/src/api/main.py` | Register monitor_endpoints router, start/stop NetworkMonitor |
| `backend/src/agents/network/report_generator.py` | Include active drift events in diagnosis reports |
| `frontend/src/App.tsx` (or router config) | Add `/network/observatory` route |
| `frontend/src/components/Sidebar.tsx` (or nav) | Add Observatory nav item |

### New Dependencies

| Package | Purpose | Notes |
|---------|---------|-------|
| `d3-sankey` + `@types/d3-sankey` | Traffic flow Sankey diagram | Frontend only. d3 already a transitive dep. |

No new backend dependencies — `icmplib`, `asyncio`, `sqlite3` already available.

---

## Items Explicitly Out of Scope

| Item | Reason |
|------|--------|
| IPv6 probe scanning | IPv6 subnet scanning is impractical (address space too large). IPv6 devices still monitored if in KG. |
| SNMP trap receiver | Would require a UDP listener on port 162. Push-based monitoring is a future phase. |
| External TSDB (InfluxDB/TimescaleDB) | Overkill for <50 devices. SQLite metric_history with 7-day prune is sufficient. |
| Grafana embedding | Adds infrastructure complexity. Native sparklines and d3-sankey provide what's needed. |
| WebSocket push | 30s polling is sufficient for <50 devices. Can upgrade to WebSocket diffs later if needed. |
| Hierarchical drill-down | Not needed at <50 devices. Everything renders on one canvas. |

---

## Verification Plan

1. **Collection Engine:** Start monitor, verify device_status rows appear within 30s for all KG devices
2. **Probe accuracy:** Take a known device offline, verify status flips to DOWN within one cycle
3. **Drift detection:** Manually change a firewall rule via adapter, verify drift_event appears
4. **Drift resolution:** Fix the rule, verify drift auto-resolves next cycle
5. **Discovery:** Add a new device to a known subnet, verify it appears as a candidate
6. **Promotion:** Promote a candidate, verify it appears in the KG and Live Topology
7. **Dashboard:** Verify all three tabs render correctly with live data
8. **History:** Verify sparkline shows 24h of data points after running for a few minutes
9. **Fault isolation:** Kill Prometheus, verify probes and adapters still collect
10. **Metric pruning:** Verify metric_history rows older than 7 days are deleted

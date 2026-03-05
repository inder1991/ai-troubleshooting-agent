# Flow-First Network Monitoring Foundation

**Date**: 2026-03-05
**Status**: Approved
**Approach**: Approach A — Flow-First (SNMP + Flow Ingestion + Alerts + InfluxDB)

## Problem

Our monitoring is ICMP-only (ping). We can detect up/down and basic latency but have zero visibility into device health (CPU, memory), traffic patterns (who talks to whom), interface utilization, or anomalous behavior. Enterprise platforms like Datadog NPM, Kentik, and Dynatrace operate at fundamentally deeper layers.

**Current state**: ~15-20% of enterprise network monitoring capability.
**Target state**: ~70% — covering the highest-impact 70% of use cases (SNMP + flows + alerts).

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Data Sources                          │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │  SNMP    │  │ NetFlow/IPFIX│  │ Existing ICMP    │    │
│  │ Poller   │  │ /sFlow Recv  │  │ Probe (keep)     │    │
│  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘    │
│       │               │                   │               │
│  ┌────▼───────────────▼───────────────────▼───────────┐  │
│  │              MetricsPipeline                        │  │
│  │  (normalize → store → evaluate alerts → emit WS)   │  │
│  └────┬───────────────┬───────────────────┬───────────┘  │
│       │               │                   │               │
│  ┌────▼─────┐  ┌──────▼──────┐  ┌────────▼───────────┐  │
│  │ InfluxDB │  │ InfluxDB    │  │ InfluxDB           │  │
│  │ device_  │  │ link_traffic│  │ flow_summary       │  │
│  │ health   │  │             │  │                    │  │
│  └──────────┘  └─────────────┘  └────────────────────┘  │
│                       │                                   │
│  ┌────────────────────▼──────────────────────────────┐   │
│  │              AlertEngine                           │   │
│  │  (threshold rules → evaluate → notify via WS)     │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### Storage Split

- **SQLite** (keep): Application state — device inventory, drift events, discovery candidates, topology, KG
- **InfluxDB**: All time-series metrics — SNMP polls, flow records, ICMP probes, alert evaluations

### InfluxDB Schema

**Bucket**: `network_metrics`

| Measurement | Tags | Fields | Use Case |
|---|---|---|---|
| `device_health` | device_id, metric_type | value | CPU, memory, latency, packet_loss, interface stats |
| `link_traffic` | src_device, dst_device, src_port, dst_port, protocol | bytes, packets, latency_ms | Aggregated per-link traffic |
| `flow_summary` | src_ip, dst_ip, src_port, dst_port, protocol, app, exporter | bytes, packets, duration | Individual flow records |
| `alert_events` | device_id, rule_id, severity | value, threshold, message | Alert fire/resolve history |

**Retention**: 30 days raw, 1 year downsampled (5-min averages after 7 days).

## Component 1: SNMP Collector

**File**: `backend/src/network/snmp_collector.py`
**Library**: `pysnmp` (async)
**Cycle**: 30 seconds (synced with existing monitor cycle)

### Standard OIDs

```
System:       sysUpTime, sysName
CPU:          hrProcessorLoad (HOST-RESOURCES-MIB)
Memory:       memTotalReal, memAvailReal (UCD-SNMP-MIB)
Interfaces:   ifDescr, ifOperStatus, ifInOctets, ifOutOctets,
              ifInErrors, ifOutErrors, ifSpeed (IF-MIB)
```

### Rate Computation

Interface counters are cumulative. We compute rates:
- `bps_in = delta(ifInOctets) * 8 / delta_seconds`
- `bps_out = delta(ifOutOctets) * 8 / delta_seconds`
- `utilization = max(bps_in, bps_out) / ifSpeed`
- `error_rate = delta(ifInErrors + ifOutErrors) / delta(ifInOctets + ifOutOctets)`

Previous counter values stored in-memory per (device_id, ifIndex).

### Device SNMP Config

Stored as KG node attributes:
```python
{
    "snmp_version": "v2c",       # v2c or v3
    "snmp_community": "public",  # v2c only
    "snmp_port": 161,
    "snmp_v3_user": "",          # v3 only
    "snmp_v3_auth_proto": "",    # MD5, SHA
    "snmp_v3_auth_key": "",
    "snmp_v3_priv_proto": "",    # DES, AES
    "snmp_v3_priv_key": "",
}
```

### Class Design

```python
class SNMPCollector:
    def __init__(self, metrics_store: MetricsStore)
    async def poll_device(self, device_id: str, ip: str, config: dict) -> dict
    async def poll_all(self, devices: list[dict]) -> list[dict]
    def _compute_rates(self, device_id: str, if_index: int, counters: dict) -> dict
```

## Component 2: Flow Ingestion Engine

**File**: `backend/src/network/flow_receiver.py`
**Protocol**: UDP listeners for NetFlow v5/v9, IPFIX, sFlow v5
**Ports**: 2055 (NetFlow), 4739 (IPFIX), 6343 (sFlow) — configurable

### Flow Record

```python
@dataclass
class FlowRecord:
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int          # 6=TCP, 17=UDP
    bytes: int
    packets: int
    start_time: datetime
    end_time: datetime
    tcp_flags: int
    tos: int
    input_snmp: int        # ingress interface index
    output_snmp: int       # egress interface index
    src_as: int
    dst_as: int
    exporter_ip: str       # which device sent this flow
```

### Pipeline

1. **Receive** — async UDP server, parse binary packets
2. **Decode** — NetFlow v5 fixed-format decode, v9/IPFIX template-based decode
3. **Enrich** — Map exporter_ip to device_id, resolve interface names via SNMP ifIndex
4. **Store** — Write individual flows to InfluxDB `flow_summary`
5. **Aggregate** — Every 30s, roll up per (src_device, dst_device) → write to `link_traffic`

### Aggregation

Per 30-second window, compute per device pair:
- Total bytes/packets
- Average latency (if TCP RTT available)
- Protocol breakdown
- Top source/destination ports

Also update SQLite `link_metrics` table for backward compatibility with existing Observatory UI.

## Component 3: MetricsStore (InfluxDB Abstraction)

**File**: `backend/src/network/metrics_store.py`

```python
class MetricsStore:
    def __init__(self, url: str, token: str, org: str, bucket: str)
    async def write_device_metric(self, device_id: str, metric: str, value: float)
    async def write_link_metric(self, src: str, dst: str, **fields)
    async def write_flow(self, flow: FlowRecord)
    async def write_alert_event(self, alert: Alert)
    async def query_device_metrics(self, device_id: str, metric: str,
                                    range: str = "1h", resolution: str = "30s") -> list
    async def query_top_talkers(self, window: str = "5m", limit: int = 20) -> list
    async def query_traffic_matrix(self, window: str = "15m") -> dict
    async def query_protocol_breakdown(self, window: str = "1h") -> list
    async def health_check(self) -> bool
    async def setup_retention_policies(self)
    async def close(self)
```

Graceful degradation: if InfluxDB is unavailable, log warning and skip writes (don't crash the monitor loop).

## Component 4: Alert Engine

**File**: `backend/src/network/alert_engine.py`
**Evaluation cycle**: Every 30 seconds (after metrics are written)

### Alert Rule

```python
@dataclass
class AlertRule:
    id: str
    name: str
    description: str
    severity: str              # critical, warning, info
    entity_type: str           # device, link, interface
    entity_filter: str         # "*" or device_id or tag match
    metric: str                # cpu_pct, mem_pct, latency_ms, etc.
    condition: str             # gt, lt, eq, rate_increase, absent
    threshold: float
    duration_seconds: int      # must exceed for this long
    cooldown_seconds: int      # don't re-fire for this long
    enabled: bool
```

### Alert Lifecycle

```
PENDING → FIRING → RESOLVED → PENDING (can fire again after cooldown)
```

### Default Rules (shipped out of box)

| Rule | Metric | Condition | Threshold | Duration | Severity |
|---|---|---|---|---|---|
| Device Unreachable | probe_response | absent | — | 90s | critical |
| High CPU | cpu_pct | > | 90% | 5 min | warning |
| High Memory | mem_pct | > | 95% | 5 min | warning |
| Interface Errors | error_rate | > | 1% | 5 min | warning |
| Link Saturation | utilization | > | 85% | 10 min | warning |
| Latency Spike | latency_ms | > | 200ms | 2 min | warning |

### Notifications (MVP)

- WebSocket push → frontend toast + bell badge
- Alert history in InfluxDB `alert_events`
- Future: webhook, Slack, PagerDuty, email

## Component 5: API Endpoints

Added to `/api/v4/network/monitor/`:

```
# SNMP
GET  /snmp/devices                            → SNMP-enabled devices + poll status
POST /snmp/devices/{id}/credentials           → Set SNMP credentials
GET  /snmp/devices/{id}/metrics               → Current SNMP metrics

# Flows
GET  /flows/top-talkers?window=5m&limit=20    → Top N flows by bytes
GET  /flows/traffic-matrix?window=15m         → Device-to-device bandwidth matrix
GET  /flows/protocols?window=1h               → Protocol breakdown
GET  /flows/device/{id}?window=1h             → Flows for specific device

# Metrics (InfluxDB time-series)
GET  /metrics/{entity_type}/{entity_id}/{metric}?from=1h&resolution=30s

# Alerts
GET    /alerts                                → Active alerts
GET    /alerts/history?from=24h               → Alert history
POST   /alerts/{id}/acknowledge               → Mute alert
GET    /alerts/rules                          → List rules
POST   /alerts/rules                          → Create rule
PUT    /alerts/rules/{id}                     → Update rule
DELETE /alerts/rules/{id}                     → Delete rule

# Config
GET  /config/influxdb/status                  → InfluxDB connection health
POST /config/flow-receiver/ports              → Configure listener ports
```

## Component 6: Frontend — Observatory Enhancements

### Device Health Tab (replaces basic NOC Wall)
- Card grid per device: CPU gauge, Memory gauge, Status dot, Uptime
- Sparkline charts (last 1hr) for CPU, memory, latency
- Click device → sidebar with full metric history (line charts, 1h/6h/24h/7d selectors)

### Traffic Flows Tab (enhance existing empty tab)
- Top Talkers table: src → dst, bandwidth, packets, protocol
- Traffic Matrix heatmap: NxN device grid colored by bandwidth
- Protocol Breakdown bar chart
- Time range selector: 5m / 15m / 1h / 6h / 24h

### Alerts Tab (new)
- Active alerts list with severity badge, device name, metric value vs threshold
- Alert timeline (last 24h) fire/resolve events
- Acknowledge button
- Rule management modal: enable/disable, edit thresholds

### Live Topology Enhancements
- Link color by utilization: green (<50%) → yellow (50-80%) → red (>80%)
- Link width scaled by bandwidth
- Device icon ring shows CPU gauge
- Hover link → tooltip: bandwidth, latency, error rate, utilization

### Alert Bell (global)
- Top-right notification bell with unread count
- Click → dropdown of recent alerts
- Integrates with existing `ToastContext`

## Build Order

```
Week 1: Foundation
├── MetricsStore class (InfluxDB client wrapper)
├── InfluxDB setup (bucket, retention policies, downsampling)
├── SNMPCollector (pysnmp, standard OIDs, rate computation)
├── Activate NetworkMonitor (wire into main.py startup)
├── Migrate ICMP probe metrics to write to InfluxDB
└── SNMP API endpoints + credentials management

Week 2: Flow Engine
├── FlowReceiver (async UDP server)
├── FlowParser (NetFlow v5/v9 decoder)
├── Flow aggregation pipeline (30s windows)
├── Flow API endpoints (top-talkers, traffic matrix, protocols)
└── Backfill link_metrics table from flow data

Week 3: Alerts + Frontend
├── AlertEngine (rule evaluation, lifecycle, cooldown)
├── Default alert rules + CRUD API
├── Observatory: Device Health tab with sparklines + gauges
├── Observatory: Traffic Flows tab with tables + charts
├── Observatory: Alerts tab + bell notification
└── Live Topology: link coloring + device CPU ring
```

## Dependencies

- `influxdb-client[async]` — InfluxDB Python client with async support
- `pysnmp` — SNMP v2c/v3 async poller
- `recharts` or `lightweight-charts` — Frontend charting (if not already available)

## Integration with Existing Systems

- **AI Diagnosis**: Feed SNMP + flow metrics into diagnosis context. When user reports "network slow", AI can query InfluxDB for CPU spikes, traffic anomalies, interface errors.
- **Drift Detection**: Drift engine continues as-is. Alert engine runs in parallel.
- **Knowledge Graph**: SNMP credentials stored as KG node attributes. Flow exporter_ip mapped to KG device_id.
- **Observatory UI**: Enhanced tabs replace current placeholders. Same polling pattern via `useMonitorSnapshot`.

## What This Doesn't Cover (Future Phases)

- Synthetic monitoring (HTTP/TCP/DNS probes)
- BGP monitoring / route hijack detection
- DDoS detection
- Deep packet inspection
- Cloud VPC flow log ingestion
- ML-based anomaly detection (adaptive baselines)
- Multi-tenancy / RBAC on alert rules

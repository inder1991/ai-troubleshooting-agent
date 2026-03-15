# Network Monitoring Gaps — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Activate 4 dormant collectors (SNMP, NetFlow, syslog/traps, ping probes), build 4 vendor health collectors (Cisco, F5, Palo Alto, Checkpoint), and build 4 new features (auto-discovery, config drift, alert thresholds, time-series storage) — closing all 12 SolarWinds NPM capability gaps.

**Architecture:** Each collector runs as an async background task. Metrics stored in SQLite time-series tables (Phase 1) with InfluxDB migration path (Phase 2). Collectors feed the Observatory UI via REST polling. Alert engine evaluates thresholds against collected metrics.

**Tech Stack:** Python asyncio (collectors), SNMP via pysnmp/pynetsnmp, Paramiko/Netmiko (SSH), SQLite (time-series), FastAPI (endpoints)

**Dependency:** Fixture data (enterprise network mock plan) should be loaded AFTER these gaps are fixed, so mock devices have real metric collection flowing through them.

---

## Tier 1: Activate Dormant Code (Tasks 1-4)

### Task 1: Activate SNMP Collector + Time-Series Storage

**Files:**
- Modify: `backend/src/network/snmp_collector.py` (activate, wire to scheduler)
- Create: `backend/src/network/metrics_store.py` (SQLite time-series storage)
- Modify: `backend/src/api/main.py` (start collector on startup)
- Create: `backend/src/api/network_metrics_endpoints.py` (REST endpoints for Observatory)

**What exists:** `snmp_collector.py` has MIB registry, OID definitions for IF-MIB (interface counters), HOST-RESOURCES-MIB (CPU/memory), and vendor MIBs. It can poll a device and return structured metrics. But it's never called.

**What to build:**

**1a. Time-series metrics store (SQLite)**

```python
# backend/src/network/metrics_store.py

"""SQLite-based time-series metrics store.

Schema:
  device_metrics: timestamp, device_id, metric_name, metric_value, unit
  interface_metrics: timestamp, device_id, interface_name, metric_name, metric_value, unit

Retention: 7 days default, configurable.
Downsampling: 1-minute raw → 5-minute avg after 24h → 1-hour avg after 7d.
"""

import sqlite3
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent.parent.parent / "data" / "metrics.db"

class MetricsStore:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS device_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                device_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                unit TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_dm_device_ts ON device_metrics(device_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_dm_ts ON device_metrics(timestamp);

            CREATE TABLE IF NOT EXISTS interface_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                device_id TEXT NOT NULL,
                interface_name TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                unit TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_im_device_ts ON interface_metrics(device_id, timestamp);

            CREATE TABLE IF NOT EXISTS probe_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                target_ip TEXT NOT NULL,
                probe_type TEXT NOT NULL,
                latency_ms REAL,
                packet_loss_pct REAL,
                status TEXT DEFAULT 'ok'
            );
            CREATE INDEX IF NOT EXISTS idx_pm_target_ts ON probe_metrics(target_ip, timestamp);
        """)
        conn.close()

    def write_device_metric(self, device_id, metric_name, value, unit=""):
        ...
    def write_interface_metric(self, device_id, interface_name, metric_name, value, unit=""):
        ...
    def write_probe_metric(self, target_ip, probe_type, latency_ms, packet_loss_pct, status):
        ...
    def query_device_metrics(self, device_id, metric_name, start_ts, end_ts, interval="1m"):
        ...
    def query_interface_metrics(self, device_id, interface_name, metric_name, start_ts, end_ts):
        ...
    def cleanup_old_metrics(self, retention_days=7):
        ...
```

**1b. SNMP polling scheduler**

```python
# Add to snmp_collector.py or create snmp_scheduler.py

class SNMPPollingScheduler:
    """Polls all SNMP-enabled devices every interval."""

    def __init__(self, metrics_store: MetricsStore, kg: KnowledgeGraph, interval_seconds: int = 60):
        self.store = metrics_store
        self.kg = kg
        self.interval = interval_seconds
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            devices = self._get_snmp_devices()  # From KG: devices with SNMP community/credentials
            tasks = [self._poll_device(d) for d in devices]
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(self.interval)

    async def _poll_device(self, device: dict):
        """Poll one device for CPU, memory, interface counters."""
        ip = device.get("management_ip", "")
        community = device.get("snmp_community", "public")

        # Device-level: CPU, memory
        cpu = await snmp_get(ip, community, OID_CPU_LOAD_1MIN)
        memory = await snmp_get(ip, community, OID_MEMORY_USED_PCT)
        self.store.write_device_metric(device["id"], "cpu_pct", cpu)
        self.store.write_device_metric(device["id"], "memory_pct", memory)

        # Interface-level: bps_in, bps_out, errors_in, errors_out, discards
        interfaces = await snmp_walk(ip, community, OID_IF_TABLE)
        for iface in interfaces:
            self.store.write_interface_metric(device["id"], iface["name"], "bps_in", iface["in_octets_rate"] * 8)
            self.store.write_interface_metric(device["id"], iface["name"], "bps_out", iface["out_octets_rate"] * 8)
            self.store.write_interface_metric(device["id"], iface["name"], "errors_in", iface["in_errors"])
            self.store.write_interface_metric(device["id"], iface["name"], "errors_out", iface["out_errors"])

    def stop(self):
        self._running = False
```

**1c. REST endpoints for Observatory**

```python
# backend/src/api/network_metrics_endpoints.py

@router.get("/devices/{device_id}/metrics")
async def get_device_metrics(device_id: str, metric: str = "cpu_pct", range: str = "1h"):
    """Get time-series metrics for a device."""

@router.get("/devices/{device_id}/interfaces/{interface_name}/metrics")
async def get_interface_metrics(device_id: str, interface_name: str, range: str = "1h"):
    """Get interface utilization, errors, discards."""

@router.get("/devices/{device_id}/health")
async def get_device_health(device_id: str):
    """Get latest CPU, memory, interface summary for a device."""

@router.get("/monitoring/summary")
async def get_monitoring_summary():
    """Aggregate: devices polled, total interfaces, alerts, overall health."""
```

**1d. Wire to startup**

In `main.py`:
```python
@app.on_event("startup")
async def startup():
    metrics_store = MetricsStore()
    snmp_scheduler = SNMPPollingScheduler(metrics_store, knowledge_graph)
    asyncio.create_task(snmp_scheduler.start())
```

**Commit:** `feat(monitoring): activate SNMP collector with SQLite time-series storage`

---

### Task 2: Activate NetFlow Receiver

**Files:**
- Modify: `backend/src/network/flow_receiver.py` (start UDP listener)
- Create: `backend/src/network/flow_store.py` (flow aggregation storage)
- Create: `backend/src/api/network_flow_endpoints.py` (REST endpoints)
- Modify: `backend/src/api/main.py` (start receiver on startup)

**What exists:** `flow_receiver.py` has NetFlow v5/v9/IPFIX parsers and biflow stitching.

**What to build:**

**2a. Flow aggregation store**

```python
# backend/src/network/flow_store.py

class FlowStore:
    """Aggregates NetFlow/IPFIX records into queryable summaries."""

    def ingest_flow(self, flow: dict):
        """Store a parsed flow record."""

    def get_top_talkers(self, time_range="1h", limit=20) -> list[dict]:
        """Top source IPs by bytes."""

    def get_top_applications(self, time_range="1h", limit=20) -> list[dict]:
        """Top destination ports / application protocols."""

    def get_conversations(self, time_range="1h", limit=20) -> list[dict]:
        """Top src→dst pairs by bytes."""

    def get_protocol_breakdown(self, time_range="1h") -> dict:
        """TCP vs UDP vs ICMP vs other."""

    def get_volume_timeline(self, time_range="1h", interval="5m") -> list[dict]:
        """Bytes over time bucketed by interval."""

    def get_asn_breakdown(self, time_range="1h") -> list[dict]:
        """Traffic by ASN (if ASN data in flow records)."""
```

**2b. Activate UDP listener**

```python
# In main.py startup:
flow_receiver = FlowReceiver(port=2055, flow_store=flow_store)
asyncio.create_task(flow_receiver.start())
```

**2c. REST endpoints**

```python
@router.get("/flows/top-talkers")
@router.get("/flows/applications")
@router.get("/flows/conversations")
@router.get("/flows/protocols")
@router.get("/flows/volume")
```

**Commit:** `feat(monitoring): activate NetFlow receiver with flow aggregation`

---

### Task 3: Activate Syslog + SNMP Trap Listeners

**Files:**
- Modify: `backend/src/network/syslog_listener.py` (start)
- Modify: `backend/src/network/trap_listener.py` (start)
- Create: `backend/src/network/event_store.py` (event storage + correlation)
- Create: `backend/src/api/network_event_endpoints.py`
- Modify: `backend/src/api/main.py`

**What exists:** `syslog_listener.py` parses Cisco/PA/CP syslog. `trap_listener.py` handles SNMP v2c/v3 traps.

**What to build:**

**3a. Event store**

```python
class EventStore:
    """Stores syslog messages, SNMP traps, and webhook events."""

    def ingest_syslog(self, source_ip, facility, severity, message, timestamp):
        ...
    def ingest_trap(self, source_ip, oid, value, timestamp):
        ...
    def ingest_webhook(self, source, event_type, payload, timestamp):
        ...
    def get_events(self, device_id=None, severity=None, time_range="1h", limit=100):
        ...
    def get_event_rate(self, time_range="1h", interval="5m"):
        """Events per interval for timeline chart."""
    def acknowledge_event(self, event_id, user):
        ...
```

**3b. Start listeners**

```python
# Syslog: UDP 514
syslog_listener = SyslogListener(port=514, event_store=event_store)
asyncio.create_task(syslog_listener.start())

# SNMP Traps: UDP 162
trap_listener = TrapListener(port=162, event_store=event_store)
asyncio.create_task(trap_listener.start())
```

**3c. REST endpoints**

```python
@router.get("/events")  # Filterable by device, severity, time
@router.get("/events/rate")  # Timeline chart data
@router.post("/events/{id}/acknowledge")
@router.get("/events/unacknowledged/count")  # For bell badge
```

**Commit:** `feat(monitoring): activate syslog + SNMP trap listeners with event store`

---

### Task 4: Activate Ping Probes

**Files:**
- Modify: `backend/src/network/ping_prober.py` (start scheduler)
- Modify: `backend/src/api/main.py`
- Add endpoints to `network_metrics_endpoints.py`

**What exists:** `ping_prober.py` has ICMP probe logic with RTT histograms.

**What to build:**

**4a. Probe scheduler**

```python
class PingProbeScheduler:
    """Probes configured targets every interval."""

    def __init__(self, metrics_store, targets: list[dict], interval=30):
        self.store = metrics_store
        self.targets = targets  # [{"ip": "10.1.40.10", "name": "pa-core-fw-01"}]
        self.interval = interval

    async def start(self):
        while True:
            for target in self.targets:
                result = await ping(target["ip"], count=3, timeout=2)
                self.store.write_probe_metric(
                    target["ip"], "icmp",
                    result.avg_rtt_ms, result.packet_loss_pct,
                    "ok" if result.packet_loss_pct == 0 else "degraded"
                )
            await asyncio.sleep(self.interval)
```

**4b. Endpoints**

```python
@router.get("/probes")  # List configured targets with latest status
@router.get("/probes/{target_ip}/history")  # RTT + loss over time
@router.post("/probes")  # Add probe target
@router.delete("/probes/{target_ip}")  # Remove
```

**Commit:** `feat(monitoring): activate ping probes with RTT/loss tracking`

---

## Tier 2: Vendor Health Collectors (Tasks 5-8)

### Task 5: Cisco Health Collector

**Files:**
- Create: `backend/src/network/collectors/cisco_collector.py`

Collects via SNMP + SSH:

```python
class CiscoHealthCollector:
    """Collects health metrics from Cisco IOS-XE/NX-OS devices."""

    async def collect(self, device: dict, metrics_store: MetricsStore):
        ip = device["management_ip"]

        # SNMP: CPU, memory, interface counters (generic, already in SNMP collector)
        # These come from Task 1's SNMP polling

        # SSH-specific (Cisco show commands):
        ssh = await connect_ssh(ip, device["credentials"])

        # BGP neighbor state
        bgp_output = await ssh.execute("show ip bgp summary")
        bgp_peers = parse_bgp_summary(bgp_output)
        for peer in bgp_peers:
            metrics_store.write_device_metric(device["id"], f"bgp_peer_{peer['neighbor']}_state", 1 if peer["state"] == "Established" else 0)
            metrics_store.write_device_metric(device["id"], f"bgp_peer_{peer['neighbor']}_prefixes", peer["prefixes_received"])

        # OSPF neighbor state
        ospf_output = await ssh.execute("show ip ospf neighbor")
        ospf_neighbors = parse_ospf_neighbors(ospf_output)
        metrics_store.write_device_metric(device["id"], "ospf_neighbor_count", len(ospf_neighbors))

        # QoS class-map drops
        qos_output = await ssh.execute("show policy-map interface")
        qos_drops = parse_qos_drops(qos_output)
        for cls, drops in qos_drops.items():
            metrics_store.write_device_metric(device["id"], f"qos_drops_{cls}", drops)

        # Routing table size
        route_output = await ssh.execute("show ip route summary")
        route_count = parse_route_count(route_output)
        metrics_store.write_device_metric(device["id"], "route_table_size", route_count)

        # GRE tunnel keepalive
        tunnel_output = await ssh.execute("show interface tunnel 100")
        tunnel_status = parse_tunnel_status(tunnel_output)
        metrics_store.write_device_metric(device["id"], "gre_tunnel_100_up", 1 if tunnel_status == "up" else 0)
```

**Commit:** `feat(monitoring): Cisco health collector (BGP, OSPF, QoS, GRE, routes)`

---

### Task 6: F5 BIG-IP Health Collector

**Files:**
- Create: `backend/src/network/collectors/f5_collector.py`

Collects via iControl REST:

```python
class F5HealthCollector:
    """Collects health metrics from F5 BIG-IP via iControl REST."""

    async def collect(self, device: dict, metrics_store: MetricsStore):
        base_url = f"https://{device['management_ip']}"
        auth = (device["credentials"]["username"], device["credentials"]["password"])

        # Virtual server stats
        vips = await http_get(f"{base_url}/mgmt/tm/ltm/virtual/stats", auth=auth)
        for vip_name, stats in vips.items():
            metrics_store.write_device_metric(device["id"], f"vip_{vip_name}_status", 1 if stats["status"] == "available" else 0)
            metrics_store.write_device_metric(device["id"], f"vip_{vip_name}_connections", stats["clientside.curConns"])
            metrics_store.write_device_metric(device["id"], f"vip_{vip_name}_bps_in", stats["clientside.bitsIn"])
            metrics_store.write_device_metric(device["id"], f"vip_{vip_name}_bps_out", stats["clientside.bitsOut"])

        # Pool member health
        pools = await http_get(f"{base_url}/mgmt/tm/ltm/pool/members/stats", auth=auth)
        for pool_name, members in pools.items():
            up = sum(1 for m in members if m["status"] == "up")
            total = len(members)
            metrics_store.write_device_metric(device["id"], f"pool_{pool_name}_members_up", up)
            metrics_store.write_device_metric(device["id"], f"pool_{pool_name}_members_total", total)

        # SSL TPS
        ssl_stats = await http_get(f"{base_url}/mgmt/tm/sys/performance/ssl", auth=auth)
        metrics_store.write_device_metric(device["id"], "ssl_tps", ssl_stats.get("sslTps", 0))

        # Certificate expiry
        certs = await http_get(f"{base_url}/mgmt/tm/sys/file/ssl-cert", auth=auth)
        for cert in certs:
            days_left = (cert["expirationDate"] - time.time()) / 86400
            metrics_store.write_device_metric(device["id"], f"cert_{cert['name']}_days_left", days_left)

        # TMM memory/CPU
        tmm_stats = await http_get(f"{base_url}/mgmt/tm/sys/tmm-info/stats", auth=auth)
        metrics_store.write_device_metric(device["id"], "tmm_memory_pct", tmm_stats.get("memoryUsed_pct", 0))
        metrics_store.write_device_metric(device["id"], "tmm_cpu_pct", tmm_stats.get("oneMinAvgUsageRatio", 0))

        # HA sync status
        ha_stats = await http_get(f"{base_url}/mgmt/tm/cm/sync-status", auth=auth)
        metrics_store.write_device_metric(device["id"], "ha_sync_status", 1 if "In Sync" in str(ha_stats) else 0)
```

**Commit:** `feat(monitoring): F5 health collector (VIPs, pools, SSL, certs, TMM, HA)`

---

### Task 7: Palo Alto Health Collector

**Files:**
- Create: `backend/src/network/collectors/paloalto_collector.py`

Collects via PAN-OS XML API:

```python
class PaloAltoHealthCollector:
    """Collects health metrics from Palo Alto via XML API."""

    async def collect(self, device: dict, metrics_store: MetricsStore):
        base_url = f"https://{device['management_ip']}/api"
        api_key = device["credentials"]["api_key"]

        # System info (CPU, memory, session count)
        sys_info = await xml_api_call(base_url, api_key, "<show><system><info></info></system></show>")
        metrics_store.write_device_metric(device["id"], "cpu_pct", parse_xml_value(sys_info, "cpu-load-average/entry[1]/coreavg"))

        # Session count
        session_info = await xml_api_call(base_url, api_key, "<show><session><info></info></session></show>")
        metrics_store.write_device_metric(device["id"], "session_count", parse_xml_value(session_info, "num-active"))
        metrics_store.write_device_metric(device["id"], "session_max", parse_xml_value(session_info, "num-max"))

        # Throughput
        throughput = await xml_api_call(base_url, api_key, "<show><system><state><filter>sys.s1.p*.stats</filter></state></system></show>")
        metrics_store.write_device_metric(device["id"], "throughput_kbps", parse_throughput(throughput))

        # Threat hits
        threat_stats = await xml_api_call(base_url, api_key, "<show><threat><id><all></all></id></threat></show>")
        metrics_store.write_device_metric(device["id"], "threat_hits_total", parse_threat_count(threat_stats))

        # SSL decryption
        ssl_stats = await xml_api_call(base_url, api_key, "<show><system><setting><ssl-decrypt></ssl-decrypt></setting></system></show>")
        metrics_store.write_device_metric(device["id"], "ssl_decrypt_sessions", parse_xml_value(ssl_stats, "current-sessions"))

        # HA state
        ha_state = await xml_api_call(base_url, api_key, "<show><high-availability><state></state></high-availability></show>")
        metrics_store.write_device_metric(device["id"], "ha_state", 1 if "active" in str(ha_state).lower() else 0)
        metrics_store.write_device_metric(device["id"], "ha_peer_state", parse_xml_value(ha_state, "peer-info/state"))

        # GlobalProtect VPN
        gp_stats = await xml_api_call(base_url, api_key, "<show><global-protect-gateway><statistics></statistics></global-protect-gateway></show>")
        metrics_store.write_device_metric(device["id"], "gp_users_connected", parse_xml_value(gp_stats, "TotalCurrentUsers"))

        # Packet buffer utilization
        dp_stats = await xml_api_call(base_url, api_key, "<show><running><resource-monitor></resource-monitor></running></show>")
        metrics_store.write_device_metric(device["id"], "packet_buffer_pct", parse_xml_value(dp_stats, "dp/resource/packet-buffer"))
```

**Commit:** `feat(monitoring): Palo Alto health collector (sessions, threats, SSL, HA, GP, buffers)`

---

### Task 8: Checkpoint Health Collector

**Files:**
- Create: `backend/src/network/collectors/checkpoint_collector.py`

Collects via Checkpoint Management API (HTTPS):

```python
class CheckpointHealthCollector:
    """Collects health metrics from Checkpoint via Management API."""

    async def collect(self, device: dict, metrics_store: MetricsStore):
        base_url = f"https://{device['management_ip']}/web_api"
        sid = await cp_login(base_url, device["credentials"])

        # Gateway status
        gateways = await cp_api_call(base_url, sid, "show-gateways", {})
        for gw in gateways.get("objects", []):
            status = gw.get("sic-state", "unknown")
            metrics_store.write_device_metric(device["id"], f"gw_{gw['name']}_sic_state", 1 if status == "communicating" else 0)

        # ClusterXL state
        cluster_status = await cp_api_call(base_url, sid, "show-simple-cluster", {"name": device.get("cluster_name", "")})
        members = cluster_status.get("cluster-members", [])
        for member in members:
            metrics_store.write_device_metric(device["id"], f"cluster_{member['name']}_state", member.get("status", ""))

        # Connection table
        conn_stats = await cp_api_call(base_url, sid, "show-gateway-counters", {"gateway": device["id"]})
        metrics_store.write_device_metric(device["id"], "connection_count", conn_stats.get("concurrent-connections", 0))
        metrics_store.write_device_metric(device["id"], "connection_peak", conn_stats.get("peak-connections", 0))

        # Policy installation status
        policy_status = await cp_api_call(base_url, sid, "show-access-policy", {})
        last_install = policy_status.get("last-install-time", "")
        metrics_store.write_device_metric(device["id"], "policy_install_age_hours", hours_since(last_install))

        # IPS signature database version
        ips_status = await cp_api_call(base_url, sid, "show-threat-prevention", {})
        metrics_store.write_device_metric(device["id"], "ips_signature_version", ips_status.get("installed-version", ""))

        await cp_logout(base_url, sid)
```

**Commit:** `feat(monitoring): Checkpoint health collector (SIC, ClusterXL, connections, IPS)`

---

## Tier 3: New Features (Tasks 9-12)

### Task 9: Auto-Discovery (LLDP/CDP/ARP)

**Files:**
- Modify: `backend/src/network/autodiscovery.py` (activate)
- Create: `backend/src/network/discovery_scheduler.py`
- Create: `backend/src/api/network_discovery_endpoints.py`

**What to build:**

```python
class DiscoveryScheduler:
    """Periodically discovers network neighbors via LLDP/CDP/ARP."""

    async def discover_device(self, device: dict):
        ip = device["management_ip"]
        neighbors = []

        # LLDP via SNMP (LLDP-MIB)
        lldp = await snmp_walk(ip, community, OID_LLDP_REMOTE_TABLE)
        for entry in lldp:
            neighbors.append({
                "local_port": entry["local_port"],
                "remote_device": entry["remote_sys_name"],
                "remote_port": entry["remote_port_desc"],
                "remote_ip": entry.get("remote_mgmt_addr", ""),
                "protocol": "LLDP",
            })

        # CDP via SNMP (CISCO-CDP-MIB) — Cisco only
        if device.get("vendor") == "Cisco":
            cdp = await snmp_walk(ip, community, OID_CDP_CACHE_TABLE)
            for entry in cdp:
                neighbors.append({...})

        # ARP table via SNMP (IP-MIB)
        arp = await snmp_walk(ip, community, OID_IP_NET_TO_MEDIA_TABLE)

        return neighbors

    async def run_discovery(self):
        """Discover all devices, update KG edges."""
        devices = self.kg.get_all_devices()
        for device in devices:
            neighbors = await self.discover_device(device)
            for neighbor in neighbors:
                self.kg.add_or_update_edge(device["id"], neighbor["remote_device"], "connected", neighbor["local_port"], neighbor["remote_port"])
```

**Endpoints:**
```python
@router.post("/discovery/run")  # Trigger manual discovery
@router.get("/discovery/results")  # Latest discovery results
@router.get("/discovery/candidates")  # Newly discovered devices not yet in inventory
```

**Commit:** `feat(monitoring): auto-discovery via LLDP/CDP/ARP with KG edge updates`

---

### Task 10: Configuration Drift Detection

**Files:**
- Modify: `backend/src/network/drift_engine.py` (activate)
- Create: `backend/src/network/config_backup.py`
- Create: `backend/src/api/network_drift_endpoints.py`

**What to build:**

```python
class ConfigBackupScheduler:
    """Backs up device configs and detects drift."""

    async def backup_device(self, device: dict) -> str:
        """Fetch running config via SSH."""
        ssh = await connect_ssh(device["management_ip"], device["credentials"])

        if device["vendor"] == "Cisco":
            config = await ssh.execute("show running-config")
        elif device["vendor"] == "Palo Alto Networks":
            config = await ssh.execute("show config running")
        elif device["vendor"] == "F5 Networks":
            config = await http_get(f"https://{device['management_ip']}/mgmt/tm/sys/config", auth=...)
        elif device["vendor"] == "Checkpoint":
            config = await cp_api_call(..., "show-configuration", {})
        else:
            config = ""

        return config

    async def detect_drift(self, device_id: str, current_config: str):
        """Compare current config against baseline, generate diff."""
        baseline = self.db.get_latest_baseline(device_id)
        if not baseline:
            self.db.store_baseline(device_id, current_config)
            return None

        diff = unified_diff(baseline.splitlines(), current_config.splitlines(), lineterm="")
        diff_text = "\n".join(diff)

        if diff_text:
            self.db.store_drift_event(device_id, diff_text, timestamp=now())
            return {"device_id": device_id, "lines_changed": len(diff_text.splitlines()), "diff": diff_text}
        return None
```

**Config storage schema:**
```sql
CREATE TABLE config_baselines (
    id INTEGER PRIMARY KEY,
    device_id TEXT NOT NULL,
    config_text TEXT NOT NULL,
    captured_at REAL NOT NULL
);
CREATE TABLE drift_events (
    id INTEGER PRIMARY KEY,
    device_id TEXT NOT NULL,
    diff_text TEXT NOT NULL,
    lines_changed INTEGER,
    detected_at REAL NOT NULL,
    acknowledged INTEGER DEFAULT 0
);
```

**Endpoints:**
```python
@router.get("/drift/events")  # List drift events
@router.get("/drift/events/{device_id}")  # Drift history for a device
@router.post("/drift/baseline/{device_id}")  # Set new baseline
@router.post("/drift/scan")  # Run manual drift scan
```

**Commit:** `feat(monitoring): config drift detection with backup and diff`

---

### Task 11: Alert Threshold Engine

**Files:**
- Modify: `backend/src/network/alert_engine.py` (activate)
- Create: `backend/src/network/alert_rules.py`
- Create: `backend/src/api/network_alert_endpoints.py`

**What to build:**

```python
# Default threshold rules
DEFAULT_ALERT_RULES = [
    {"id": "cpu_high", "metric": "cpu_pct", "operator": ">", "threshold": 80, "severity": "warning", "duration_seconds": 300},
    {"id": "cpu_critical", "metric": "cpu_pct", "operator": ">", "threshold": 95, "severity": "critical", "duration_seconds": 60},
    {"id": "memory_high", "metric": "memory_pct", "operator": ">", "threshold": 85, "severity": "warning", "duration_seconds": 300},
    {"id": "interface_util_high", "metric": "interface_util_pct", "operator": ">", "threshold": 90, "severity": "warning", "duration_seconds": 300},
    {"id": "interface_errors", "metric": "errors_in", "operator": ">", "threshold": 100, "severity": "warning", "duration_seconds": 60},
    {"id": "bgp_down", "metric": "bgp_peer_*_state", "operator": "==", "threshold": 0, "severity": "critical", "duration_seconds": 0},
    {"id": "ha_desync", "metric": "ha_sync_status", "operator": "==", "threshold": 0, "severity": "critical", "duration_seconds": 0},
    {"id": "ping_loss", "metric": "packet_loss_pct", "operator": ">", "threshold": 5, "severity": "warning", "duration_seconds": 60},
    {"id": "cert_expiry", "metric": "cert_*_days_left", "operator": "<", "threshold": 14, "severity": "warning", "duration_seconds": 0},
    {"id": "gre_tunnel_down", "metric": "gre_tunnel_*_up", "operator": "==", "threshold": 0, "severity": "critical", "duration_seconds": 0},
]

class AlertEngine:
    """Evaluates threshold rules against collected metrics."""

    def __init__(self, metrics_store, event_store, rules=DEFAULT_ALERT_RULES):
        ...

    async def evaluate(self):
        """Run all rules against latest metrics, generate alerts."""
        for rule in self.rules:
            devices = self.get_devices_with_metric(rule["metric"])
            for device_id in devices:
                value = self.metrics_store.get_latest(device_id, rule["metric"])
                if self._evaluate_condition(value, rule["operator"], rule["threshold"]):
                    if self._sustained(device_id, rule, rule["duration_seconds"]):
                        self.event_store.create_alert(
                            device_id=device_id,
                            rule_id=rule["id"],
                            severity=rule["severity"],
                            metric=rule["metric"],
                            value=value,
                            threshold=rule["threshold"],
                        )

    async def start(self, interval=30):
        """Evaluate rules every interval seconds."""
        while True:
            await self.evaluate()
            await asyncio.sleep(interval)
```

**Endpoints:**
```python
@router.get("/alerts")  # List active alerts (filterable)
@router.get("/alerts/active/count")  # For notification badge
@router.post("/alerts/{id}/acknowledge")
@router.get("/alert-rules")  # List threshold rules
@router.post("/alert-rules")  # Create custom rule
@router.put("/alert-rules/{id}")  # Update rule
@router.delete("/alert-rules/{id}")  # Delete rule
```

**Commit:** `feat(monitoring): alert threshold engine with default rules`

---

### Task 12: Wire Observatory UI to Real Endpoints

**Files:**
- Modify: `frontend/src/components/Observatory/ObservatoryView.tsx`
- Modify: `frontend/src/components/Observatory/` (all tabs)
- Modify: `frontend/src/services/api.ts` (add monitoring API functions)

Replace placeholder data in Observatory with real API calls:

**Device Health tab:**
- Call `GET /monitoring/summary` for overview
- Call `GET /devices/{id}/health` per device for CPU/memory/interface
- Call `GET /devices/{id}/metrics?metric=cpu_pct&range=1h` for sparklines

**Traffic Flows tab:**
- Call `GET /flows/top-talkers` for top talkers table
- Call `GET /flows/applications` for application breakdown
- Call `GET /flows/volume` for volume timeline chart
- Show "Configure NetFlow" if no flow data returned

**Alerts tab:**
- Call `GET /alerts` for active alerts list
- Call `GET /alerts/active/count` for bell badge
- Call `POST /alerts/{id}/acknowledge` for ack button
- Call `GET /events` for syslog/trap event log

**DNS tab:**
- Call `GET /probes?type=dns` for DNS probe results
- Show "Configure DNS probes" if none configured

**Each tab falls back to the honest empty state (from earlier plan) when no data is available.**

**Commit:** `feat(observatory): wire all tabs to real monitoring endpoints`

---

## Implementation Order

```
Task 1: SNMP Collector + Metrics Store (foundation — everything depends on this)
  ↓
Tasks 2, 3, 4 in parallel: NetFlow, Syslog/Traps, Ping Probes
  ↓
Tasks 5, 6, 7, 8 in parallel: Cisco, F5, PA, CP health collectors
  ↓
Tasks 9, 10 in parallel: Auto-discovery, Config Drift
  ↓
Task 11: Alert Threshold Engine (needs metrics from Tasks 1-8)
  ↓
Task 12: Observatory UI wiring (needs all endpoints from Tasks 1-11)
```

**Then:** Load enterprise network fixture data (from the fixture plan) so all collectors have devices to poll against.

**Total: 12 tasks. War Room untouched. All new monitoring infrastructure.**

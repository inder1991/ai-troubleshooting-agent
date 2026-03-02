# Enterprise Network Path Troubleshooting Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Build a topology-aware network reasoning engine that diagnoses firewall, NAT, and routing issues across enterprise networks using a self-improving Network Knowledge Graph, visual React Flow diagram editor, and multi-vendor firewall policy simulation (Palo Alto, Azure NSG, AWS SG, Oracle NSG, Zscaler).

**Architecture:** Two-layer system: (1) Topology Layer — persistent Network Knowledge Graph (NetworkX MultiDiGraph + SQLite + pytricia radix tree) storing devices, subnets, zones, routes, firewall rules, NAT rules; (2) Diagnostic Layer — LangGraph pipeline with 8 deterministic nodes (input_resolver → graph_pathfinder → traceroute_probe → hop_attributor → firewall_evaluator → nat_resolver → path_synthesizer → report_generator) producing confidence-scored diagnoses with evidence chains.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, LangGraph, NetworkX, pytricia, icmplib, pan-os-python, boto3, azure-mgmt-network, oci, React 18, TypeScript, Tailwind CSS, React Flow, SQLite

**Design Doc:** `docs/plans/2026-03-02-network-troubleshooting-design.md`

**Branch:** `feature/network-troubleshooting` (from `main`)

---

## Task 1: Backend Data Models + SQLite Schema

**Files:**
- Create: `backend/src/network/__init__.py`
- Create: `backend/src/network/models.py`
- Create: `backend/src/network/topology_store.py`
- Create: `backend/tests/test_network_models.py`

**Context:** All models use Pydantic v2 BaseModel with `model_config`. The cluster diagnostics pattern in `backend/src/agents/cluster/state.py` (lines 1-116) shows enum, frozen model, and state model patterns. SQLite is already used via `data/debugduck.db` (see `backend/src/integrations/profile_store.py` for the existing SQLite pattern).

**Changes:**

1. **`backend/src/network/__init__.py`** — Empty init file.

2. **`backend/src/network/models.py`** — All Pydantic models for the network subsystem:

```python
"""Network troubleshooting data models."""
from __future__ import annotations
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


# ── Enums ──

class DeviceType(str, Enum):
    ROUTER = "router"
    SWITCH = "switch"
    FIREWALL = "firewall"
    PROXY = "proxy"
    GATEWAY = "gateway"
    HOST = "host"

class FirewallVendor(str, Enum):
    PALO_ALTO = "palo_alto"
    AZURE_NSG = "azure_nsg"
    AWS_SG = "aws_sg"
    ORACLE_NSG = "oracle_nsg"
    ZSCALER = "zscaler"

class EdgeSource(str, Enum):
    MANUAL = "manual"
    IPAM = "ipam"
    TRACEROUTE = "traceroute"
    API = "api"
    INFERRED = "inferred"

class PolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    DROP = "drop"

class NATDirection(str, Enum):
    SNAT = "snat"
    DNAT = "dnat"

class AdapterHealthStatus(str, Enum):
    CONNECTED = "connected"
    AUTH_FAILED = "auth_failed"
    STALE = "stale"
    UNREACHABLE = "unreachable"
    NOT_CONFIGURED = "not_configured"

class DiagnosisStatus(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    NO_PATH_KNOWN = "no_path_known"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"

class TraceMethod(str, Enum):
    TCP = "tcp"
    ICMP = "icmp"
    UNAVAILABLE = "unavailable"
    MANUAL = "manual"
    INFERRED = "inferred"

class HopStatus(str, Enum):
    RESPONDED = "responded"
    TIMEOUT = "timeout"
    INFERRED = "inferred"

class VerdictMatchType(str, Enum):
    EXACT = "exact"           # confidence 0.95
    IMPLICIT_DENY = "implicit_deny"  # 0.75
    SHADOWED = "shadowed"     # 0.60
    ADAPTER_INFERENCE = "adapter_inference"  # 0.50
    ADAPTER_UNAVAILABLE = "adapter_unavailable"  # 0.0
    INSUFFICIENT_DATA = "insufficient_data"  # 0.0


# ── Infrastructure Entities (persist in graph + SQLite) ──

class Device(BaseModel):
    id: str
    name: str
    vendor: str = ""
    device_type: DeviceType = DeviceType.HOST
    management_ip: str = ""
    model: str = ""
    location: str = ""

class Interface(BaseModel):
    id: str
    device_id: str
    name: str = ""
    ip: str = ""
    mac: str = ""
    zone_id: str = ""
    vrf: str = ""
    speed: str = ""
    status: str = "up"

class Subnet(BaseModel):
    id: str
    cidr: str
    vlan_id: int = 0
    zone_id: str = ""
    gateway_ip: str = ""
    description: str = ""
    site: str = ""

class Zone(BaseModel):
    id: str
    name: str
    security_level: int = 0
    description: str = ""
    firewall_id: str = ""

class Workload(BaseModel):
    id: str
    name: str
    namespace: str = ""
    cluster: str = ""
    ips: list[str] = Field(default_factory=list)
    description: str = ""


# ── Relationship Tables (SQLite, loaded dynamically) ──

class Route(BaseModel):
    id: str
    device_id: str
    destination_cidr: str
    next_hop: str
    interface: str = ""
    metric: int = 0
    protocol: str = "static"  # static | ospf | bgp | connected
    vrf: str = ""
    learned_from: str = ""
    last_updated: str = ""

class NATRule(BaseModel):
    id: str
    device_id: str
    original_src: str = ""
    original_dst: str = ""
    translated_src: str = ""
    translated_dst: str = ""
    original_port: int = 0
    translated_port: int = 0
    direction: NATDirection = NATDirection.SNAT
    rule_id: str = ""
    description: str = ""

class FirewallRule(BaseModel):
    id: str
    device_id: str
    rule_name: str = ""
    src_zone: str = ""
    dst_zone: str = ""
    src_ips: list[str] = Field(default_factory=list)
    dst_ips: list[str] = Field(default_factory=list)
    ports: list[int] = Field(default_factory=list)
    protocol: str = "tcp"
    action: PolicyAction = PolicyAction.DENY
    logged: bool = False
    order: int = 0


# ── Investigation Artifacts (SQLite only, never in NetworkX) ──

class Flow(BaseModel):
    id: str
    src_ip: str
    dst_ip: str
    port: int
    protocol: str = "tcp"
    timestamp: str = ""
    diagnosis_status: DiagnosisStatus = DiagnosisStatus.RUNNING
    confidence: float = 0.0
    session_id: str = ""

class Trace(BaseModel):
    id: str
    flow_id: str
    src: str
    dst: str
    method: TraceMethod = TraceMethod.TCP
    timestamp: str = ""
    raw_output: str = ""
    hop_count: int = 0

class TraceHop(BaseModel):
    id: str
    trace_id: str
    hop_number: int
    ip: str
    device_id: Optional[str] = None
    rtt_ms: float = 0.0
    status: HopStatus = HopStatus.RESPONDED

class FlowVerdict(BaseModel):
    id: str
    flow_id: str
    firewall_id: str
    rule_id: str = ""
    action: PolicyAction = PolicyAction.DENY
    nat_applied: bool = False
    confidence: float = 0.0
    match_type: VerdictMatchType = VerdictMatchType.EXACT
    evidence_type: str = ""


# ── Edge Metadata ──

class EdgeMetadata(BaseModel):
    confidence: float = 0.5
    source: EdgeSource = EdgeSource.MANUAL
    last_verified_at: str = ""
    edge_type: str = "connected_to"


# ── Adapter Models ──

class AdapterHealth(BaseModel):
    vendor: FirewallVendor
    status: AdapterHealthStatus = AdapterHealthStatus.NOT_CONFIGURED
    message: str = ""
    snapshot_age_seconds: float = 0.0
    last_refresh: str = ""

class PolicyVerdict(BaseModel):
    action: PolicyAction
    rule_id: str = ""
    rule_name: str = ""
    match_type: VerdictMatchType = VerdictMatchType.EXACT
    confidence: float = 0.0
    details: str = ""

class AdapterConfig(BaseModel):
    vendor: FirewallVendor
    api_endpoint: str = ""
    api_key: str = ""
    extra_config: dict = Field(default_factory=dict)


# ── Identity Chain (NAT tracking) ──

class IdentityStage(BaseModel):
    stage: str  # "original", "post-snat-fw1", "post-dnat-fw3"
    ip: str
    port: int = 0
    device_id: Optional[str] = None


# ── Diagnostic State (for LangGraph) ──

class NetworkDiagnosticState(BaseModel):
    """LangGraph shared state for network diagnosis pipeline."""
    # Input
    flow_id: str = ""
    src_ip: str = ""
    dst_ip: str = ""
    port: int = 0
    protocol: str = "tcp"

    # Resolution
    src_device: Optional[dict] = None
    dst_device: Optional[dict] = None
    src_subnet: Optional[dict] = None
    dst_subnet: Optional[dict] = None
    resolution_status: str = "pending"  # resolved | ambiguous | failed
    ambiguous_candidates: list[dict] = Field(default_factory=list)

    # Path discovery
    candidate_paths: list[dict] = Field(default_factory=list)
    traced_path: Optional[dict] = None
    trace_method: str = "pending"
    final_path: Optional[dict] = None

    # Firewalls
    firewalls_in_path: list[dict] = Field(default_factory=list)
    firewall_verdicts: list[dict] = Field(default_factory=list)

    # NAT
    nat_translations: list[dict] = Field(default_factory=list)
    identity_chain: list[dict] = Field(default_factory=list)

    # Trace
    trace_id: Optional[str] = None
    trace_hops: list[dict] = Field(default_factory=list)
    routing_loop_detected: bool = False

    # Diagnosis
    diagnosis_status: str = "running"
    confidence: float = 0.0
    evidence: list[dict] = Field(default_factory=list)
    contradictions: list[dict] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    executive_summary: str = ""
    error: Optional[str] = None
```

3. **`backend/src/network/topology_store.py`** — SQLite persistence for all entities:

```python
"""SQLite persistence for the Network Knowledge Graph."""
import sqlite3
import json
import os
from typing import Optional
from .models import (
    Device, Interface, Subnet, Zone, Workload,
    Route, NATRule, FirewallRule,
    Flow, Trace, TraceHop, FlowVerdict,
    AdapterConfig,
)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "network.db")


class TopologyStore:
    """SQLite-backed persistence for network topology and investigation artifacts."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_tables(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY, name TEXT, vendor TEXT, device_type TEXT,
                management_ip TEXT, model TEXT, location TEXT
            );
            CREATE TABLE IF NOT EXISTS interfaces (
                id TEXT PRIMARY KEY, device_id TEXT, name TEXT, ip TEXT,
                mac TEXT, zone_id TEXT, vrf TEXT, speed TEXT, status TEXT,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            );
            CREATE TABLE IF NOT EXISTS subnets (
                id TEXT PRIMARY KEY, cidr TEXT UNIQUE, vlan_id INTEGER,
                zone_id TEXT, gateway_ip TEXT, description TEXT, site TEXT
            );
            CREATE TABLE IF NOT EXISTS zones (
                id TEXT PRIMARY KEY, name TEXT, security_level INTEGER,
                description TEXT, firewall_id TEXT
            );
            CREATE TABLE IF NOT EXISTS workloads (
                id TEXT PRIMARY KEY, name TEXT, namespace TEXT, cluster TEXT,
                ips TEXT, description TEXT
            );
            CREATE TABLE IF NOT EXISTS routes (
                id TEXT PRIMARY KEY, device_id TEXT, destination_cidr TEXT,
                next_hop TEXT, interface TEXT, metric INTEGER, protocol TEXT,
                vrf TEXT, learned_from TEXT, last_updated TEXT,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            );
            CREATE TABLE IF NOT EXISTS nat_rules (
                id TEXT PRIMARY KEY, device_id TEXT,
                original_src TEXT, original_dst TEXT,
                translated_src TEXT, translated_dst TEXT,
                original_port INTEGER, translated_port INTEGER,
                direction TEXT, rule_id TEXT, description TEXT,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            );
            CREATE TABLE IF NOT EXISTS firewall_rules (
                id TEXT PRIMARY KEY, device_id TEXT, rule_name TEXT,
                src_zone TEXT, dst_zone TEXT,
                src_ips TEXT, dst_ips TEXT, ports TEXT,
                protocol TEXT, action TEXT, logged INTEGER, "order" INTEGER,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            );
            CREATE TABLE IF NOT EXISTS flows (
                id TEXT PRIMARY KEY, src_ip TEXT, dst_ip TEXT, port INTEGER,
                protocol TEXT, timestamp TEXT, diagnosis_status TEXT,
                confidence REAL, session_id TEXT
            );
            CREATE TABLE IF NOT EXISTS traces (
                id TEXT PRIMARY KEY, flow_id TEXT, src TEXT, dst TEXT,
                method TEXT, timestamp TEXT, raw_output TEXT, hop_count INTEGER,
                FOREIGN KEY (flow_id) REFERENCES flows(id)
            );
            CREATE TABLE IF NOT EXISTS trace_hops (
                id TEXT PRIMARY KEY, trace_id TEXT, hop_number INTEGER,
                ip TEXT, device_id TEXT, rtt_ms REAL, status TEXT,
                FOREIGN KEY (trace_id) REFERENCES traces(id)
            );
            CREATE TABLE IF NOT EXISTS flow_verdicts (
                id TEXT PRIMARY KEY, flow_id TEXT, firewall_id TEXT,
                rule_id TEXT, action TEXT, nat_applied INTEGER,
                confidence REAL, match_type TEXT, evidence_type TEXT,
                FOREIGN KEY (flow_id) REFERENCES flows(id)
            );
            CREATE TABLE IF NOT EXISTS adapter_configs (
                vendor TEXT PRIMARY KEY, api_endpoint TEXT, api_key TEXT,
                extra_config TEXT
            );
            CREATE TABLE IF NOT EXISTS diagram_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_json TEXT, timestamp TEXT, description TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_routes_device ON routes(device_id);
            CREATE INDEX IF NOT EXISTS idx_routes_cidr ON routes(destination_cidr);
            CREATE INDEX IF NOT EXISTS idx_fw_rules_device ON firewall_rules(device_id);
            CREATE INDEX IF NOT EXISTS idx_nat_rules_device ON nat_rules(device_id);
            CREATE INDEX IF NOT EXISTS idx_flows_session ON flows(session_id);
            CREATE INDEX IF NOT EXISTS idx_flows_src_dst ON flows(src_ip, dst_ip, port);
            CREATE INDEX IF NOT EXISTS idx_trace_hops_trace ON trace_hops(trace_id);
            CREATE INDEX IF NOT EXISTS idx_interfaces_ip ON interfaces(ip);
            CREATE INDEX IF NOT EXISTS idx_subnets_cidr ON subnets(cidr);
        """)
        conn.commit()
        conn.close()

    # ── Device CRUD ──
    def add_device(self, device: Device) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO devices VALUES (?,?,?,?,?,?,?)",
            (device.id, device.name, device.vendor, device.device_type.value,
             device.management_ip, device.model, device.location),
        )
        conn.commit()
        conn.close()

    def get_device(self, device_id: str) -> Optional[Device]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return Device(**dict(row))

    def list_devices(self) -> list[Device]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM devices").fetchall()
        conn.close()
        return [Device(**dict(r)) for r in rows]

    def delete_device(self, device_id: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
        conn.commit()
        conn.close()

    # ── Subnet CRUD ──
    def add_subnet(self, subnet: Subnet) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO subnets VALUES (?,?,?,?,?,?,?)",
            (subnet.id, subnet.cidr, subnet.vlan_id, subnet.zone_id,
             subnet.gateway_ip, subnet.description, subnet.site),
        )
        conn.commit()
        conn.close()

    def list_subnets(self) -> list[Subnet]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM subnets").fetchall()
        conn.close()
        return [Subnet(**dict(r)) for r in rows]

    # ── Interface CRUD ──
    def add_interface(self, iface: Interface) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO interfaces VALUES (?,?,?,?,?,?,?,?,?)",
            (iface.id, iface.device_id, iface.name, iface.ip,
             iface.mac, iface.zone_id, iface.vrf, iface.speed, iface.status),
        )
        conn.commit()
        conn.close()

    def get_interfaces_by_device(self, device_id: str) -> list[Interface]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM interfaces WHERE device_id=?", (device_id,)).fetchall()
        conn.close()
        return [Interface(**dict(r)) for r in rows]

    def get_interface_by_ip(self, ip: str) -> Optional[Interface]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM interfaces WHERE ip=?", (ip,)).fetchone()
        conn.close()
        return Interface(**dict(row)) if row else None

    # ── Zone CRUD ──
    def add_zone(self, zone: Zone) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO zones VALUES (?,?,?,?,?)",
            (zone.id, zone.name, zone.security_level, zone.description, zone.firewall_id),
        )
        conn.commit()
        conn.close()

    def list_zones(self) -> list[Zone]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM zones").fetchall()
        conn.close()
        return [Zone(**dict(r)) for r in rows]

    # ── Route CRUD ──
    def add_route(self, route: Route) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO routes VALUES (?,?,?,?,?,?,?,?,?,?)",
            (route.id, route.device_id, route.destination_cidr, route.next_hop,
             route.interface, route.metric, route.protocol, route.vrf,
             route.learned_from, route.last_updated),
        )
        conn.commit()
        conn.close()

    def get_routes_by_device(self, device_id: str) -> list[Route]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM routes WHERE device_id=?", (device_id,)).fetchall()
        conn.close()
        return [Route(**dict(r)) for r in rows]

    def bulk_add_routes(self, routes: list[Route]) -> None:
        conn = self._conn()
        conn.executemany(
            "INSERT OR REPLACE INTO routes VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(r.id, r.device_id, r.destination_cidr, r.next_hop, r.interface,
              r.metric, r.protocol, r.vrf, r.learned_from, r.last_updated) for r in routes],
        )
        conn.commit()
        conn.close()

    # ── Firewall Rule CRUD ──
    def add_firewall_rule(self, rule: FirewallRule) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO firewall_rules VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rule.id, rule.device_id, rule.rule_name, rule.src_zone, rule.dst_zone,
             json.dumps(rule.src_ips), json.dumps(rule.dst_ips), json.dumps(rule.ports),
             rule.protocol, rule.action.value, int(rule.logged), rule.order),
        )
        conn.commit()
        conn.close()

    def get_firewall_rules_by_device(self, device_id: str) -> list[FirewallRule]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM firewall_rules WHERE device_id=? ORDER BY \"order\"", (device_id,)
        ).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["src_ips"] = json.loads(d["src_ips"]) if d["src_ips"] else []
            d["dst_ips"] = json.loads(d["dst_ips"]) if d["dst_ips"] else []
            d["ports"] = json.loads(d["ports"]) if d["ports"] else []
            d["logged"] = bool(d["logged"])
            results.append(FirewallRule(**d))
        return results

    # ── NAT Rule CRUD ──
    def add_nat_rule(self, rule: NATRule) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO nat_rules VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (rule.id, rule.device_id, rule.original_src, rule.original_dst,
             rule.translated_src, rule.translated_dst, rule.original_port,
             rule.translated_port, rule.direction.value, rule.rule_id, rule.description),
        )
        conn.commit()
        conn.close()

    def get_nat_rules_by_device(self, device_id: str) -> list[NATRule]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM nat_rules WHERE device_id=?", (device_id,)).fetchall()
        conn.close()
        return [NATRule(**dict(r)) for r in rows]

    # ── Flow CRUD ──
    def add_flow(self, flow: Flow) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO flows VALUES (?,?,?,?,?,?,?,?,?)",
            (flow.id, flow.src_ip, flow.dst_ip, flow.port, flow.protocol,
             flow.timestamp, flow.diagnosis_status.value, flow.confidence, flow.session_id),
        )
        conn.commit()
        conn.close()

    def update_flow(self, flow_id: str, status: str, confidence: float) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE flows SET diagnosis_status=?, confidence=? WHERE id=?",
            (status, confidence, flow_id),
        )
        conn.commit()
        conn.close()

    def list_flows(self, limit: int = 50) -> list[Flow]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM flows ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [Flow(**dict(r)) for r in rows]

    def find_recent_flow(self, src_ip: str, dst_ip: str, port: int, max_age_seconds: int = 60) -> Optional[Flow]:
        """Idempotent lookup: find a recent flow with same params."""
        conn = self._conn()
        row = conn.execute(
            """SELECT * FROM flows WHERE src_ip=? AND dst_ip=? AND port=?
               AND diagnosis_status='running'
               ORDER BY timestamp DESC LIMIT 1""",
            (src_ip, dst_ip, port),
        ).fetchone()
        conn.close()
        return Flow(**dict(row)) if row else None

    # ── Trace CRUD ──
    def add_trace(self, trace: Trace) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO traces VALUES (?,?,?,?,?,?,?,?)",
            (trace.id, trace.flow_id, trace.src, trace.dst,
             trace.method.value, trace.timestamp, trace.raw_output, trace.hop_count),
        )
        conn.commit()
        conn.close()

    def add_trace_hop(self, hop: TraceHop) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO trace_hops VALUES (?,?,?,?,?,?,?)",
            (hop.id, hop.trace_id, hop.hop_number, hop.ip,
             hop.device_id, hop.rtt_ms, hop.status.value),
        )
        conn.commit()
        conn.close()

    # ── Flow Verdict CRUD ──
    def add_flow_verdict(self, verdict: FlowVerdict) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO flow_verdicts VALUES (?,?,?,?,?,?,?,?,?)",
            (verdict.id, verdict.flow_id, verdict.firewall_id, verdict.rule_id,
             verdict.action.value, int(verdict.nat_applied), verdict.confidence,
             verdict.match_type.value, verdict.evidence_type),
        )
        conn.commit()
        conn.close()

    # ── Adapter Config CRUD ──
    def save_adapter_config(self, config: AdapterConfig) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO adapter_configs VALUES (?,?,?,?)",
            (config.vendor.value, config.api_endpoint, config.api_key,
             json.dumps(config.extra_config)),
        )
        conn.commit()
        conn.close()

    def get_adapter_config(self, vendor: str) -> Optional[AdapterConfig]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM adapter_configs WHERE vendor=?", (vendor,)).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        d["extra_config"] = json.loads(d["extra_config"]) if d["extra_config"] else {}
        return AdapterConfig(**d)

    def list_adapter_configs(self) -> list[AdapterConfig]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM adapter_configs").fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["extra_config"] = json.loads(d["extra_config"]) if d["extra_config"] else {}
            results.append(AdapterConfig(**d))
        return results

    # ── Diagram Snapshots ──
    def save_diagram(self, diagram_json: str, description: str = "") -> int:
        from datetime import datetime, timezone
        conn = self._conn()
        cursor = conn.execute(
            "INSERT INTO diagram_snapshots (snapshot_json, timestamp, description) VALUES (?,?,?)",
            (diagram_json, datetime.now(timezone.utc).isoformat(), description),
        )
        snapshot_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return snapshot_id

    def load_latest_diagram(self) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM diagram_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row["id"], "snapshot": json.loads(row["snapshot_json"]),
                "timestamp": row["timestamp"], "description": row["description"]}

    def list_diagram_versions(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, timestamp, description FROM diagram_snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Workload CRUD ──
    def add_workload(self, workload: Workload) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO workloads VALUES (?,?,?,?,?,?)",
            (workload.id, workload.name, workload.namespace, workload.cluster,
             json.dumps(workload.ips), workload.description),
        )
        conn.commit()
        conn.close()

    def list_workloads(self) -> list[Workload]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM workloads").fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["ips"] = json.loads(d["ips"]) if d["ips"] else []
            results.append(Workload(**d))
        return results
```

4. **`backend/tests/test_network_models.py`** — Tests:
- All model construction with defaults
- Enum serialization
- TopologyStore CRUD: add/get/list/delete for devices, subnets, interfaces, routes, firewall_rules, nat_rules, flows, traces, flow_verdicts, adapter_configs, diagram_snapshots
- Idempotent flow lookup (`find_recent_flow`)
- Bulk route insertion
- JSON serialization of list fields (src_ips, dst_ips, ports)
- Index creation (verify via `PRAGMA index_list`)

---

## Task 2: Network Knowledge Graph Core (NetworkX + pytricia)

**Files:**
- Create: `backend/src/network/knowledge_graph.py`
- Create: `backend/src/network/ip_resolver.py`
- Create: `backend/tests/test_knowledge_graph.py`
- Create: `backend/tests/test_ip_resolver.py`

**Context:** NetworkX MultiDiGraph is the in-memory graph. pytricia is a radix tree for O(log n) CIDR resolution. Routes stored in SQLite, loaded dynamically as edges during path computation. Investigation artifacts (flows, traces) never enter the graph.

**Changes:**

1. **`backend/src/network/ip_resolver.py`** — pytricia wrapper:

```python
"""Radix tree wrapper for fast IP → subnet/device resolution."""
import pytricia
from typing import Optional


class IPResolver:
    """O(log n) longest-prefix-match IP resolution using pytricia radix tree."""

    def __init__(self):
        self._tree = pytricia.PyTricia()

    def load_subnets(self, subnets: list[dict]) -> None:
        """Load subnet metadata into the radix tree.
        Each dict: {cidr, gateway_ip, zone_id, vlan_id, description, site}
        """
        self._tree = pytricia.PyTricia()
        for s in subnets:
            self._tree[s["cidr"]] = s

    def resolve(self, ip: str) -> Optional[dict]:
        """Resolve IP to its longest-prefix-match subnet metadata."""
        try:
            return self._tree[ip]
        except KeyError:
            return None

    def get_prefix(self, ip: str) -> Optional[str]:
        """Get the matching CIDR prefix for an IP."""
        try:
            return self._tree.get_key(ip)
        except KeyError:
            return None

    @property
    def count(self) -> int:
        return len(self._tree)
```

2. **`backend/src/network/knowledge_graph.py`** — NetworkX graph manager:

```python
"""Network Knowledge Graph — NetworkX MultiDiGraph with confidence-weighted edges."""
import networkx as nx
from typing import Optional
from datetime import datetime, timezone
from .models import Device, Subnet, Zone, Interface, EdgeMetadata, EdgeSource, Route
from .topology_store import TopologyStore
from .ip_resolver import IPResolver


# Topology penalties for dual cost model
_TOPOLOGY_PENALTIES = {
    "vrf_boundary": 0.3,
    "inter_site": 0.2,
    "overlay_tunnel": 0.15,
    "low_bandwidth": 0.1,
}


class NetworkKnowledgeGraph:
    """In-memory NetworkX graph backed by SQLite persistence.

    Only topology entities live in the graph.
    Investigation artifacts (flows, traces) stay in SQLite.
    """

    def __init__(self, store: TopologyStore):
        self.store = store
        self.graph = nx.MultiDiGraph()
        self.ip_resolver = IPResolver()
        self._device_index: dict[str, str] = {}  # ip → device_id

    def load_from_store(self) -> None:
        """Load all topology entities from SQLite into the graph."""
        self.graph.clear()

        # Load devices
        for d in self.store.list_devices():
            self.graph.add_node(d.id, **d.model_dump(), node_type="device")
            if d.management_ip:
                self._device_index[d.management_ip] = d.id

        # Load subnets
        for s in self.store.list_subnets():
            self.graph.add_node(s.id, **s.model_dump(), node_type="subnet")

        # Load zones
        for z in self.store.list_zones():
            self.graph.add_node(z.id, **z.model_dump(), node_type="zone")

        # Load interfaces and create edges (device → subnet via interface)
        for d in self.store.list_devices():
            for iface in self.store.get_interfaces_by_device(d.id):
                self._device_index[iface.ip] = d.id
                # Find which subnet this interface IP belongs to
                subnet_meta = self.ip_resolver.resolve(iface.ip)
                if subnet_meta:
                    self.graph.add_edge(
                        d.id, subnet_meta.get("id", iface.ip),
                        edge_type="connected_to",
                        interface=iface.name,
                        ip=iface.ip,
                        confidence=0.9,
                        source=EdgeSource.API.value,
                        last_verified_at=datetime.now(timezone.utc).isoformat(),
                    )

        # Rebuild pytricia
        subnets = self.store.list_subnets()
        self.ip_resolver.load_subnets([s.model_dump() for s in subnets])

    def add_device(self, device: Device) -> None:
        self.store.add_device(device)
        self.graph.add_node(device.id, **device.model_dump(), node_type="device")
        if device.management_ip:
            self._device_index[device.management_ip] = device.id

    def add_subnet(self, subnet: Subnet) -> None:
        self.store.add_subnet(subnet)
        self.graph.add_node(subnet.id, **subnet.model_dump(), node_type="subnet")
        # Rebuild resolver
        subnets = self.store.list_subnets()
        self.ip_resolver.load_subnets([s.model_dump() for s in subnets])

    def add_edge(self, src_id: str, dst_id: str, metadata: EdgeMetadata, **attrs) -> None:
        self.graph.add_edge(
            src_id, dst_id,
            confidence=metadata.confidence,
            source=metadata.source.value,
            last_verified_at=metadata.last_verified_at,
            edge_type=metadata.edge_type,
            **attrs,
        )

    def resolve_ip(self, ip: str) -> dict:
        """Resolve an IP to subnet + device metadata."""
        subnet = self.ip_resolver.resolve(ip)
        device_id = self._device_index.get(ip)
        device = None
        if device_id:
            device = self.store.get_device(device_id)
        return {
            "ip": ip,
            "subnet": subnet,
            "device": device.model_dump() if device else None,
            "device_id": device_id,
        }

    def find_device_by_ip(self, ip: str) -> Optional[str]:
        """Find device_id for a given IP (interface or management IP)."""
        # Direct index lookup
        device_id = self._device_index.get(ip)
        if device_id:
            return device_id
        # Try interface table
        iface = self.store.get_interface_by_ip(ip)
        if iface:
            return iface.device_id
        return None

    def find_candidate_devices(self, ip: str) -> list[dict]:
        """When IP is in a known subnet but can't be uniquely attributed,
        return all devices with interfaces in that subnet."""
        subnet_meta = self.ip_resolver.resolve(ip)
        if not subnet_meta:
            return []
        subnet_cidr = subnet_meta.get("cidr", "")
        # Find all devices with interfaces in this subnet
        candidates = []
        for d in self.store.list_devices():
            for iface in self.store.get_interfaces_by_device(d.id):
                iface_subnet = self.ip_resolver.resolve(iface.ip)
                if iface_subnet and iface_subnet.get("cidr") == subnet_cidr:
                    candidates.append({
                        "device_id": d.id,
                        "device_name": d.name,
                        "interface_ip": iface.ip,
                        "interface_name": iface.name,
                    })
        return candidates

    def build_route_edges(self, src_ip: str, dst_ip: str) -> None:
        """Dynamically build routes_to edges relevant to a specific path query.
        Only loads routes that could be part of a path between src and dst.
        """
        # Get all devices in the graph
        for node_id, data in self.graph.nodes(data=True):
            if data.get("node_type") != "device":
                continue
            routes = self.store.get_routes_by_device(node_id)
            for route in routes:
                # Find what device has the next_hop IP
                next_device = self.find_device_by_ip(route.next_hop)
                if next_device and next_device != node_id:
                    self.graph.add_edge(
                        node_id, next_device,
                        edge_type="routes_to",
                        destination=route.destination_cidr,
                        next_hop=route.next_hop,
                        metric=route.metric,
                        protocol=route.protocol,
                        vrf=route.vrf,
                        confidence=0.85,
                        source=EdgeSource.API.value,
                        last_verified_at=route.last_updated or "",
                    )

    def find_k_shortest_paths(
        self, src_id: str, dst_id: str, k: int = 3
    ) -> list[list[str]]:
        """Find K shortest paths using confidence-weighted dual cost model.
        cost = (1 - confidence) + topology_penalty
        """
        if src_id not in self.graph or dst_id not in self.graph:
            return []

        # Build cost graph
        cost_graph = nx.DiGraph()
        for u, v, data in self.graph.edges(data=True):
            confidence = data.get("confidence", 0.5)
            penalty = 0.0
            if data.get("vrf") and data.get("vrf") != "":
                penalty += _TOPOLOGY_PENALTIES["vrf_boundary"]
            if data.get("edge_type") == "overlay":
                penalty += _TOPOLOGY_PENALTIES["overlay_tunnel"]
            cost = (1.0 - confidence) + penalty
            # Keep minimum cost if multiple edges between same nodes
            if cost_graph.has_edge(u, v):
                if cost < cost_graph[u][v]["weight"]:
                    cost_graph[u][v]["weight"] = cost
            else:
                cost_graph.add_edge(u, v, weight=cost)

        try:
            paths = list(nx.shortest_simple_paths(cost_graph, src_id, dst_id, weight="weight"))
            return paths[:k]
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def boost_edge_confidence(self, src_id: str, dst_id: str, boost: float = 0.05) -> None:
        """Boost confidence on a verified edge (from successful trace/API check)."""
        if self.graph.has_edge(src_id, dst_id):
            for key in self.graph[src_id][dst_id]:
                current = self.graph[src_id][dst_id][key].get("confidence", 0.5)
                new_conf = min(1.0, current + boost)
                self.graph[src_id][dst_id][key]["confidence"] = new_conf
                self.graph[src_id][dst_id][key]["last_verified_at"] = \
                    datetime.now(timezone.utc).isoformat()

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()
```

**Tests:**
- `test_ip_resolver_load_and_resolve` — load subnets, resolve IPs, longest-prefix match
- `test_ip_resolver_no_match` — unresolvable IP returns None
- `test_graph_load_from_store` — devices/subnets/zones become nodes
- `test_graph_add_device_and_subnet` — adds to both store and graph
- `test_graph_resolve_ip` — returns subnet + device metadata
- `test_graph_find_device_by_ip` — management IP, interface IP, missing IP
- `test_graph_find_candidate_devices` — multiple devices in same subnet
- `test_graph_build_route_edges` — routes become dynamic edges
- `test_graph_k_shortest_paths` — dual cost model, confidence weighting
- `test_graph_boost_edge_confidence` — confidence increment, timestamp update
- `test_graph_node_and_edge_counts`

---

## Task 3: Firewall Adapter Base + Mock Adapter

**Files:**
- Create: `backend/src/network/adapters/__init__.py`
- Create: `backend/src/network/adapters/base.py`
- Create: `backend/src/network/adapters/mock_adapter.py`
- Create: `backend/tests/test_firewall_adapters.py`

**Context:** Every adapter implements the same ABC. Diagnostics read from cached policy snapshots (never live API). TTL = 300s default. `health_check()` returns adapter status for UI display.

**Changes:**

1. **`backend/src/network/adapters/base.py`** — Abstract base:

```python
"""Base firewall adapter interface. All vendor adapters implement this."""
from abc import ABC, abstractmethod
from typing import Optional
import time
from ..models import (
    PolicyVerdict, AdapterHealth, AdapterHealthStatus, FirewallVendor,
    FirewallRule, NATRule, Zone, Route, PolicyAction, VerdictMatchType,
)


class VRF:
    def __init__(self, name: str, rd: str = "", interfaces: list[str] = None):
        self.name = name
        self.rd = rd
        self.interfaces = interfaces or []


class VirtualRouter:
    def __init__(self, name: str, interfaces: list[str] = None, static_routes: list[dict] = None):
        self.name = name
        self.interfaces = interfaces or []
        self.static_routes = static_routes or []


class DeviceInterface:
    def __init__(self, name: str, ip: str, zone: str = "", vrf: str = "", status: str = "up"):
        self.name = name
        self.ip = ip
        self.zone = zone
        self.vrf = vrf
        self.status = status


class FirewallAdapter(ABC):
    """Abstract base for all firewall vendor adapters.

    Key design principles:
    - Diagnostics NEVER hit live API. Always read from cached snapshot.
    - Snapshot refreshed on TTL expiry or manual trigger.
    - Each adapter normalizes vendor-specific data to common models.
    """

    DEFAULT_TTL = 300  # 5 minutes

    def __init__(self, vendor: FirewallVendor, api_endpoint: str = "", api_key: str = "",
                 extra_config: dict = None):
        self.vendor = vendor
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self.extra_config = extra_config or {}
        self._snapshot_time: float = 0
        self._rules_cache: list[FirewallRule] = []
        self._nat_cache: list[NATRule] = []
        self._zones_cache: list[Zone] = []
        self._routes_cache: list[Route] = []
        self._interfaces_cache: list[DeviceInterface] = []

    # ── Core troubleshooting ──

    @abstractmethod
    async def simulate_flow(
        self, src_ip: str, dst_ip: str, port: int, protocol: str = "tcp"
    ) -> PolicyVerdict:
        """Simulate a flow against cached rules. Return verdict with confidence."""

    # ── Policy snapshot (cached) ──

    @abstractmethod
    async def _fetch_rules(self) -> list[FirewallRule]:
        """Vendor-specific: fetch rules from API."""

    @abstractmethod
    async def _fetch_nat_rules(self) -> list[NATRule]:
        """Vendor-specific: fetch NAT rules from API."""

    @abstractmethod
    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        """Vendor-specific: fetch interfaces from API."""

    @abstractmethod
    async def _fetch_routes(self) -> list[Route]:
        """Vendor-specific: fetch routing table from API."""

    @abstractmethod
    async def _fetch_zones(self) -> list[Zone]:
        """Vendor-specific: fetch security zones from API."""

    async def get_rules(self, zone_src: str = "", zone_dst: str = "") -> list[FirewallRule]:
        await self._ensure_snapshot()
        if zone_src or zone_dst:
            return [r for r in self._rules_cache
                    if (not zone_src or r.src_zone == zone_src)
                    and (not zone_dst or r.dst_zone == zone_dst)]
        return self._rules_cache

    async def get_nat_rules(self) -> list[NATRule]:
        await self._ensure_snapshot()
        return self._nat_cache

    async def get_interfaces(self) -> list[DeviceInterface]:
        await self._ensure_snapshot()
        return self._interfaces_cache

    async def get_routes(self) -> list[Route]:
        await self._ensure_snapshot()
        return self._routes_cache

    async def get_zones(self) -> list[Zone]:
        await self._ensure_snapshot()
        return self._zones_cache

    async def get_vrfs(self) -> list[VRF]:
        """Override in adapters that support VRFs."""
        return []

    async def get_virtual_routers(self) -> list[VirtualRouter]:
        """Override in adapters that support virtual routers (e.g., PAN-OS)."""
        return []

    # ── Operational ──

    async def health_check(self) -> AdapterHealth:
        """Check adapter connectivity and snapshot freshness."""
        if not self.api_endpoint:
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.NOT_CONFIGURED,
                message="No API endpoint configured",
            )
        try:
            await self._fetch_zones()  # Lightweight connectivity test
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.CONNECTED,
                snapshot_age_seconds=self.snapshot_age_seconds(),
                last_refresh=self._format_snapshot_time(),
            )
        except Exception as e:
            if "auth" in str(e).lower() or "401" in str(e) or "403" in str(e):
                return AdapterHealth(
                    vendor=self.vendor,
                    status=AdapterHealthStatus.AUTH_FAILED,
                    message=str(e),
                )
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.UNREACHABLE,
                message=str(e),
            )

    async def refresh_snapshot(self) -> None:
        """Force a full snapshot refresh."""
        self._rules_cache = await self._fetch_rules()
        self._nat_cache = await self._fetch_nat_rules()
        self._interfaces_cache = await self._fetch_interfaces()
        self._routes_cache = await self._fetch_routes()
        self._zones_cache = await self._fetch_zones()
        self._snapshot_time = time.time()

    def snapshot_age_seconds(self) -> float:
        if self._snapshot_time == 0:
            return float("inf")
        return time.time() - self._snapshot_time

    # ── Internal ──

    async def _ensure_snapshot(self) -> None:
        if self.snapshot_age_seconds() > self.DEFAULT_TTL:
            await self.refresh_snapshot()

    def _format_snapshot_time(self) -> str:
        if self._snapshot_time == 0:
            return ""
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self._snapshot_time, tz=timezone.utc).isoformat()

    def _match_ip(self, ip: str, patterns: list[str]) -> bool:
        """Check if ip matches any pattern (exact or CIDR)."""
        import ipaddress
        if not patterns or "any" in patterns:
            return True
        try:
            addr = ipaddress.ip_address(ip)
            for p in patterns:
                if "/" in p:
                    if addr in ipaddress.ip_network(p, strict=False):
                        return True
                elif p == ip:
                    return True
        except ValueError:
            pass
        return False

    def _match_port(self, port: int, ports: list[int]) -> bool:
        """Check if port matches rule port list (empty = any)."""
        if not ports:
            return True
        return port in ports
```

2. **`backend/src/network/adapters/mock_adapter.py`** — Mock adapter for testing and demo:

```python
"""Mock firewall adapter for testing and demo purposes."""
from .base import FirewallAdapter, DeviceInterface, VRF, VirtualRouter
from ..models import (
    PolicyVerdict, FirewallVendor, FirewallRule, NATRule, Zone, Route,
    PolicyAction, VerdictMatchType,
)


class MockFirewallAdapter(FirewallAdapter):
    """Returns configurable mock responses. Used in tests and demos."""

    def __init__(self, vendor: FirewallVendor = FirewallVendor.PALO_ALTO,
                 rules: list[FirewallRule] = None,
                 nat_rules: list[NATRule] = None,
                 zones: list[Zone] = None,
                 default_action: PolicyAction = PolicyAction.DENY):
        super().__init__(vendor=vendor)
        self._mock_rules = rules or []
        self._mock_nat_rules = nat_rules or []
        self._mock_zones = zones or []
        self._default_action = default_action

    async def simulate_flow(self, src_ip: str, dst_ip: str, port: int,
                           protocol: str = "tcp") -> PolicyVerdict:
        await self._ensure_snapshot()
        # Evaluate rules in priority order
        for rule in sorted(self._rules_cache, key=lambda r: r.order):
            src_match = self._match_ip(src_ip, rule.src_ips)
            dst_match = self._match_ip(dst_ip, rule.dst_ips)
            port_match = self._match_port(port, rule.ports)
            if src_match and dst_match and port_match:
                confidence = {
                    VerdictMatchType.EXACT: 0.95,
                    VerdictMatchType.IMPLICIT_DENY: 0.75,
                }.get(VerdictMatchType.EXACT, 0.95)
                return PolicyVerdict(
                    action=rule.action,
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    match_type=VerdictMatchType.EXACT,
                    confidence=confidence,
                    details=f"Matched rule {rule.rule_name} (order {rule.order})",
                )
        # No explicit match → implicit deny
        return PolicyVerdict(
            action=self._default_action,
            rule_name="implicit-deny",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.75,
            details="No matching rule found, implicit deny",
        )

    async def _fetch_rules(self) -> list[FirewallRule]:
        return list(self._mock_rules)

    async def _fetch_nat_rules(self) -> list[NATRule]:
        return list(self._mock_nat_rules)

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        return []

    async def _fetch_routes(self) -> list[Route]:
        return []

    async def _fetch_zones(self) -> list[Zone]:
        return list(self._mock_zones)
```

**Tests:**
- `test_mock_adapter_simulate_allow` — rule matches, returns ALLOW with exact match confidence
- `test_mock_adapter_simulate_deny` — no rule matches, returns implicit deny
- `test_mock_adapter_rule_priority` — first matching rule (by order) wins
- `test_mock_adapter_ip_cidr_matching` — CIDR patterns match correctly
- `test_mock_adapter_port_matching` — empty ports = any, specific ports match
- `test_adapter_health_check_not_configured` — no endpoint returns NOT_CONFIGURED
- `test_adapter_snapshot_ttl` — snapshot refreshes after TTL
- `test_adapter_snapshot_age` — age calculation

---

## Task 4: Palo Alto Panorama Adapter

**Files:**
- Create: `backend/src/network/adapters/panorama_adapter.py`
- Create: `backend/tests/test_panorama_adapter.py`

**Context:** Uses `pan-os-python` library. Connects to Panorama or device directly. Fetches security rules, NAT rules, zones, virtual routers, interfaces. `simulate_flow()` evaluates rules in priority order against cached snapshot.

**Changes:**

Implement `PanoramaAdapter(FirewallAdapter)` with:
- `__init__` accepting hostname, api_key, device_group (for Panorama-managed devices)
- `_fetch_rules()` → `panos.policies.SecurityRule` objects → normalized to `FirewallRule`
- `_fetch_nat_rules()` → `panos.policies.NatRule` objects → normalized to `NATRule`
- `_fetch_zones()` → `panos.network.Zone` objects → normalized to `Zone`
- `_fetch_interfaces()` → `panos.network.EthernetInterface` → `DeviceInterface`
- `_fetch_routes()` → `panos.network.StaticRoute` → `Route`
- `get_vrfs()` → VSYS-based VRF info
- `get_virtual_routers()` → `panos.network.VirtualRouter`
- `simulate_flow()` — zone-aware rule matching: resolve src/dst IPs to zones via interfaces, then match against rules filtered by src_zone/dst_zone

**Tests:** Mock `panos.Panorama` and `panos.Firewall` objects. Test rule normalization, zone resolution, NAT rule parsing, flow simulation with zone matching.

---

## Task 5: Cloud NSG Adapters (Azure + AWS + Oracle)

**Files:**
- Create: `backend/src/network/adapters/azure_nsg_adapter.py`
- Create: `backend/src/network/adapters/aws_sg_adapter.py`
- Create: `backend/src/network/adapters/oracle_nsg_adapter.py`
- Create: `backend/tests/test_cloud_adapters.py`

**Context:** Each cloud adapter uses its respective SDK. Azure: `azure-mgmt-network`. AWS: `boto3`. Oracle: `oci`. All normalize to the common `FirewallRule`/`NATRule`/`PolicyVerdict` models.

**Changes:**

1. **`AzureNSGAdapter`** — Azure SDK (`NetworkManagementClient`):
   - `_fetch_rules()` → NSG rules by resource group / NSG name, normalized to `FirewallRule` (priority → order, access → action)
   - `_fetch_routes()` → route tables attached to subnets
   - `simulate_flow()` → evaluate NSG rules in priority order (lower number = higher priority), inbound/outbound separation

2. **`AWSSGAdapter`** — boto3 (`ec2.describe_security_groups`):
   - `_fetch_rules()` → security group ingress/egress rules → `FirewallRule`
   - Also fetch NACLs if subnet specified
   - `simulate_flow()` → SG rules are stateful (allow = allow return), NACLs are stateless

3. **`OracleNSGAdapter`** — OCI SDK (`VirtualNetworkClient`):
   - `_fetch_rules()` → `list_network_security_group_security_rules()` → `FirewallRule`
   - `_fetch_routes()` → route table rules
   - `simulate_flow()` — similar to Azure pattern, priority-ordered

**Tests:** Mock SDK clients for each provider. Test rule normalization, priority ordering, flow simulation, auth failure handling.

---

## Task 6: Zscaler Adapter

**Files:**
- Create: `backend/src/network/adapters/zscaler_adapter.py`
- Create: `backend/tests/test_zscaler_adapter.py`

**Context:** Zscaler ZIA (Internet Access) and ZPA (Private Access) use REST APIs with OAuth. Zscaler is a proxy model — traffic is tunneled through Zscaler cloud, not through traditional firewall hops.

**Changes:**

Implement `ZscalerAdapter(FirewallAdapter)`:
- Auth: OAuth flow (client_id, client_secret, vanity_url)
- `_fetch_rules()` → ZIA firewall policies + URL filtering rules → `FirewallRule`
- `simulate_flow()` → check if traffic matches any ZIA policy, check DLP rules
- `get_zones()` → ZPA trusted networks
- Health check: verify ZIA API reachability

**Tests:** Mock ZIA/ZPA REST responses. Test OAuth token handling, rule normalization, proxy detection.

---

## Task 7: IPAM Ingestion Service

**Files:**
- Create: `backend/src/network/ipam_ingestion.py`
- Create: `backend/tests/test_ipam_ingestion.py`

**Context:** Three input methods: CSV/Excel upload, diagram editor (handled separately), IPAM API (Infoblox). CSV is the primary input for most enterprises.

**Changes:**

1. **`ipam_ingestion.py`**:

```python
"""IPAM data ingestion — CSV/Excel upload and parsing."""
import csv
import io
import uuid
from typing import Optional
from .models import Device, Subnet, Interface, DeviceType
from .topology_store import TopologyStore


def parse_ipam_csv(content: str, store: TopologyStore) -> dict:
    """Parse CSV with columns: ip, subnet, device, zone, vlan, description.
    Creates/updates devices, subnets, and interfaces in the store.
    Returns summary: {devices_added, subnets_added, interfaces_added, errors}.
    """
    reader = csv.DictReader(io.StringIO(content))
    stats = {"devices_added": 0, "subnets_added": 0, "interfaces_added": 0, "errors": []}
    seen_devices = set()
    seen_subnets = set()

    for row_num, row in enumerate(reader, start=2):
        try:
            ip = row.get("ip", "").strip()
            subnet_cidr = row.get("subnet", "").strip()
            device_name = row.get("device", "").strip()
            zone = row.get("zone", "").strip()
            vlan = row.get("vlan", "0").strip()
            description = row.get("description", "").strip()

            if not ip and not subnet_cidr:
                continue

            # Create/update subnet
            if subnet_cidr and subnet_cidr not in seen_subnets:
                subnet_id = f"subnet-{subnet_cidr.replace('/', '-')}"
                store.add_subnet(Subnet(
                    id=subnet_id, cidr=subnet_cidr, vlan_id=int(vlan or 0),
                    zone_id=zone, description=description,
                ))
                seen_subnets.add(subnet_cidr)
                stats["subnets_added"] += 1

            # Create/update device
            if device_name and device_name not in seen_devices:
                device_id = f"device-{device_name.lower().replace(' ', '-')}"
                store.add_device(Device(
                    id=device_id, name=device_name,
                    device_type=DeviceType.HOST,
                ))
                seen_devices.add(device_name)
                stats["devices_added"] += 1

            # Create interface linking IP to device
            if ip and device_name:
                device_id = f"device-{device_name.lower().replace(' ', '-')}"
                iface_id = f"iface-{ip.replace('.', '-')}"
                store.add_interface(Interface(
                    id=iface_id, device_id=device_id, ip=ip,
                    zone_id=zone,
                ))
                stats["interfaces_added"] += 1

        except Exception as e:
            stats["errors"].append(f"Row {row_num}: {str(e)}")

    return stats


def parse_ipam_excel(file_bytes: bytes, store: TopologyStore) -> dict:
    """Parse Excel file with same column structure as CSV."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"devices_added": 0, "subnets_added": 0, "interfaces_added": 0, "errors": []}

    headers = [str(h).strip().lower() if h else "" for h in rows[0]]
    csv_lines = []
    csv_lines.append(",".join(headers))
    for row in rows[1:]:
        csv_lines.append(",".join(str(c or "") for c in row))

    return parse_ipam_csv("\n".join(csv_lines), store)
```

**Tests:**
- `test_parse_csv_basic` — 3 rows, creates devices/subnets/interfaces, returns correct stats
- `test_parse_csv_duplicate_devices` — same device name not duplicated
- `test_parse_csv_missing_fields` — rows with only subnet or only IP handled gracefully
- `test_parse_csv_invalid_row` — bad data captured in errors list
- `test_parse_csv_empty` — empty file returns zero stats
- `test_parse_excel` — xlsx file parsed correctly (mock openpyxl)

---

## Task 8: Diagnostic Pipeline — Input Resolution + Path Finding

**Files:**
- Create: `backend/src/agents/network/__init__.py`
- Create: `backend/src/agents/network/state.py`
- Create: `backend/src/agents/network/input_resolver.py`
- Create: `backend/src/agents/network/graph_pathfinder.py`
- Create: `backend/tests/test_network_input_resolver.py`
- Create: `backend/tests/test_network_pathfinder.py`

**Context:** These are deterministic LangGraph nodes (no LLM). Follow the cluster diagnostics pattern: each node is an `async def` taking `state: dict` and returning a partial state dict. The `State` TypedDict uses `Annotated[list, operator.add]` for fan-in fields.

**Changes:**

1. **`state.py`** — LangGraph TypedDict state (mirrors `cluster/graph.py` pattern):

```python
"""LangGraph state definition for the network diagnostic pipeline."""
from typing import TypedDict, Optional, Annotated
import operator


class State(TypedDict):
    # Input
    flow_id: str
    src_ip: str
    dst_ip: str
    port: int
    protocol: str

    # Resolution
    src_device: Optional[dict]
    dst_device: Optional[dict]
    src_subnet: Optional[dict]
    dst_subnet: Optional[dict]
    resolution_status: str
    ambiguous_candidates: list[dict]

    # Path discovery
    candidate_paths: list[dict]
    traced_path: Optional[dict]
    trace_method: str
    final_path: Optional[dict]

    # Firewalls
    firewalls_in_path: list[dict]
    firewall_verdicts: Annotated[list[dict], operator.add]  # fan-in from parallel adapters

    # NAT
    nat_translations: list[dict]
    identity_chain: list[dict]

    # Trace
    trace_id: Optional[str]
    trace_hops: list[dict]
    routing_loop_detected: bool

    # Diagnosis
    diagnosis_status: str
    confidence: float
    evidence: Annotated[list[dict], operator.add]
    contradictions: list[dict]
    next_steps: list[str]
    executive_summary: str
    error: Optional[str]

    # Internal refs
    _knowledge_graph: Optional[object]  # NetworkKnowledgeGraph reference
    _topology_store: Optional[object]   # TopologyStore reference
```

2. **`input_resolver.py`**:

```python
"""Resolve source/destination IPs to subnet, zone, and device metadata."""


def input_resolver(state: dict) -> dict:
    """Deterministic node. Resolves IPs via pytricia + device index.
    Returns AMBIGUOUS if IP matches multiple VRFs/subnets.
    """
    kg = state.get("_knowledge_graph")
    if not kg:
        return {"resolution_status": "failed", "error": "Knowledge graph not available"}

    src_ip = state["src_ip"]
    dst_ip = state["dst_ip"]

    src_info = kg.resolve_ip(src_ip)
    dst_info = kg.resolve_ip(dst_ip)

    # Check for ambiguity (multiple candidate devices in same subnet)
    ambiguous = []
    if not src_info.get("device_id"):
        candidates = kg.find_candidate_devices(src_ip)
        if len(candidates) > 1:
            ambiguous.extend([{"ip": src_ip, "candidates": candidates}])
    if not dst_info.get("device_id"):
        candidates = kg.find_candidate_devices(dst_ip)
        if len(candidates) > 1:
            ambiguous.extend([{"ip": dst_ip, "candidates": candidates}])

    if ambiguous:
        return {
            "resolution_status": "ambiguous",
            "ambiguous_candidates": ambiguous,
            "src_subnet": src_info.get("subnet"),
            "dst_subnet": dst_info.get("subnet"),
        }

    # Check if at least subnets are known
    if not src_info.get("subnet") and not dst_info.get("subnet"):
        return {
            "resolution_status": "failed",
            "error": f"Neither {src_ip} nor {dst_ip} found in any known subnet. "
                     "Upload IPAM data or draw topology to add them.",
        }

    return {
        "src_device": src_info.get("device"),
        "dst_device": dst_info.get("device"),
        "src_subnet": src_info.get("subnet"),
        "dst_subnet": dst_info.get("subnet"),
        "resolution_status": "resolved",
        "evidence": [{
            "type": "resolution",
            "src": src_info,
            "dst": dst_info,
        }],
    }
```

3. **`graph_pathfinder.py`**:

```python
"""Find candidate paths through the knowledge graph using confidence-weighted search."""


def graph_pathfinder(state: dict) -> dict:
    """Deterministic node. Builds route edges dynamically, then runs K-shortest paths."""
    kg = state.get("_knowledge_graph")
    if not kg:
        return {"candidate_paths": []}

    src_ip = state["src_ip"]
    dst_ip = state["dst_ip"]

    # Build dynamic route edges for this query
    kg.build_route_edges(src_ip, dst_ip)

    # Find source and destination node IDs
    src_device_id = kg.find_device_by_ip(src_ip)
    dst_device_id = kg.find_device_by_ip(dst_ip)

    # Fallback to subnet gateway devices if direct device not found
    if not src_device_id:
        src_subnet = state.get("src_subnet") or {}
        gw = src_subnet.get("gateway_ip", "")
        if gw:
            src_device_id = kg.find_device_by_ip(gw)
    if not dst_device_id:
        dst_subnet = state.get("dst_subnet") or {}
        gw = dst_subnet.get("gateway_ip", "")
        if gw:
            dst_device_id = kg.find_device_by_ip(gw)

    if not src_device_id or not dst_device_id:
        return {"candidate_paths": []}

    # K-shortest paths with dual cost model
    paths = kg.find_k_shortest_paths(src_device_id, dst_device_id, k=3)

    candidate_paths = []
    for i, path in enumerate(paths):
        # Annotate each hop with device metadata
        hops = []
        for node_id in path:
            node_data = kg.graph.nodes.get(node_id, {})
            hops.append({
                "device_id": node_id,
                "device_name": node_data.get("name", node_id),
                "device_type": node_data.get("device_type", "unknown"),
                "vendor": node_data.get("vendor", ""),
            })
        candidate_paths.append({
            "path_index": i,
            "hops": hops,
            "hop_count": len(hops),
        })

    # Identify firewalls in candidate paths
    firewalls = []
    seen_fw = set()
    for cp in candidate_paths:
        for hop in cp["hops"]:
            if hop["device_type"] == "firewall" and hop["device_id"] not in seen_fw:
                firewalls.append(hop)
                seen_fw.add(hop["device_id"])

    return {
        "candidate_paths": candidate_paths,
        "firewalls_in_path": firewalls,
        "evidence": [{
            "type": "graph_pathfinder",
            "paths_found": len(candidate_paths),
            "firewalls_found": len(firewalls),
        }],
    }
```

**Tests:**
- `test_input_resolver_resolved` — both IPs found, returns device + subnet
- `test_input_resolver_ambiguous` — IP in subnet with multiple devices
- `test_input_resolver_failed` — neither IP in any known subnet
- `test_input_resolver_partial` — one IP known, other unknown
- `test_pathfinder_finds_paths` — 3-node graph, finds path
- `test_pathfinder_no_path` — disconnected graph, returns empty
- `test_pathfinder_identifies_firewalls` — firewall nodes extracted from paths
- `test_pathfinder_gateway_fallback` — uses subnet gateway when device not directly found

---

## Task 9: Diagnostic Pipeline — Traceroute + Hop Attribution

**Files:**
- Create: `backend/src/agents/network/traceroute_probe.py`
- Create: `backend/src/agents/network/hop_attributor.py`
- Create: `backend/tests/test_traceroute_probe.py`
- Create: `backend/tests/test_hop_attributor.py`

**Context:** `traceroute_probe` uses icmplib for TCP/ICMP traceroute. Rate-limited to 3 concurrent probes (asyncio.Semaphore). Loop detection if same IP appears >2 times. `hop_attributor` maps hop IPs to devices using pytricia + device index, with probabilistic matching for ambiguous IPs.

**Changes:**

1. **`traceroute_probe.py`** — TCP/ICMP traceroute with rate limiting and loop detection. Uses `icmplib.async_traceroute()` or subprocess fallback. Stores trace artifact in SQLite. Returns hop list.

2. **`hop_attributor.py`** — For each hop IP: pytricia → subnet → device index → device. If IP in known subnet but not attributed, returns `candidate_devices[]` with confidence=0.6. Merges traced hops with graph candidate paths (overlapping segments unified).

**Tests:**
- `test_traceroute_tcp_success` — mock icmplib, returns hops
- `test_traceroute_blocked` — all timeouts, returns trace_method="unavailable"
- `test_traceroute_loop_detection` — same IP 3+ times → routing_loop_detected=True
- `test_hop_attributor_known_device` — hop IP maps to device
- `test_hop_attributor_unknown_device` — returns candidate_devices
- `test_hop_attributor_no_match` — unknown IP, device_id=None

---

## Task 10: Diagnostic Pipeline — Firewall Evaluation + NAT

**Files:**
- Create: `backend/src/agents/network/firewall_evaluator.py`
- Create: `backend/src/agents/network/nat_resolver.py`
- Create: `backend/tests/test_firewall_evaluator.py`
- Create: `backend/tests/test_nat_resolver.py`

**Context:** `firewall_evaluator` fans out to relevant adapters (max concurrency=5 via asyncio.Semaphore). Reads from cached snapshots only. `nat_resolver` builds the identity chain (address stack through multi-firewall NAT), then re-evaluates downstream rules with translated IPs.

**Changes:**

1. **`firewall_evaluator.py`** — For each firewall in `firewalls_in_path`: look up adapter by vendor → `simulate_flow()` → collect verdicts. Bounded `asyncio.gather` with Semaphore(5). Handles ADAPTER_UNAVAILABLE and INSUFFICIENT_DATA.

2. **`nat_resolver.py`** — For each firewall in path: query `nat_rules` table. If SNAT/DNAT matches, create identity_chain entries. Track `[{stage, ip, port, device_id}]` through the entire path. If NAT changes addresses, re-evaluate downstream firewall rules with post-NAT IPs.

**Tests:**
- `test_evaluator_allow_verdict` — adapter returns ALLOW
- `test_evaluator_deny_verdict` — adapter returns DENY
- `test_evaluator_adapter_unavailable` — no adapter → ADAPTER_UNAVAILABLE
- `test_evaluator_bounded_concurrency` — max 5 concurrent adapter calls
- `test_nat_resolver_snat` — source NAT applied, identity chain has 2 stages
- `test_nat_resolver_dnat` — destination NAT, downstream re-evaluation
- `test_nat_resolver_chain` — SNAT → transit → DNAT chain (3 stages)
- `test_nat_resolver_no_nat` — no NAT rules, pass-through

---

## Task 11: Diagnostic Pipeline — Synthesis + Report

**Files:**
- Create: `backend/src/agents/network/path_synthesizer.py`
- Create: `backend/src/agents/network/report_generator.py`
- Create: `backend/tests/test_path_synthesizer.py`

**Context:** `path_synthesizer` is the brain — merges all sources, detects contradictions, computes weighted confidence. `report_generator` is the only LLM node — generates human-readable narrative from structured JSON.

**Changes:**

1. **`path_synthesizer.py`** — Merges traced_path + candidate_paths + firewall verdicts. Marks each segment with `method` (traced|graph|inferred|policy). Weighted confidence: `traced=3.0, api=2.0, graph=1.0, inferred=0.5`. Contradiction detection: if graph says path A but traceroute shows path B → `INCONSISTENT_EVIDENCE`, reduce confidence 30%.

2. **`report_generator.py`** — LLM-assisted (Claude). Takes structured JSON → produces executive summary, path narrative, firewall citations, NAT explanations, confidence breakdown, next steps. System prompt: "Only use provided evidence. Never invent paths."

**Tests:**
- `test_synthesizer_traced_only` — traced path → high confidence
- `test_synthesizer_graph_only` — graph path → medium confidence
- `test_synthesizer_merged` — traced + graph → merged with correct segment attribution
- `test_synthesizer_contradiction` — conflicting paths → INCONSISTENT_EVIDENCE, confidence reduced
- `test_synthesizer_weighted_confidence` — correct formula application
- `test_synthesizer_no_path` — no data → NO_PATH_KNOWN

---

## Task 12: LangGraph Wiring + Backend API Endpoints

**Files:**
- Create: `backend/src/agents/network/graph.py`
- Create: `backend/src/api/network_endpoints.py`
- Create: `backend/src/api/network_models.py`
- Modify: `backend/src/api/main.py`
- Modify: `backend/src/api/models.py`
- Modify: `backend/src/api/routes_v4.py`
- Create: `backend/tests/test_network_endpoints.py`

**Context:** Follow `cluster/graph.py` pattern for LangGraph wiring. Follow `agent_endpoints.py` pattern for API router. Add `elif capability == "network_troubleshooting":` branch in `routes_v4.py:start_session()` (around line 304) and in the findings endpoint.

**Changes:**

1. **`graph.py`** — `build_network_diagnostic_graph()`:
   - Wire: `START → input_resolver → [conditional] → graph_pathfinder → traceroute_probe → hop_attributor → firewall_evaluator → nat_resolver → path_synthesizer → report_generator → END`
   - Conditional routing: ambiguous → END, no path + no trace → END early

2. **`network_endpoints.py`** — `network_router = APIRouter(prefix="/api/v4/network")`:
   - `POST /diagnose` — start diagnosis (idempotent within 60s)
   - `GET /session/{id}/findings` — get results
   - `POST /topology/save` — save diagram JSON
   - `GET /topology/load` — load diagram
   - `POST /ipam/upload` — upload CSV/Excel
   - `GET /ipam/subnets` — list subnets
   - `GET /ipam/devices` — list devices
   - `POST /adapters/{vendor}/configure` — configure adapter
   - `GET /adapters/status` — all adapter health
   - `POST /adapters/{vendor}/refresh` — force refresh
   - `GET /flows` — list past flows
   - `GET /flows/{flow_id}` — flow details

3. **`network_models.py`** — Request/response Pydantic models for all endpoints.

4. **`main.py`** — Add `from .network_endpoints import network_router` + `app.include_router(network_router)`.

5. **`models.py`** — Add optional fields to `StartSessionRequest`: `target_host`, `port_num`, `net_protocol`.

6. **`routes_v4.py`** — Add `elif capability == "network_troubleshooting":` branch with session creation + background task. Add capability check in findings endpoint.

**Tests:**
- `test_diagnose_endpoint` — POST creates session, returns session_id
- `test_diagnose_idempotent` — same params within 60s returns existing session
- `test_topology_save_load` — save diagram JSON, load returns it
- `test_ipam_upload_csv` — CSV upload processes correctly
- `test_adapters_status` — returns health for all vendors
- `test_flows_list` — returns past investigations
- `test_start_session_network` — integration: routes_v4 creates network session

---

## Task 13: Frontend Types + Form + Capability Wiring

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/components/ActionCenter/forms/NetworkTroubleshootingFields.tsx`
- Modify: `frontend/src/components/ActionCenter/CapabilityForm.tsx`
- Modify: `frontend/src/components/ActionCenter/ActionCenter.tsx`
- Modify: `frontend/src/components/Home/CapabilityLauncher.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout/SidebarNav.tsx`
- Modify: `frontend/src/services/api.ts`

**Context:** Follow exact patterns from existing capabilities. `CapabilityType` union at types/index.ts:546. `CapabilityFormData` union at types/index.ts:758. `capabilityMeta` at CapabilityForm.tsx:21. `capabilities` array at CapabilityLauncher.tsx:8. `ViewState` at App.tsx:37. `handleFormSubmit` at App.tsx:220. `showSidebar` at App.tsx:353.

**Changes:**

1. **`types/index.ts`** — Add `'network_troubleshooting'` to `CapabilityType`. Add:
```typescript
export interface NetworkTroubleshootingForm {
  capability: 'network_troubleshooting';
  src_ip: string;
  dst_ip: string;
  port: string;
  protocol: 'tcp' | 'udp';
}
```
Add to `CapabilityFormData` union. Add response types for network diagnosis.

2. **`NetworkTroubleshootingFields.tsx`** — Form with: source IP input, destination IP input, port input, protocol toggle (TCP/UDP). Same input styling as ClusterDiagnosticsFields.

3. **`CapabilityForm.tsx`** — Add to `capabilityMeta` (icon: `route`, color: `#f59e0b`), `getInitialData`, `isValid` (both IPs non-empty, port > 0), field component dispatch.

4. **`ActionCenter.tsx`** — Add to capabilities array: `{ type: 'network_troubleshooting', title: 'Network Path', icon: Route, color: '#f59e0b' }`.

5. **`CapabilityLauncher.tsx`** — Add card: icon `route`, iconColor `#f59e0b`, ctaText `Trace Path`.

6. **`App.tsx`** — Add `'network-troubleshooting'` to ViewState. Add form submit handler. Add `showSidebar` exclusion. Add render block for NetworkWarRoom.

7. **`SidebarNav.tsx`** — Add `'topology'` to NavView with icon `device_hub`.

8. **`api.ts`** — Add `diagnoseNetwork()`, `getNetworkFindings()`, `saveTopology()`, `loadTopology()`, `uploadIPAM()`, `getAdapterStatus()` functions.

**Verification:** `npx tsc --noEmit` passes.

---

## Task 14: Frontend Topology Editor (React Flow)

**Files:**
- Create: `frontend/src/components/TopologyEditor/TopologyEditorView.tsx`
- Create: `frontend/src/components/TopologyEditor/NodePalette.tsx`
- Create: `frontend/src/components/TopologyEditor/DeviceNode.tsx`
- Create: `frontend/src/components/TopologyEditor/SubnetGroupNode.tsx`
- Create: `frontend/src/components/TopologyEditor/DevicePropertyPanel.tsx`
- Create: `frontend/src/components/TopologyEditor/TopologyToolbar.tsx`
- Create: `frontend/src/components/TopologyEditor/IPAMUploadDialog.tsx`
- Create: `frontend/src/components/TopologyEditor/AdapterConfigDialog.tsx`

**Context:** Install `reactflow` package. Custom node types for router, switch, firewall, subnet, zone, workload, cloud gateway. Node palette with drag-and-drop. Edge types: solid (L3 link), dashed (overlay). Save/load via `/api/v4/network/topology/save` and `/load`. Properties panel for editing node attributes.

**Changes:**

1. **Install:** `npm install reactflow`

2. **`TopologyEditorView.tsx`** — Main page container. ReactFlowProvider + React Flow canvas. Loads diagram on mount via `loadTopology()`. Saves on Ctrl+S or toolbar button. Sidebar with NodePalette. Right panel with DevicePropertyPanel (when node selected).

3. **`NodePalette.tsx`** — Draggable node items: Router, Switch, Firewall, Subnet, Zone, Workload, Cloud Gateway. Uses `onDragStart` with `event.dataTransfer.setData('application/reactflow', type)`.

4. **`DeviceNode.tsx`** — Custom React Flow node. Hexagon shape for firewalls, rounded rect for routers/switches. Material Symbol icon. Status indicator dot. Name label.

5. **`SubnetGroupNode.tsx`** — Group node with dashed border. CIDR label. Contains child device nodes.

6. **`DevicePropertyPanel.tsx`** — Side panel showing editable properties for selected node. Name, IP, vendor, type, zone. For firewall nodes: adapter config button.

7. **`TopologyToolbar.tsx`** — Save, Load, Import IPAM, Version History buttons.

8. **`IPAMUploadDialog.tsx`** — Modal with file drop zone. Accepts .csv, .xlsx. Shows parse results.

9. **`AdapterConfigDialog.tsx`** — Modal for configuring firewall adapter credentials. Vendor dropdown, API endpoint, API key. Test connection button.

**Verification:** `npx tsc --noEmit` passes. Topology editor renders and saves/loads correctly.

---

## Task 15: Frontend Network War Room

**Files:**
- Create: `frontend/src/components/NetworkTroubleshooting/NetworkWarRoom.tsx`
- Create: `frontend/src/components/NetworkTroubleshooting/DiagnosisPanel.tsx`
- Create: `frontend/src/components/NetworkTroubleshooting/NetworkCanvas.tsx`
- Create: `frontend/src/components/NetworkTroubleshooting/NetworkEvidenceStack.tsx`
- Create: `frontend/src/components/NetworkTroubleshooting/PathHopList.tsx`
- Create: `frontend/src/components/NetworkTroubleshooting/FirewallVerdictCard.tsx`
- Create: `frontend/src/components/NetworkTroubleshooting/NATChainDisplay.tsx`
- Create: `frontend/src/components/NetworkTroubleshooting/AdapterHealthBadge.tsx`

**Context:** Follow ClusterWarRoom pattern: `grid grid-cols-12`, 3 columns (col-span-3, col-span-5, col-span-4), polling `fetchFindings` every 5s. Uses React Flow for center canvas with path highlighting and animated flow edges.

**Changes:**

1. **`NetworkWarRoom.tsx`** — Main container. Props: `session, events, wsConnected, onGoHome`. Fetches findings via `getNetworkFindings(session.session_id)` every 5s. 12-column grid layout. Loading state with spinner.

2. **`DiagnosisPanel.tsx`** — Left column (col-3): executive summary, PathHopList, NATChainDisplay, next steps list, past flows.

3. **`NetworkCanvas.tsx`** — Center column (col-5): React Flow canvas showing topology with investigated path highlighted. Firewall nodes colored red (deny) or green (allow). Animated dashed edge for traced segments.

4. **`NetworkEvidenceStack.tsx`** — Right column (col-4): traceroute raw output, FirewallVerdictCard for each firewall, NAT translations, confidence breakdown, contradiction alerts, AdapterHealthBadge for each adapter.

5. **`PathHopList.tsx`** — Ordered list of hops with: hop number, IP, device name, status dot (responded/timeout/inferred), RTT.

6. **`FirewallVerdictCard.tsx`** — Card showing: firewall name, vendor badge, verdict (ALLOW green / DENY red / UNKNOWN amber), rule citation, match type, confidence.

7. **`NATChainDisplay.tsx`** — Visual identity chain: original IP → post-SNAT → post-DNAT with device labels.

8. **`AdapterHealthBadge.tsx`** — Small badge: vendor icon + status dot (green/red/amber/gray).

**Verification:** `npx tsc --noEmit` passes. War Room renders with all panels.

---

## Task 16: Integration Tests + Verification

**Files:**
- Create: `backend/tests/test_network_integration.py`
- Modify: existing test files as needed

**Changes:**

1. **Integration tests:**
   - `test_full_diagnosis_flow` — end-to-end: create topology, add firewall rules, run diagnosis, verify verdict
   - `test_diagnosis_no_topology` — empty graph → NO_PATH_KNOWN
   - `test_diagnosis_nat_chain` — topology with NAT → identity chain correct
   - `test_diagnosis_contradiction` — conflicting trace vs graph → INCONSISTENT_EVIDENCE
   - `test_ipam_upload_then_diagnose` — upload CSV, then run diagnosis against uploaded topology
   - `test_diagram_save_load_roundtrip` — save React Flow JSON, load back, verify
   - `test_adapter_health_all_vendors` — health check returns correct status per vendor
   - `test_idempotent_diagnosis` — same params within 60s returns existing session

2. **Verification:**
   - `cd backend && python3 -m pytest --tb=short -q` — all tests pass
   - `cd frontend && npx tsc --noEmit` — no TypeScript errors
   - Start backend + frontend, verify:
     - Home page shows "Network Path" capability card
     - Click card → form with src/dst/port fields
     - Sidebar shows "Topology" nav item → editor page loads
     - IPAM upload works
     - Diagnosis flow creates session and streams results to War Room

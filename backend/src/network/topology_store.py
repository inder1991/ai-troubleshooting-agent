"""SQLite persistence for the Network Knowledge Graph."""
import sqlite3
import json
import os
from datetime import datetime, timedelta, timezone
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

    def list_interfaces(self, device_id: Optional[str] = None) -> list[Interface]:
        conn = self._conn()
        if device_id:
            rows = conn.execute("SELECT * FROM interfaces WHERE device_id=?", (device_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM interfaces").fetchall()
        conn.close()
        return [Interface(**dict(r)) for r in rows]

    def find_interface_by_ip(self, ip: str) -> Optional[Interface]:
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

    def bulk_add_routes(self, routes: list[Route]) -> None:
        conn = self._conn()
        conn.executemany(
            "INSERT OR REPLACE INTO routes VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(r.id, r.device_id, r.destination_cidr, r.next_hop, r.interface,
              r.metric, r.protocol, r.vrf, r.learned_from, r.last_updated) for r in routes],
        )
        conn.commit()
        conn.close()

    def list_routes(self, device_id: Optional[str] = None) -> list[Route]:
        conn = self._conn()
        if device_id:
            rows = conn.execute("SELECT * FROM routes WHERE device_id=?", (device_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM routes").fetchall()
        conn.close()
        return [Route(**dict(r)) for r in rows]

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

    def list_nat_rules(self, device_id: Optional[str] = None) -> list[NATRule]:
        conn = self._conn()
        if device_id:
            rows = conn.execute("SELECT * FROM nat_rules WHERE device_id=?", (device_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM nat_rules").fetchall()
        conn.close()
        return [NATRule(**dict(r)) for r in rows]

    # ── Firewall Rule CRUD ──
    def add_firewall_rule(self, rule: FirewallRule) -> None:
        conn = self._conn()
        conn.execute(
            'INSERT OR REPLACE INTO firewall_rules VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (rule.id, rule.device_id, rule.rule_name, rule.src_zone, rule.dst_zone,
             json.dumps(rule.src_ips), json.dumps(rule.dst_ips), json.dumps(rule.ports),
             rule.protocol, rule.action.value, int(rule.logged), rule.order),
        )
        conn.commit()
        conn.close()

    def list_firewall_rules(self, device_id: Optional[str] = None) -> list[FirewallRule]:
        conn = self._conn()
        if device_id:
            rows = conn.execute("SELECT * FROM firewall_rules WHERE device_id=?", (device_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM firewall_rules").fetchall()
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

    # ── Workload CRUD ──
    def add_workload(self, wl: Workload) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO workloads VALUES (?,?,?,?,?,?)",
            (wl.id, wl.name, wl.namespace, wl.cluster, json.dumps(wl.ips), wl.description),
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

    def get_flow(self, flow_id: str) -> Optional[Flow]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM flows WHERE id=?", (flow_id,)).fetchone()
        conn.close()
        return Flow(**dict(row)) if row else None

    def find_recent_flow(self, src_ip: str, dst_ip: str, port: int, within_seconds: int = 60) -> Optional[Flow]:
        """Idempotent flow lookup for dedup within time window."""
        conn = self._conn()
        # Normalize cutoff to +00:00 format (matches datetime.now(timezone.utc).isoformat())
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
        # Use REPLACE to normalize Z suffix to +00:00 for consistent comparison
        row = conn.execute(
            "SELECT * FROM flows WHERE src_ip=? AND dst_ip=? AND port=? "
            "AND REPLACE(timestamp, 'Z', '+00:00') >= ? ORDER BY timestamp DESC LIMIT 1",
            (src_ip, dst_ip, port, cutoff),
        ).fetchone()
        conn.close()
        return Flow(**dict(row)) if row else None

    def update_flow_status(self, flow_id: str, status: str, confidence: float = 0.0) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE flows SET diagnosis_status=?, confidence=? WHERE id=?",
            (status, confidence, flow_id),
        )
        conn.commit()
        conn.close()

    # ── Trace CRUD ──
    def add_trace(self, trace: Trace) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO traces VALUES (?,?,?,?,?,?,?,?)",
            (trace.id, trace.flow_id, trace.src, trace.dst, trace.method.value,
             trace.timestamp, trace.raw_output, trace.hop_count),
        )
        conn.commit()
        conn.close()

    def add_trace_hop(self, hop: TraceHop) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO trace_hops VALUES (?,?,?,?,?,?,?)",
            (hop.id, hop.trace_id, hop.hop_number, hop.ip, hop.device_id,
             hop.rtt_ms, hop.status.value),
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

    # ── Diagram Snapshots ──
    def save_diagram_snapshot(self, snapshot_json: str, description: str = "") -> int:
        conn = self._conn()
        cursor = conn.execute(
            "INSERT INTO diagram_snapshots (snapshot_json, timestamp, description) VALUES (?,?,?)",
            (snapshot_json, datetime.now(timezone.utc).isoformat(), description),
        )
        conn.commit()
        snap_id = cursor.lastrowid
        conn.close()
        return snap_id

    def load_diagram_snapshot(self) -> Optional[dict]:
        """Load the most recent diagram snapshot."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM diagram_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        return {
            "id": d["id"],
            "snapshot_json": d["snapshot_json"],
            "timestamp": d["timestamp"],
            "description": d["description"],
        }

    def list_flows(self, limit: int = 50) -> list[Flow]:
        """List recent flows, ordered by timestamp descending."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM flows ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [Flow(**dict(r)) for r in rows]

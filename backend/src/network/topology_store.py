"""SQLite persistence for the Network Knowledge Graph."""
import sqlite3
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from .models import (
    Device, DeviceType, Interface, Subnet, Zone, Workload,
    Route, NATRule, FirewallRule,
    Flow, Trace, TraceHop, FlowVerdict,
    AdapterConfig, AdapterInstance, FirewallVendor,
    VPC, RouteTable, VPCPeering, TransitGateway,
    VPNTunnel, DirectConnect,
    NACL, NACLRule,
    LoadBalancer, LBTargetGroup,
    VLAN, MPLSCircuit, ComplianceZone,
    HAGroup, HAMode,
)
from src.integrations.credential_resolver import get_credential_resolver

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "network.db")


class TopologyStore:
    """SQLite-backed persistence for network topology and investigation artifacts."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_tables()
        self._migrate_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_tables(self):
        conn = self._conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY, name TEXT, vendor TEXT, device_type TEXT,
                    management_ip TEXT, model TEXT, location TEXT,
                    zone_id TEXT DEFAULT '', vlan_id INTEGER DEFAULT 0, description TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS interfaces (
                    id TEXT PRIMARY KEY, device_id TEXT, name TEXT, ip TEXT,
                    mac TEXT, zone_id TEXT, vrf TEXT, speed TEXT, status TEXT,
                    role TEXT DEFAULT '', subnet_id TEXT DEFAULT '',
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS subnets (
                    id TEXT PRIMARY KEY, cidr TEXT UNIQUE, vlan_id INTEGER,
                    zone_id TEXT, gateway_ip TEXT, description TEXT, site TEXT
                );
                CREATE TABLE IF NOT EXISTS zones (
                    id TEXT PRIMARY KEY, name TEXT, security_level INTEGER,
                    description TEXT, firewall_id TEXT, zone_type TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS workloads (
                    id TEXT PRIMARY KEY, name TEXT, namespace TEXT, cluster TEXT,
                    ips TEXT, description TEXT
                );
                CREATE TABLE IF NOT EXISTS routes (
                    id TEXT PRIMARY KEY, device_id TEXT, destination_cidr TEXT,
                    next_hop TEXT, interface TEXT, metric INTEGER, protocol TEXT,
                    vrf TEXT, learned_from TEXT, last_updated TEXT,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS nat_rules (
                    id TEXT PRIMARY KEY, device_id TEXT,
                    original_src TEXT, original_dst TEXT,
                    translated_src TEXT, translated_dst TEXT,
                    original_port INTEGER, translated_port INTEGER,
                    direction TEXT, rule_id TEXT, description TEXT,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS firewall_rules (
                    id TEXT PRIMARY KEY, device_id TEXT, rule_name TEXT,
                    src_zone TEXT, dst_zone TEXT,
                    src_ips TEXT, dst_ips TEXT, ports TEXT,
                    protocol TEXT, action TEXT, logged INTEGER, "order" INTEGER,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS flows (
                    id TEXT PRIMARY KEY, src_ip TEXT, dst_ip TEXT, port INTEGER,
                    protocol TEXT, timestamp TEXT, diagnosis_status TEXT,
                    confidence REAL, session_id TEXT
                );
                CREATE TABLE IF NOT EXISTS traces (
                    id TEXT PRIMARY KEY, flow_id TEXT, src TEXT, dst TEXT,
                    method TEXT, timestamp TEXT, raw_output TEXT, hop_count INTEGER,
                    FOREIGN KEY (flow_id) REFERENCES flows(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS trace_hops (
                    id TEXT PRIMARY KEY, trace_id TEXT, hop_number INTEGER,
                    ip TEXT, device_id TEXT, rtt_ms REAL, status TEXT,
                    FOREIGN KEY (trace_id) REFERENCES traces(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS flow_verdicts (
                    id TEXT PRIMARY KEY, flow_id TEXT, firewall_id TEXT,
                    rule_id TEXT, action TEXT, nat_applied INTEGER,
                    confidence REAL, match_type TEXT, evidence_type TEXT,
                    FOREIGN KEY (flow_id) REFERENCES flows(id) ON DELETE CASCADE
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

                CREATE TABLE IF NOT EXISTS vpcs (
                    id TEXT PRIMARY KEY, name TEXT, cloud_provider TEXT,
                    region TEXT, cidr_blocks TEXT, account_id TEXT, compliance_zone TEXT
                );
                CREATE TABLE IF NOT EXISTS route_tables (
                    id TEXT PRIMARY KEY, vpc_id TEXT, name TEXT, is_main INTEGER,
                    FOREIGN KEY (vpc_id) REFERENCES vpcs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS vpc_peerings (
                    id TEXT PRIMARY KEY, requester_vpc_id TEXT, accepter_vpc_id TEXT,
                    status TEXT, cidr_routes TEXT
                );
                CREATE TABLE IF NOT EXISTS transit_gateways (
                    id TEXT PRIMARY KEY, name TEXT, cloud_provider TEXT,
                    region TEXT, attached_vpc_ids TEXT, route_table_id TEXT
                );
                CREATE TABLE IF NOT EXISTS vpn_tunnels (
                    id TEXT PRIMARY KEY, name TEXT, tunnel_type TEXT,
                    local_gateway_id TEXT, remote_gateway_ip TEXT,
                    local_cidrs TEXT, remote_cidrs TEXT,
                    encryption TEXT, ike_version TEXT, status TEXT
                );
                CREATE TABLE IF NOT EXISTS direct_connects (
                    id TEXT PRIMARY KEY, name TEXT, provider TEXT,
                    bandwidth_mbps INTEGER, location TEXT, vlan_id INTEGER,
                    bgp_asn INTEGER, status TEXT
                );
                CREATE TABLE IF NOT EXISTS nacls (
                    id TEXT PRIMARY KEY, name TEXT, vpc_id TEXT,
                    subnet_ids TEXT, is_default INTEGER
                );
                CREATE TABLE IF NOT EXISTS nacl_rules (
                    id TEXT PRIMARY KEY, nacl_id TEXT, direction TEXT,
                    rule_number INTEGER, protocol TEXT, cidr TEXT,
                    port_range_from INTEGER, port_range_to INTEGER, action TEXT,
                    FOREIGN KEY (nacl_id) REFERENCES nacls(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS load_balancers (
                    id TEXT PRIMARY KEY, name TEXT, lb_type TEXT,
                    scheme TEXT, vpc_id TEXT, listeners TEXT, health_check_path TEXT
                );
                CREATE TABLE IF NOT EXISTS lb_target_groups (
                    id TEXT PRIMARY KEY, lb_id TEXT, name TEXT,
                    protocol TEXT, port INTEGER, target_ids TEXT, health_status TEXT,
                    FOREIGN KEY (lb_id) REFERENCES load_balancers(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS vlans (
                    id TEXT PRIMARY KEY, vlan_number INTEGER, name TEXT,
                    trunk_ports TEXT, access_ports TEXT, site TEXT
                );
                CREATE TABLE IF NOT EXISTS mpls_circuits (
                    id TEXT PRIMARY KEY, name TEXT, label INTEGER,
                    provider TEXT, bandwidth_mbps INTEGER, endpoints TEXT, qos_class TEXT
                );
                CREATE TABLE IF NOT EXISTS compliance_zones (
                    id TEXT PRIMARY KEY, name TEXT, standard TEXT,
                    description TEXT, subnet_ids TEXT, vpc_ids TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_nacl_rules_nacl ON nacl_rules(nacl_id);
                CREATE INDEX IF NOT EXISTS idx_lb_targets_lb ON lb_target_groups(lb_id);
                CREATE INDEX IF NOT EXISTS idx_route_tables_vpc ON route_tables(vpc_id);

                CREATE TABLE IF NOT EXISTS ha_groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    ha_mode TEXT NOT NULL,
                    member_ids TEXT NOT NULL,
                    virtual_ips TEXT DEFAULT '[]',
                    active_member_id TEXT DEFAULT '',
                    priority_map TEXT DEFAULT '{}',
                    sync_interface TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS edge_confidence (
                    src_id TEXT, dst_id TEXT, confidence REAL,
                    source TEXT, last_verified_at TEXT,
                    PRIMARY KEY (src_id, dst_id)
                );

                CREATE TABLE IF NOT EXISTS adapter_instances (
                    instance_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    vendor TEXT NOT NULL,
                    api_endpoint TEXT DEFAULT '',
                    api_key TEXT DEFAULT '',
                    extra_config TEXT DEFAULT '{}',
                    device_groups TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT '',
                    updated_at TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_adapter_instances_vendor ON adapter_instances(vendor);

                CREATE TABLE IF NOT EXISTS adapter_device_bindings (
                    device_id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS device_status (
                    device_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    latency_ms REAL DEFAULT 0,
                    packet_loss REAL DEFAULT 0,
                    last_seen TEXT,
                    last_status_change TEXT,
                    probe_method TEXT DEFAULT 'icmp',
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS link_metrics (
                    src_device_id TEXT,
                    dst_device_id TEXT,
                    latency_ms REAL DEFAULT 0,
                    bandwidth_bps INTEGER DEFAULT 0,
                    error_rate REAL DEFAULT 0,
                    utilization REAL DEFAULT 0,
                    updated_at TEXT,
                    PRIMARY KEY (src_device_id, dst_device_id)
                );
                CREATE TABLE IF NOT EXISTS metric_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_metric_history_entity
                    ON metric_history(entity_type, entity_id, recorded_at);
                CREATE TABLE IF NOT EXISTS drift_events (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    drift_type TEXT NOT NULL,
                    field TEXT DEFAULT '',
                    expected TEXT DEFAULT '',
                    actual TEXT DEFAULT '',
                    severity TEXT DEFAULT 'warning',
                    detected_at TEXT,
                    resolved_at TEXT,
                    UNIQUE(entity_type, entity_id, drift_type, field)
                );
                CREATE TABLE IF NOT EXISTS discovery_candidates (
                    ip TEXT PRIMARY KEY,
                    mac TEXT DEFAULT '',
                    hostname TEXT DEFAULT '',
                    discovered_via TEXT DEFAULT '',
                    source_device_id TEXT DEFAULT '',
                    first_seen TEXT,
                    last_seen TEXT,
                    promoted_device_id TEXT DEFAULT '',
                    dismissed INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS alert_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_key TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL,
                    threshold REAL NOT NULL,
                    condition TEXT NOT NULL,
                    state TEXT NOT NULL,
                    message TEXT DEFAULT '',
                    timestamp TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_alert_history_key ON alert_history(alert_key);
                CREATE INDEX IF NOT EXISTS idx_alert_history_severity ON alert_history(severity);
            """)
            conn.commit()
        finally:
            conn.close()

    def _migrate_tables(self):
        """Add columns that may be missing from older schemas."""
        conn = self._conn()
        try:
            migrations = [
                "ALTER TABLE devices ADD COLUMN zone_id TEXT DEFAULT ''",
                "ALTER TABLE devices ADD COLUMN vlan_id INTEGER DEFAULT 0",
                "ALTER TABLE devices ADD COLUMN description TEXT DEFAULT ''",
                "ALTER TABLE devices ADD COLUMN ha_group_id TEXT DEFAULT ''",
                "ALTER TABLE devices ADD COLUMN ha_role TEXT DEFAULT ''",
                "ALTER TABLE interfaces ADD COLUMN role TEXT DEFAULT ''",
                "ALTER TABLE interfaces ADD COLUMN subnet_id TEXT DEFAULT ''",
                "ALTER TABLE zones ADD COLUMN zone_type TEXT DEFAULT ''",
            ]
            for sql in migrations:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # Column already exists
            conn.commit()
        finally:
            conn.close()

        # Migrate old adapter_configs rows into adapter_instances
        self._migrate_adapter_configs()

    def _migrate_adapter_configs(self):
        """Migrate rows from legacy adapter_configs table into adapter_instances."""
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM adapter_configs").fetchall()
            if not rows:
                return
            from uuid import uuid4
            for r in rows:
                d = dict(r)
                vendor = d.get("vendor", "")
                api_endpoint = d.get("api_endpoint", "")
                # Check if already migrated (same vendor + endpoint exists)
                existing = conn.execute(
                    "SELECT 1 FROM adapter_instances WHERE vendor=? AND api_endpoint=?",
                    (vendor, api_endpoint),
                ).fetchone()
                if existing:
                    continue
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO adapter_instances (instance_id, label, vendor, api_endpoint, api_key, extra_config, device_groups, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (str(uuid4()), vendor, vendor, api_endpoint,
                     d.get("api_key", ""), d.get("extra_config", "{}"), "[]", now, now),
                )
            conn.commit()
        except sqlite3.OperationalError:
            pass  # adapter_configs table may not exist yet
        finally:
            conn.close()

    @staticmethod
    def _safe_json_loads(raw, fallback=None):
        """Safely parse JSON, returning fallback on failure."""
        if fallback is None:
            fallback = []
        if not raw:
            return fallback
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return fallback

    # ── Device CRUD ──
    def add_device(self, device: Device) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO devices (id, name, vendor, device_type, management_ip, model, location, zone_id, vlan_id, description, ha_group_id, ha_role) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (device.id, device.name, device.vendor, device.device_type.value,
                 device.management_ip, device.model, device.location,
                 device.zone_id, device.vlan_id, device.description,
                 device.ha_group_id, device.ha_role),
            )
            conn.commit()
        finally:
            conn.close()

    def get_device(self, device_id: str) -> Optional[Device]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            return Device(
                id=d["id"], name=d["name"], vendor=d.get("vendor") or "",
                device_type=DeviceType(d["device_type"]) if d.get("device_type") else DeviceType.HOST,
                management_ip=d.get("management_ip") or "", model=d.get("model") or "",
                location=d.get("location") or "",
                zone_id=d.get("zone_id") or "",
                vlan_id=d.get("vlan_id") or 0,
                description=d.get("description") or "",
                ha_group_id=d.get("ha_group_id") or "",
                ha_role=d.get("ha_role") or "",
            )
        finally:
            conn.close()

    def list_devices(self) -> list[Device]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM devices").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                results.append(Device(
                    id=d["id"], name=d["name"], vendor=d.get("vendor") or "",
                    device_type=DeviceType(d["device_type"]) if d.get("device_type") else DeviceType.HOST,
                    management_ip=d.get("management_ip") or "", model=d.get("model") or "",
                    location=d.get("location") or "",
                    zone_id=d.get("zone_id") or "",
                    vlan_id=d.get("vlan_id") or 0,
                    description=d.get("description") or "",
                    ha_group_id=d.get("ha_group_id") or "",
                    ha_role=d.get("ha_role") or "",
                ))
            return results
        finally:
            conn.close()

    def delete_device(self, device_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM interfaces WHERE device_id=?", (device_id,))
            conn.execute("DELETE FROM routes WHERE device_id=?", (device_id,))
            conn.execute("DELETE FROM nat_rules WHERE device_id=?", (device_id,))
            conn.execute("DELETE FROM firewall_rules WHERE device_id=?", (device_id,))
            conn.execute("DELETE FROM adapter_device_bindings WHERE device_id=?", (device_id,))
            conn.execute("DELETE FROM device_status WHERE device_id=?", (device_id,))
            conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
            conn.commit()
        finally:
            conn.close()

    def update_device(self, device_id: str, **kwargs) -> Optional[Device]:
        """Update specific fields on a device. Returns updated device or None."""
        conn = self._conn()
        try:
            existing = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
            if not existing:
                return None
            d = dict(existing)
            allowed = {"name", "vendor", "device_type", "management_ip", "model",
                       "location", "zone_id", "vlan_id", "description", "ha_group_id", "ha_role"}
            updates = {k: v for k, v in kwargs.items() if k in allowed}
            if not updates:
                return self.get_device(device_id)
            set_clause = ", ".join(f"{k}=?" for k in updates)
            values = list(updates.values()) + [device_id]
            conn.execute(f"UPDATE devices SET {set_clause} WHERE id=?", values)
            conn.commit()
        finally:
            conn.close()
        return self.get_device(device_id)

    # ── Subnet CRUD ──
    def add_subnet(self, subnet: Subnet) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO subnets VALUES (?,?,?,?,?,?,?)",
                (subnet.id, subnet.cidr, subnet.vlan_id, subnet.zone_id,
                 subnet.gateway_ip, subnet.description, subnet.site),
            )
            conn.commit()
        finally:
            conn.close()

    def list_subnets(self) -> list[Subnet]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM subnets").fetchall()
            return [Subnet(**dict(r)) for r in rows]
        finally:
            conn.close()

    def delete_subnet(self, subnet_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM subnets WHERE id=?", (subnet_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Interface CRUD ──
    def add_interface(self, iface: Interface) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO interfaces VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (iface.id, iface.device_id, iface.name, iface.ip,
                 iface.mac, iface.zone_id, iface.vrf, iface.speed, iface.status,
                 iface.role, iface.subnet_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_interfaces(self, device_id: Optional[str] = None) -> list[Interface]:
        conn = self._conn()
        try:
            if device_id:
                rows = conn.execute("SELECT * FROM interfaces WHERE device_id=?", (device_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM interfaces").fetchall()
            return [Interface(**dict(r)) for r in rows]
        finally:
            conn.close()

    def find_interface_by_ip(self, ip: str) -> Optional[Interface]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM interfaces WHERE ip=?", (ip,)).fetchone()
            return Interface(**dict(row)) if row else None
        finally:
            conn.close()

    def delete_interface(self, interface_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM interfaces WHERE id=?", (interface_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Zone CRUD ──
    def add_zone(self, zone: Zone) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO zones VALUES (?,?,?,?,?,?)",
                (zone.id, zone.name, zone.security_level, zone.description,
                 zone.firewall_id, zone.zone_type),
            )
            conn.commit()
        finally:
            conn.close()

    def list_zones(self) -> list[Zone]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM zones").fetchall()
            return [Zone(**dict(r)) for r in rows]
        finally:
            conn.close()

    def delete_zone(self, zone_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM zones WHERE id=?", (zone_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Route CRUD ──
    def add_route(self, route: Route) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO routes VALUES (?,?,?,?,?,?,?,?,?,?)",
                (route.id, route.device_id, route.destination_cidr, route.next_hop,
                 route.interface, route.metric, route.protocol, route.vrf,
                 route.learned_from, route.last_updated),
            )
            conn.commit()
        finally:
            conn.close()

    def bulk_add_routes(self, routes: list[Route]) -> None:
        conn = self._conn()
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO routes VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(r.id, r.device_id, r.destination_cidr, r.next_hop, r.interface,
                  r.metric, r.protocol, r.vrf, r.learned_from, r.last_updated) for r in routes],
            )
            conn.commit()
        finally:
            conn.close()

    def list_routes(self, device_id: Optional[str] = None) -> list[Route]:
        conn = self._conn()
        try:
            if device_id:
                rows = conn.execute("SELECT * FROM routes WHERE device_id=?", (device_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM routes").fetchall()
            return [Route(**dict(r)) for r in rows]
        finally:
            conn.close()

    def delete_route(self, route_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM routes WHERE id=?", (route_id,))
            conn.commit()
        finally:
            conn.close()

    # ── NAT Rule CRUD ──
    def add_nat_rule(self, rule: NATRule) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO nat_rules VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (rule.id, rule.device_id, rule.original_src, rule.original_dst,
                 rule.translated_src, rule.translated_dst, rule.original_port,
                 rule.translated_port, rule.direction.value, rule.rule_id, rule.description),
            )
            conn.commit()
        finally:
            conn.close()

    def list_nat_rules(self, device_id: Optional[str] = None) -> list[NATRule]:
        conn = self._conn()
        try:
            if device_id:
                rows = conn.execute("SELECT * FROM nat_rules WHERE device_id=?", (device_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM nat_rules").fetchall()
            return [NATRule(**dict(r)) for r in rows]
        finally:
            conn.close()

    # ── Firewall Rule CRUD ──
    def add_firewall_rule(self, rule: FirewallRule) -> None:
        conn = self._conn()
        try:
            conn.execute(
                'INSERT OR REPLACE INTO firewall_rules VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (rule.id, rule.device_id, rule.rule_name, rule.src_zone, rule.dst_zone,
                 json.dumps(rule.src_ips), json.dumps(rule.dst_ips), json.dumps(rule.ports),
                 rule.protocol, rule.action.value, int(rule.logged), rule.order),
            )
            conn.commit()
        finally:
            conn.close()

    def list_firewall_rules(self, device_id: Optional[str] = None) -> list[FirewallRule]:
        conn = self._conn()
        try:
            if device_id:
                rows = conn.execute("SELECT * FROM firewall_rules WHERE device_id=?", (device_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM firewall_rules").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["src_ips"] = self._safe_json_loads(d.get("src_ips"))
                d["dst_ips"] = self._safe_json_loads(d.get("dst_ips"))
                d["ports"] = self._safe_json_loads(d.get("ports"))
                d["logged"] = bool(d["logged"])
                results.append(FirewallRule(**d))
            return results
        finally:
            conn.close()

    # ── Workload CRUD ──
    def add_workload(self, wl: Workload) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO workloads VALUES (?,?,?,?,?,?)",
                (wl.id, wl.name, wl.namespace, wl.cluster, json.dumps(wl.ips), wl.description),
            )
            conn.commit()
        finally:
            conn.close()

    def list_workloads(self) -> list[Workload]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM workloads").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["ips"] = self._safe_json_loads(d.get("ips"))
                results.append(Workload(**d))
            return results
        finally:
            conn.close()

    # ── Flow CRUD ──
    def add_flow(self, flow: Flow) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO flows VALUES (?,?,?,?,?,?,?,?,?)",
                (flow.id, flow.src_ip, flow.dst_ip, flow.port, flow.protocol,
                 flow.timestamp, flow.diagnosis_status.value, flow.confidence, flow.session_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_flow(self, flow_id: str) -> Optional[Flow]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM flows WHERE id=?", (flow_id,)).fetchone()
            return Flow(**dict(row)) if row else None
        finally:
            conn.close()

    def find_recent_flow(self, src_ip: str, dst_ip: str, port: int, within_seconds: int = 60) -> Optional[Flow]:
        """Idempotent flow lookup for dedup within time window."""
        conn = self._conn()
        try:
            # Normalize cutoff to +00:00 format (matches datetime.now(timezone.utc).isoformat())
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
            # Use REPLACE to normalize Z suffix to +00:00 for consistent comparison
            row = conn.execute(
                "SELECT * FROM flows WHERE src_ip=? AND dst_ip=? AND port=? "
                "AND REPLACE(timestamp, 'Z', '+00:00') >= ? ORDER BY timestamp DESC LIMIT 1",
                (src_ip, dst_ip, port, cutoff),
            ).fetchone()
            return Flow(**dict(row)) if row else None
        finally:
            conn.close()

    def update_flow_status(self, flow_id: str, status: str, confidence: float = 0.0) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE flows SET diagnosis_status=?, confidence=? WHERE id=?",
                (status, confidence, flow_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Trace CRUD ──
    def add_trace(self, trace: Trace) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO traces VALUES (?,?,?,?,?,?,?,?)",
                (trace.id, trace.flow_id, trace.src, trace.dst, trace.method.value,
                 trace.timestamp, trace.raw_output, trace.hop_count),
            )
            conn.commit()
        finally:
            conn.close()

    def add_trace_hop(self, hop: TraceHop) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO trace_hops VALUES (?,?,?,?,?,?,?)",
                (hop.id, hop.trace_id, hop.hop_number, hop.ip, hop.device_id,
                 hop.rtt_ms, hop.status.value),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Flow Verdict CRUD ──
    def add_flow_verdict(self, verdict: FlowVerdict) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO flow_verdicts VALUES (?,?,?,?,?,?,?,?,?)",
                (verdict.id, verdict.flow_id, verdict.firewall_id, verdict.rule_id,
                 verdict.action.value, int(verdict.nat_applied), verdict.confidence,
                 verdict.match_type.value, verdict.evidence_type),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Adapter Config CRUD ──
    def save_adapter_config(self, config: AdapterConfig) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO adapter_configs VALUES (?,?,?,?)",
                (config.vendor.value, config.api_endpoint, config.api_key,
                 json.dumps(config.extra_config)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_adapter_config(self, vendor: str) -> Optional[AdapterConfig]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM adapter_configs WHERE vendor=?", (vendor,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["extra_config"] = self._safe_json_loads(d.get("extra_config"), fallback={})
            return AdapterConfig(**d)
        finally:
            conn.close()

    # ── Adapter Instance CRUD ──

    def save_adapter_instance(self, instance: AdapterInstance) -> None:
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            # Preserve created_at on update
            existing = conn.execute(
                "SELECT created_at FROM adapter_instances WHERE instance_id=?",
                (instance.instance_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else (instance.created_at or now)
            # Encrypt api_key before storing
            encrypted_key = instance.api_key
            if instance.api_key:
                resolver = get_credential_resolver()
                encrypted_key = resolver.encrypt_and_store(
                    instance.instance_id, "adapter_api_key", instance.api_key
                )
            conn.execute(
                "INSERT OR REPLACE INTO adapter_instances (instance_id, label, vendor, api_endpoint, api_key, extra_config, device_groups, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (instance.instance_id, instance.label, instance.vendor.value,
                 instance.api_endpoint, encrypted_key,
                 json.dumps(instance.extra_config), json.dumps(instance.device_groups),
                 created_at, now),
            )
            conn.commit()
        finally:
            conn.close()

    def get_adapter_instance(self, instance_id: str) -> Optional[AdapterInstance]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM adapter_instances WHERE instance_id=?", (instance_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["extra_config"] = self._safe_json_loads(d.get("extra_config"), fallback={})
            d["device_groups"] = self._safe_json_loads(d.get("device_groups"))
            result = AdapterInstance(**d)
            if result.api_key:
                try:
                    resolver = get_credential_resolver()
                    result.api_key = resolver.resolve(
                        result.instance_id, "adapter_api_key", result.api_key
                    )
                except Exception:
                    result.api_key = ""  # Handle corrupted/old entries
            return result
        finally:
            conn.close()

    def list_adapter_instances(self) -> list[AdapterInstance]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM adapter_instances ORDER BY created_at").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["extra_config"] = self._safe_json_loads(d.get("extra_config"), fallback={})
                d["device_groups"] = self._safe_json_loads(d.get("device_groups"))
                inst = AdapterInstance(**d)
                if inst.api_key:
                    try:
                        resolver = get_credential_resolver()
                        inst.api_key = resolver.resolve(
                            inst.instance_id, "adapter_api_key", inst.api_key
                        )
                    except Exception:
                        inst.api_key = ""  # Handle corrupted/old entries
                results.append(inst)
            return results
        finally:
            conn.close()

    def list_adapter_instances_by_vendor(self, vendor: str) -> list[AdapterInstance]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM adapter_instances WHERE vendor=? ORDER BY created_at", (vendor,)).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["extra_config"] = self._safe_json_loads(d.get("extra_config"), fallback={})
                d["device_groups"] = self._safe_json_loads(d.get("device_groups"))
                inst = AdapterInstance(**d)
                if inst.api_key:
                    try:
                        resolver = get_credential_resolver()
                        inst.api_key = resolver.resolve(
                            inst.instance_id, "adapter_api_key", inst.api_key
                        )
                    except Exception:
                        inst.api_key = ""  # Handle corrupted/old entries
                results.append(inst)
            return results
        finally:
            conn.close()

    def delete_adapter_instance(self, instance_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM adapter_device_bindings WHERE instance_id=?", (instance_id,))
            conn.execute("DELETE FROM adapter_instances WHERE instance_id=?", (instance_id,))
            conn.commit()
        finally:
            conn.close()

    def save_device_binding(self, device_id: str, instance_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO adapter_device_bindings (device_id, instance_id) VALUES (?,?)",
                (device_id, instance_id),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_device_binding(self, device_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM adapter_device_bindings WHERE device_id=?", (device_id,))
            conn.commit()
        finally:
            conn.close()

    def list_device_bindings(self) -> list[tuple[str, str]]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT device_id, instance_id FROM adapter_device_bindings").fetchall()
            return [(r["device_id"], r["instance_id"]) for r in rows]
        finally:
            conn.close()

    def list_device_bindings_for_instance(self, instance_id: str) -> list[str]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT device_id FROM adapter_device_bindings WHERE instance_id=?",
                (instance_id,),
            ).fetchall()
            return [r["device_id"] for r in rows]
        finally:
            conn.close()

    # ── Diagram Snapshots ──
    def save_diagram_snapshot(self, snapshot_json: str, description: str = "") -> int:
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO diagram_snapshots (snapshot_json, timestamp, description) VALUES (?,?,?)",
                (snapshot_json, datetime.now(timezone.utc).isoformat(), description),
            )
            conn.commit()
            snap_id = cursor.lastrowid
            return snap_id
        finally:
            conn.close()

    def load_diagram_snapshot(self) -> Optional[dict]:
        """Load the most recent diagram snapshot."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM diagram_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            return {
                "id": d["id"],
                "snapshot_json": d["snapshot_json"],
                "timestamp": d["timestamp"],
                "description": d["description"],
            }
        finally:
            conn.close()

    def list_diagram_snapshots(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, timestamp, description FROM diagram_snapshots ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def load_diagram_snapshot_by_id(self, snap_id: int) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM diagram_snapshots WHERE id=?", (snap_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            return {
                "id": d["id"],
                "snapshot_json": d["snapshot_json"],
                "timestamp": d["timestamp"],
                "description": d["description"],
            }
        finally:
            conn.close()

    def list_flows(self, limit: int = 50) -> list[Flow]:
        """List recent flows, ordered by timestamp descending."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM flows ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [Flow(**dict(r)) for r in rows]
        finally:
            conn.close()

    def list_traces(self, flow_id: Optional[str] = None) -> list[Trace]:
        conn = self._conn()
        try:
            if flow_id:
                rows = conn.execute("SELECT * FROM traces WHERE flow_id=?", (flow_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM traces").fetchall()
            return [Trace(**dict(r)) for r in rows]
        finally:
            conn.close()

    def list_trace_hops(self, trace_id: str) -> list[TraceHop]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM trace_hops WHERE trace_id=? ORDER BY hop_number",
                (trace_id,),
            ).fetchall()
            return [TraceHop(**dict(r)) for r in rows]
        finally:
            conn.close()

    def list_flow_verdicts(self, flow_id: str) -> list[FlowVerdict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM flow_verdicts WHERE flow_id=?", (flow_id,)
            ).fetchall()
            return [FlowVerdict(**dict(r)) for r in rows]
        finally:
            conn.close()

    # ── VPC CRUD ──
    def add_vpc(self, vpc: VPC) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO vpcs VALUES (?,?,?,?,?,?,?)",
                (vpc.id, vpc.name, vpc.cloud_provider.value, vpc.region,
                 json.dumps(vpc.cidr_blocks), vpc.account_id, vpc.compliance_zone),
            )
            conn.commit()
        finally:
            conn.close()

    def list_vpcs(self) -> list[VPC]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM vpcs").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["cidr_blocks"] = self._safe_json_loads(d.get("cidr_blocks"))
                results.append(VPC(**d))
            return results
        finally:
            conn.close()

    def get_vpc(self, vpc_id: str) -> Optional[VPC]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM vpcs WHERE id=?", (vpc_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["cidr_blocks"] = self._safe_json_loads(d.get("cidr_blocks"))
            return VPC(**d)
        finally:
            conn.close()

    def delete_vpc(self, vpc_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM route_tables WHERE vpc_id=?", (vpc_id,))
            conn.execute("DELETE FROM vpcs WHERE id=?", (vpc_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Route Table CRUD ──
    def add_route_table(self, rt: RouteTable) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO route_tables VALUES (?,?,?,?)",
                (rt.id, rt.vpc_id, rt.name, int(rt.is_main)),
            )
            conn.commit()
        finally:
            conn.close()

    def list_route_tables(self, vpc_id: Optional[str] = None) -> list[RouteTable]:
        conn = self._conn()
        try:
            if vpc_id:
                rows = conn.execute("SELECT * FROM route_tables WHERE vpc_id=?", (vpc_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM route_tables").fetchall()
            return [RouteTable(**{**dict(r), "is_main": bool(r["is_main"])}) for r in rows]
        finally:
            conn.close()

    # ── VPC Peering CRUD ──
    def add_vpc_peering(self, p: VPCPeering) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO vpc_peerings VALUES (?,?,?,?,?)",
                (p.id, p.requester_vpc_id, p.accepter_vpc_id, p.status,
                 json.dumps(p.cidr_routes)),
            )
            conn.commit()
        finally:
            conn.close()

    def list_vpc_peerings(self) -> list[VPCPeering]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM vpc_peerings").fetchall()
            return [VPCPeering(**{**dict(r), "cidr_routes": self._safe_json_loads(r["cidr_routes"])}) for r in rows]
        finally:
            conn.close()

    # ── Transit Gateway CRUD ──
    def add_transit_gateway(self, tgw: TransitGateway) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO transit_gateways VALUES (?,?,?,?,?,?)",
                (tgw.id, tgw.name, tgw.cloud_provider.value, tgw.region,
                 json.dumps(tgw.attached_vpc_ids), tgw.route_table_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_transit_gateways(self) -> list[TransitGateway]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM transit_gateways").fetchall()
            return [TransitGateway(**{**dict(r), "attached_vpc_ids": self._safe_json_loads(r["attached_vpc_ids"])}) for r in rows]
        finally:
            conn.close()

    # ── VPN Tunnel CRUD ──
    def add_vpn_tunnel(self, vpn: VPNTunnel) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO vpn_tunnels VALUES (?,?,?,?,?,?,?,?,?,?)",
                (vpn.id, vpn.name, vpn.tunnel_type.value, vpn.local_gateway_id,
                 vpn.remote_gateway_ip, json.dumps(vpn.local_cidrs), json.dumps(vpn.remote_cidrs),
                 vpn.encryption, vpn.ike_version, vpn.status.value),
            )
            conn.commit()
        finally:
            conn.close()

    def list_vpn_tunnels(self) -> list[VPNTunnel]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM vpn_tunnels").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["local_cidrs"] = self._safe_json_loads(d.get("local_cidrs"))
                d["remote_cidrs"] = self._safe_json_loads(d.get("remote_cidrs"))
                results.append(VPNTunnel(**d))
            return results
        finally:
            conn.close()

    # ── Direct Connect CRUD ──
    def add_direct_connect(self, dx: DirectConnect) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO direct_connects VALUES (?,?,?,?,?,?,?,?)",
                (dx.id, dx.name, dx.provider.value, dx.bandwidth_mbps,
                 dx.location, dx.vlan_id, dx.bgp_asn, dx.status.value),
            )
            conn.commit()
        finally:
            conn.close()

    def list_direct_connects(self) -> list[DirectConnect]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM direct_connects").fetchall()
            return [DirectConnect(**dict(r)) for r in rows]
        finally:
            conn.close()

    # ── NACL CRUD ──
    def add_nacl(self, nacl: NACL) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO nacls VALUES (?,?,?,?,?)",
                (nacl.id, nacl.name, nacl.vpc_id, json.dumps(nacl.subnet_ids), int(nacl.is_default)),
            )
            conn.commit()
        finally:
            conn.close()

    def list_nacls(self, vpc_id: Optional[str] = None) -> list[NACL]:
        conn = self._conn()
        try:
            if vpc_id:
                rows = conn.execute("SELECT * FROM nacls WHERE vpc_id=?", (vpc_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM nacls").fetchall()
            return [NACL(**{**dict(r), "subnet_ids": self._safe_json_loads(r["subnet_ids"]), "is_default": bool(r["is_default"])}) for r in rows]
        finally:
            conn.close()

    # ── NACL Rule CRUD ──
    def add_nacl_rule(self, rule: NACLRule) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO nacl_rules VALUES (?,?,?,?,?,?,?,?,?)",
                (rule.id, rule.nacl_id, rule.direction.value, rule.rule_number,
                 rule.protocol, rule.cidr, rule.port_range_from, rule.port_range_to,
                 rule.action.value),
            )
            conn.commit()
        finally:
            conn.close()

    def list_nacl_rules(self, nacl_id: str) -> list[NACLRule]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM nacl_rules WHERE nacl_id=? ORDER BY rule_number",
                (nacl_id,),
            ).fetchall()
            return [NACLRule(**dict(r)) for r in rows]
        finally:
            conn.close()

    # ── Load Balancer CRUD ──
    def add_load_balancer(self, lb: LoadBalancer) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO load_balancers VALUES (?,?,?,?,?,?,?)",
                (lb.id, lb.name, lb.lb_type.value, lb.scheme.value, lb.vpc_id,
                 json.dumps(lb.listeners), lb.health_check_path),
            )
            conn.commit()
        finally:
            conn.close()

    def list_load_balancers(self) -> list[LoadBalancer]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM load_balancers").fetchall()
            return [LoadBalancer(**{**dict(r), "listeners": self._safe_json_loads(r["listeners"])}) for r in rows]
        finally:
            conn.close()

    # ── LB Target Group CRUD ──
    def add_lb_target_group(self, tg: LBTargetGroup) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO lb_target_groups VALUES (?,?,?,?,?,?,?)",
                (tg.id, tg.lb_id, tg.name, tg.protocol, tg.port,
                 json.dumps(tg.target_ids), tg.health_status),
            )
            conn.commit()
        finally:
            conn.close()

    def list_lb_target_groups(self, lb_id: Optional[str] = None) -> list[LBTargetGroup]:
        conn = self._conn()
        try:
            if lb_id:
                rows = conn.execute("SELECT * FROM lb_target_groups WHERE lb_id=?", (lb_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM lb_target_groups").fetchall()
            return [LBTargetGroup(**{**dict(r), "target_ids": self._safe_json_loads(r["target_ids"])}) for r in rows]
        finally:
            conn.close()

    # ── VLAN CRUD ──
    def add_vlan(self, vlan: VLAN) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO vlans VALUES (?,?,?,?,?,?)",
                (vlan.id, vlan.vlan_number, vlan.name,
                 json.dumps(vlan.trunk_ports), json.dumps(vlan.access_ports), vlan.site),
            )
            conn.commit()
        finally:
            conn.close()

    def list_vlans(self) -> list[VLAN]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM vlans").fetchall()
            return [VLAN(**{**dict(r), "trunk_ports": self._safe_json_loads(r["trunk_ports"]), "access_ports": self._safe_json_loads(r["access_ports"])}) for r in rows]
        finally:
            conn.close()

    # ── MPLS Circuit CRUD ──
    def add_mpls_circuit(self, mpls: MPLSCircuit) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO mpls_circuits VALUES (?,?,?,?,?,?,?)",
                (mpls.id, mpls.name, mpls.label, mpls.provider,
                 mpls.bandwidth_mbps, json.dumps(mpls.endpoints), mpls.qos_class),
            )
            conn.commit()
        finally:
            conn.close()

    def list_mpls_circuits(self) -> list[MPLSCircuit]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM mpls_circuits").fetchall()
            return [MPLSCircuit(**{**dict(r), "endpoints": self._safe_json_loads(r["endpoints"])}) for r in rows]
        finally:
            conn.close()

    # ── Compliance Zone CRUD ──
    def add_compliance_zone(self, cz: ComplianceZone) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO compliance_zones VALUES (?,?,?,?,?,?)",
                (cz.id, cz.name, cz.standard.value, cz.description,
                 json.dumps(cz.subnet_ids), json.dumps(cz.vpc_ids)),
            )
            conn.commit()
        finally:
            conn.close()

    def list_compliance_zones(self) -> list[ComplianceZone]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM compliance_zones").fetchall()
            return [ComplianceZone(**{**dict(r), "subnet_ids": self._safe_json_loads(r["subnet_ids"]), "vpc_ids": self._safe_json_loads(r["vpc_ids"])}) for r in rows]
        finally:
            conn.close()

    # ── HA Group CRUD ──
    def add_ha_group(self, group: HAGroup) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO ha_groups (id, name, ha_mode, member_ids, virtual_ips, active_member_id, priority_map, sync_interface) VALUES (?,?,?,?,?,?,?,?)",
                (group.id, group.name, group.ha_mode.value, json.dumps(group.member_ids),
                 json.dumps(group.virtual_ips), group.active_member_id,
                 json.dumps(group.priority_map), group.sync_interface),
            )
            conn.commit()
        finally:
            conn.close()

    def get_ha_group(self, group_id: str) -> Optional[HAGroup]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM ha_groups WHERE id = ?", (group_id,)).fetchone()
            if not row:
                return None
            return HAGroup(
                id=row["id"], name=row["name"],
                ha_mode=HAMode(row["ha_mode"]),
                member_ids=self._safe_json_loads(row["member_ids"]),
                virtual_ips=self._safe_json_loads(row["virtual_ips"]),
                active_member_id=row["active_member_id"] or "",
                priority_map=self._safe_json_loads(row["priority_map"], fallback={}),
                sync_interface=row["sync_interface"] or "",
            )
        finally:
            conn.close()

    def list_ha_groups(self) -> list[HAGroup]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM ha_groups").fetchall()
            return [HAGroup(
                id=r["id"], name=r["name"],
                ha_mode=HAMode(r["ha_mode"]),
                member_ids=self._safe_json_loads(r["member_ids"]),
                virtual_ips=self._safe_json_loads(r["virtual_ips"]),
                active_member_id=r["active_member_id"] or "",
                priority_map=self._safe_json_loads(r["priority_map"], fallback={}),
                sync_interface=r["sync_interface"] or "",
            ) for r in rows]
        finally:
            conn.close()

    def delete_ha_group(self, group_id: str) -> None:
        conn = self._conn()
        try:
            # Clear ha_group_id on member devices
            conn.execute("UPDATE devices SET ha_group_id='', ha_role='' WHERE ha_group_id=?", (group_id,))
            conn.execute("DELETE FROM ha_groups WHERE id=?", (group_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Edge Confidence Persistence ──
    def save_edge_confidence(self, src_id: str, dst_id: str, confidence: float, source: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO edge_confidence VALUES (?,?,?,?,?)",
                (src_id, dst_id, confidence, source, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def list_edge_confidences(self) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM edge_confidence").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Device Status ──

    def upsert_device_status(self, device_id: str, status: str, latency_ms: float,
                              packet_loss: float, probe_method: str) -> None:
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            existing = conn.execute(
                "SELECT status, last_status_change FROM device_status WHERE device_id=?",
                (device_id,),
            ).fetchone()
            if existing:
                last_change = existing["last_status_change"]
                if existing["status"] != status:
                    last_change = now
                conn.execute(
                    "UPDATE device_status SET status=?, latency_ms=?, packet_loss=?, "
                    "last_seen=?, last_status_change=?, probe_method=?, updated_at=? "
                    "WHERE device_id=?",
                    (status, latency_ms, packet_loss, now, last_change, probe_method, now, device_id),
                )
            else:
                conn.execute(
                    "INSERT INTO device_status VALUES (?,?,?,?,?,?,?,?)",
                    (device_id, status, latency_ms, packet_loss, now, now, probe_method, now),
                )
            conn.commit()
        finally:
            conn.close()

    def get_device_status(self, device_id: str):
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM device_status WHERE device_id=?", (device_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_device_statuses(self) -> list:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM device_status").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Link Metrics ──

    def upsert_link_metric(self, src_id: str, dst_id: str, latency_ms: float,
                            bandwidth_bps: int, error_rate: float, utilization: float) -> None:
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO link_metrics VALUES (?,?,?,?,?,?,?)",
                (src_id, dst_id, latency_ms, bandwidth_bps, error_rate, utilization, now),
            )
            conn.commit()
        finally:
            conn.close()

    def list_link_metrics(self) -> list:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM link_metrics").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Metric History ──

    def append_metric(self, entity_type: str, entity_id: str, metric: str, value: float) -> None:
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO metric_history (entity_type, entity_id, metric, value, recorded_at) VALUES (?,?,?,?,?)",
                (entity_type, entity_id, metric, value, now),
            )
            conn.commit()
        finally:
            conn.close()

    def query_metric_history(self, entity_type: str, entity_id: str, metric: str,
                              since: str) -> list:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM metric_history WHERE entity_type=? AND entity_id=? AND metric=? "
                "AND recorded_at>=? ORDER BY recorded_at",
                (entity_type, entity_id, metric, since),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def prune_metric_history(self, older_than_days: int = 7) -> int:
        conn = self._conn()
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
            cursor = conn.execute("DELETE FROM metric_history WHERE recorded_at < ?", (cutoff,))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    # ── Drift Events ──

    def upsert_drift_event(self, entity_type: str, entity_id: str, drift_type: str,
                            field: str, expected: str, actual: str, severity: str) -> None:
        conn = self._conn()
        try:
            import uuid
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO drift_events (id, entity_type, entity_id, drift_type, field, "
                "expected, actual, severity, detected_at) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(entity_type, entity_id, drift_type, field) DO UPDATE SET "
                "expected=excluded.expected, actual=excluded.actual, severity=excluded.severity, "
                "resolved_at=NULL",
                (str(uuid.uuid4()), entity_type, entity_id, drift_type, field,
                 expected, actual, severity, now),
            )
            conn.commit()
        finally:
            conn.close()

    def resolve_drift_event(self, event_id: str) -> None:
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE drift_events SET resolved_at=? WHERE id=?", (now, event_id))
            conn.commit()
        finally:
            conn.close()

    def list_active_drift_events(self) -> list:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM drift_events WHERE resolved_at IS NULL ORDER BY severity, detected_at"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Discovery Candidates ──

    def upsert_discovery_candidate(self, ip: str, mac: str, hostname: str,
                                    discovered_via: str, source_device_id: str) -> None:
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO discovery_candidates (ip, mac, hostname, discovered_via, "
                "source_device_id, first_seen, last_seen) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(ip) DO UPDATE SET mac=excluded.mac, "
                "hostname=CASE WHEN excluded.hostname!='' THEN excluded.hostname ELSE discovery_candidates.hostname END, "
                "last_seen=excluded.last_seen",
                (ip, mac, hostname, discovered_via, source_device_id, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    def list_discovery_candidates(self) -> list:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM discovery_candidates WHERE dismissed=0 AND promoted_device_id=''"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def promote_candidate(self, ip: str, device_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE discovery_candidates SET promoted_device_id=? WHERE ip=?",
                (device_id, ip),
            )
            conn.commit()
        finally:
            conn.close()

    def dismiss_candidate(self, ip: str) -> None:
        conn = self._conn()
        try:
            conn.execute("UPDATE discovery_candidates SET dismissed=1 WHERE ip=?", (ip,))
            conn.commit()
        finally:
            conn.close()

    # ── Alert History ──

    def upsert_alert_history(
        self, alert_key: str, rule_id: str, rule_name: str,
        entity_id: str, severity: str, metric: str,
        value: float, threshold: float, condition: str,
        state: str, message: str = "",
    ) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO alert_history
                   (alert_key, rule_id, rule_name, entity_id, severity,
                    metric, value, threshold, condition, state, message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (alert_key, rule_id, rule_name, entity_id, severity,
                 metric, value, threshold, condition, state, message),
            )
            conn.commit()
        finally:
            conn.close()

    def list_alert_history(
        self, severity: str = "", entity_id: str = "",
        state: str = "", limit: int = 100,
    ) -> list[dict]:
        clauses = []
        params: list = []
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if state:
            clauses.append("state = ?")
            params.append(state)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        conn = self._conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM alert_history {where} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def count_alert_history(self, severity: str = "") -> int:
        conn = self._conn()
        try:
            if severity:
                row = conn.execute(
                    "SELECT COUNT(*) FROM alert_history WHERE severity = ?", (severity,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM alert_history").fetchone()
            return row[0]
        finally:
            conn.close()

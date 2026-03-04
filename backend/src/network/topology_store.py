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
    AdapterConfig,
    VPC, RouteTable, VPCPeering, TransitGateway,
    VPNTunnel, DirectConnect,
    NACL, NACLRule,
    LoadBalancer, LBTargetGroup,
    VLAN, MPLSCircuit, ComplianceZone,
    HAGroup, HAMode,
)

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
        return conn

    def _init_tables(self):
        conn = self._conn()
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
                FOREIGN KEY (device_id) REFERENCES devices(id)
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

            CREATE TABLE IF NOT EXISTS vpcs (
                id TEXT PRIMARY KEY, name TEXT, cloud_provider TEXT,
                region TEXT, cidr_blocks TEXT, account_id TEXT, compliance_zone TEXT
            );
            CREATE TABLE IF NOT EXISTS route_tables (
                id TEXT PRIMARY KEY, vpc_id TEXT, name TEXT, is_main INTEGER,
                FOREIGN KEY (vpc_id) REFERENCES vpcs(id)
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
                FOREIGN KEY (nacl_id) REFERENCES nacls(id)
            );
            CREATE TABLE IF NOT EXISTS load_balancers (
                id TEXT PRIMARY KEY, name TEXT, lb_type TEXT,
                scheme TEXT, vpc_id TEXT, listeners TEXT, health_check_path TEXT
            );
            CREATE TABLE IF NOT EXISTS lb_target_groups (
                id TEXT PRIMARY KEY, lb_id TEXT, name TEXT,
                protocol TEXT, port INTEGER, target_ids TEXT, health_status TEXT,
                FOREIGN KEY (lb_id) REFERENCES load_balancers(id)
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
        """)
        conn.commit()
        conn.close()

    def _migrate_tables(self):
        """Add columns that may be missing from older schemas."""
        conn = self._conn()
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
        conn.close()

    # ── Device CRUD ──
    def add_device(self, device: Device) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO devices (id, name, vendor, device_type, management_ip, model, location, zone_id, vlan_id, description, ha_group_id, ha_role) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (device.id, device.name, device.vendor, device.device_type.value,
             device.management_ip, device.model, device.location,
             device.zone_id, device.vlan_id, device.description,
             device.ha_group_id, device.ha_role),
        )
        conn.commit()
        conn.close()

    def get_device(self, device_id: str) -> Optional[Device]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        conn.close()
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

    def list_devices(self) -> list[Device]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM devices").fetchall()
        conn.close()
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
            "INSERT OR REPLACE INTO interfaces VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (iface.id, iface.device_id, iface.name, iface.ip,
             iface.mac, iface.zone_id, iface.vrf, iface.speed, iface.status,
             iface.role, iface.subnet_id),
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
            "INSERT OR REPLACE INTO zones VALUES (?,?,?,?,?,?)",
            (zone.id, zone.name, zone.security_level, zone.description,
             zone.firewall_id, zone.zone_type),
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

    def list_diagram_snapshots(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, timestamp, description FROM diagram_snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def load_diagram_snapshot_by_id(self, snap_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM diagram_snapshots WHERE id=?", (snap_id,)).fetchone()
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

    # ── VPC CRUD ──
    def add_vpc(self, vpc: VPC) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO vpcs VALUES (?,?,?,?,?,?,?)",
            (vpc.id, vpc.name, vpc.cloud_provider.value, vpc.region,
             json.dumps(vpc.cidr_blocks), vpc.account_id, vpc.compliance_zone),
        )
        conn.commit(); conn.close()

    def list_vpcs(self) -> list[VPC]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM vpcs").fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["cidr_blocks"] = json.loads(d["cidr_blocks"]) if d["cidr_blocks"] else []
            results.append(VPC(**d))
        return results

    def get_vpc(self, vpc_id: str) -> Optional[VPC]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM vpcs WHERE id=?", (vpc_id,)).fetchone()
        conn.close()
        if not row: return None
        d = dict(row)
        d["cidr_blocks"] = json.loads(d["cidr_blocks"]) if d["cidr_blocks"] else []
        return VPC(**d)

    # ── Route Table CRUD ──
    def add_route_table(self, rt: RouteTable) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO route_tables VALUES (?,?,?,?)",
            (rt.id, rt.vpc_id, rt.name, int(rt.is_main)),
        )
        conn.commit(); conn.close()

    def list_route_tables(self, vpc_id: Optional[str] = None) -> list[RouteTable]:
        conn = self._conn()
        if vpc_id:
            rows = conn.execute("SELECT * FROM route_tables WHERE vpc_id=?", (vpc_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM route_tables").fetchall()
        conn.close()
        return [RouteTable(**{**dict(r), "is_main": bool(r["is_main"])}) for r in rows]

    # ── VPC Peering CRUD ──
    def add_vpc_peering(self, p: VPCPeering) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO vpc_peerings VALUES (?,?,?,?,?)",
            (p.id, p.requester_vpc_id, p.accepter_vpc_id, p.status,
             json.dumps(p.cidr_routes)),
        )
        conn.commit(); conn.close()

    def list_vpc_peerings(self) -> list[VPCPeering]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM vpc_peerings").fetchall()
        conn.close()
        return [VPCPeering(**{**dict(r), "cidr_routes": json.loads(r["cidr_routes"]) if r["cidr_routes"] else []}) for r in rows]

    # ── Transit Gateway CRUD ──
    def add_transit_gateway(self, tgw: TransitGateway) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO transit_gateways VALUES (?,?,?,?,?,?)",
            (tgw.id, tgw.name, tgw.cloud_provider.value, tgw.region,
             json.dumps(tgw.attached_vpc_ids), tgw.route_table_id),
        )
        conn.commit(); conn.close()

    def list_transit_gateways(self) -> list[TransitGateway]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM transit_gateways").fetchall()
        conn.close()
        return [TransitGateway(**{**dict(r), "attached_vpc_ids": json.loads(r["attached_vpc_ids"]) if r["attached_vpc_ids"] else []}) for r in rows]

    # ── VPN Tunnel CRUD ──
    def add_vpn_tunnel(self, vpn: VPNTunnel) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO vpn_tunnels VALUES (?,?,?,?,?,?,?,?,?,?)",
            (vpn.id, vpn.name, vpn.tunnel_type.value, vpn.local_gateway_id,
             vpn.remote_gateway_ip, json.dumps(vpn.local_cidrs), json.dumps(vpn.remote_cidrs),
             vpn.encryption, vpn.ike_version, vpn.status.value),
        )
        conn.commit(); conn.close()

    def list_vpn_tunnels(self) -> list[VPNTunnel]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM vpn_tunnels").fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["local_cidrs"] = json.loads(d["local_cidrs"]) if d["local_cidrs"] else []
            d["remote_cidrs"] = json.loads(d["remote_cidrs"]) if d["remote_cidrs"] else []
            results.append(VPNTunnel(**d))
        return results

    # ── Direct Connect CRUD ──
    def add_direct_connect(self, dx: DirectConnect) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO direct_connects VALUES (?,?,?,?,?,?,?,?)",
            (dx.id, dx.name, dx.provider.value, dx.bandwidth_mbps,
             dx.location, dx.vlan_id, dx.bgp_asn, dx.status.value),
        )
        conn.commit(); conn.close()

    def list_direct_connects(self) -> list[DirectConnect]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM direct_connects").fetchall()
        conn.close()
        return [DirectConnect(**dict(r)) for r in rows]

    # ── NACL CRUD ──
    def add_nacl(self, nacl: NACL) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO nacls VALUES (?,?,?,?,?)",
            (nacl.id, nacl.name, nacl.vpc_id, json.dumps(nacl.subnet_ids), int(nacl.is_default)),
        )
        conn.commit(); conn.close()

    def list_nacls(self, vpc_id: Optional[str] = None) -> list[NACL]:
        conn = self._conn()
        if vpc_id:
            rows = conn.execute("SELECT * FROM nacls WHERE vpc_id=?", (vpc_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM nacls").fetchall()
        conn.close()
        return [NACL(**{**dict(r), "subnet_ids": json.loads(r["subnet_ids"]) if r["subnet_ids"] else [], "is_default": bool(r["is_default"])}) for r in rows]

    # ── NACL Rule CRUD ──
    def add_nacl_rule(self, rule: NACLRule) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO nacl_rules VALUES (?,?,?,?,?,?,?,?,?)",
            (rule.id, rule.nacl_id, rule.direction.value, rule.rule_number,
             rule.protocol, rule.cidr, rule.port_range_from, rule.port_range_to,
             rule.action.value),
        )
        conn.commit(); conn.close()

    def list_nacl_rules(self, nacl_id: str) -> list[NACLRule]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM nacl_rules WHERE nacl_id=? ORDER BY rule_number",
            (nacl_id,),
        ).fetchall()
        conn.close()
        return [NACLRule(**dict(r)) for r in rows]

    # ── Load Balancer CRUD ──
    def add_load_balancer(self, lb: LoadBalancer) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO load_balancers VALUES (?,?,?,?,?,?,?)",
            (lb.id, lb.name, lb.lb_type.value, lb.scheme.value, lb.vpc_id,
             json.dumps(lb.listeners), lb.health_check_path),
        )
        conn.commit(); conn.close()

    def list_load_balancers(self) -> list[LoadBalancer]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM load_balancers").fetchall()
        conn.close()
        return [LoadBalancer(**{**dict(r), "listeners": json.loads(r["listeners"]) if r["listeners"] else []}) for r in rows]

    # ── LB Target Group CRUD ──
    def add_lb_target_group(self, tg: LBTargetGroup) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO lb_target_groups VALUES (?,?,?,?,?,?,?)",
            (tg.id, tg.lb_id, tg.name, tg.protocol, tg.port,
             json.dumps(tg.target_ids), tg.health_status),
        )
        conn.commit(); conn.close()

    def list_lb_target_groups(self, lb_id: Optional[str] = None) -> list[LBTargetGroup]:
        conn = self._conn()
        if lb_id:
            rows = conn.execute("SELECT * FROM lb_target_groups WHERE lb_id=?", (lb_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM lb_target_groups").fetchall()
        conn.close()
        return [LBTargetGroup(**{**dict(r), "target_ids": json.loads(r["target_ids"]) if r["target_ids"] else []}) for r in rows]

    # ── VLAN CRUD ──
    def add_vlan(self, vlan: VLAN) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO vlans VALUES (?,?,?,?,?,?)",
            (vlan.id, vlan.vlan_number, vlan.name,
             json.dumps(vlan.trunk_ports), json.dumps(vlan.access_ports), vlan.site),
        )
        conn.commit(); conn.close()

    def list_vlans(self) -> list[VLAN]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM vlans").fetchall()
        conn.close()
        return [VLAN(**{**dict(r), "trunk_ports": json.loads(r["trunk_ports"]) if r["trunk_ports"] else [], "access_ports": json.loads(r["access_ports"]) if r["access_ports"] else []}) for r in rows]

    # ── MPLS Circuit CRUD ──
    def add_mpls_circuit(self, mpls: MPLSCircuit) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO mpls_circuits VALUES (?,?,?,?,?,?,?)",
            (mpls.id, mpls.name, mpls.label, mpls.provider,
             mpls.bandwidth_mbps, json.dumps(mpls.endpoints), mpls.qos_class),
        )
        conn.commit(); conn.close()

    def list_mpls_circuits(self) -> list[MPLSCircuit]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM mpls_circuits").fetchall()
        conn.close()
        return [MPLSCircuit(**{**dict(r), "endpoints": json.loads(r["endpoints"]) if r["endpoints"] else []}) for r in rows]

    # ── Compliance Zone CRUD ──
    def add_compliance_zone(self, cz: ComplianceZone) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO compliance_zones VALUES (?,?,?,?,?,?)",
            (cz.id, cz.name, cz.standard.value, cz.description,
             json.dumps(cz.subnet_ids), json.dumps(cz.vpc_ids)),
        )
        conn.commit(); conn.close()

    def list_compliance_zones(self) -> list[ComplianceZone]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM compliance_zones").fetchall()
        conn.close()
        return [ComplianceZone(**{**dict(r), "subnet_ids": json.loads(r["subnet_ids"]) if r["subnet_ids"] else [], "vpc_ids": json.loads(r["vpc_ids"]) if r["vpc_ids"] else []}) for r in rows]

    # ── HA Group CRUD ──
    def add_ha_group(self, group: HAGroup) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO ha_groups (id, name, ha_mode, member_ids, virtual_ips, active_member_id, priority_map, sync_interface) VALUES (?,?,?,?,?,?,?,?)",
            (group.id, group.name, group.ha_mode.value, json.dumps(group.member_ids),
             json.dumps(group.virtual_ips), group.active_member_id,
             json.dumps(group.priority_map), group.sync_interface),
        )
        conn.commit()
        conn.close()

    def get_ha_group(self, group_id: str) -> Optional[HAGroup]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM ha_groups WHERE id = ?", (group_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return HAGroup(
            id=row["id"], name=row["name"],
            ha_mode=HAMode(row["ha_mode"]),
            member_ids=json.loads(row["member_ids"]),
            virtual_ips=json.loads(row["virtual_ips"] or "[]"),
            active_member_id=row["active_member_id"] or "",
            priority_map=json.loads(row["priority_map"] or "{}"),
            sync_interface=row["sync_interface"] or "",
        )

    def list_ha_groups(self) -> list[HAGroup]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM ha_groups").fetchall()
        conn.close()
        return [HAGroup(
            id=r["id"], name=r["name"],
            ha_mode=HAMode(r["ha_mode"]),
            member_ids=json.loads(r["member_ids"]),
            virtual_ips=json.loads(r["virtual_ips"] or "[]"),
            active_member_id=r["active_member_id"] or "",
            priority_map=json.loads(r["priority_map"] or "{}"),
            sync_interface=r["sync_interface"] or "",
        ) for r in rows]

    # ── Edge Confidence Persistence ──
    def save_edge_confidence(self, src_id: str, dst_id: str, confidence: float, source: str) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO edge_confidence VALUES (?,?,?,?,?)",
            (src_id, dst_id, confidence, source, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    def list_edge_confidences(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM edge_confidence").fetchall()
        conn.close()
        return [dict(r) for r in rows]

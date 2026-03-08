"""SQLite persistence for the Network Knowledge Graph."""
import sqlite3
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from cachetools import TTLCache
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
    IPAddress, IPStatus, IPType,
    VRF, Region, Site, AddressBlock,
    CloudAccount, CloudInterface,
)
from src.integrations.credential_resolver import get_credential_resolver

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "network.db")


class TopologyStore:
    """SQLite-backed persistence for network topology and investigation artifacts."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._cache = TTLCache(maxsize=64, ttl=10)
        self._init_tables()
        self._migrate_tables()

    def _invalidate_cache(self, *keys):
        """Remove one or more keys from the in-memory cache."""
        for key in keys:
            self._cache.pop(key, None)

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

                CREATE TABLE IF NOT EXISTS ip_addresses (
                    id TEXT PRIMARY KEY,
                    address TEXT NOT NULL,
                    subnet_id TEXT NOT NULL,
                    status TEXT DEFAULT 'available',
                    ip_type TEXT DEFAULT 'static',
                    assigned_device_id TEXT DEFAULT '',
                    assigned_interface_id TEXT DEFAULT '',
                    hostname TEXT DEFAULT '',
                    mac_address TEXT DEFAULT '',
                    vendor TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    last_seen TEXT DEFAULT '',
                    created_at TEXT DEFAULT '',
                    FOREIGN KEY (subnet_id) REFERENCES subnets(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS ip_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_id TEXT NOT NULL,
                    address TEXT NOT NULL,
                    action TEXT NOT NULL,
                    old_status TEXT DEFAULT '',
                    new_status TEXT DEFAULT '',
                    device_id TEXT DEFAULT '',
                    details TEXT DEFAULT '',
                    timestamp TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_ip_audit_ip ON ip_audit_log(ip_id);
                CREATE INDEX IF NOT EXISTS idx_ip_audit_ts ON ip_audit_log(timestamp);
                CREATE INDEX IF NOT EXISTS idx_ip_address ON ip_addresses(address);
                CREATE INDEX IF NOT EXISTS idx_ip_subnet ON ip_addresses(subnet_id);
                CREATE INDEX IF NOT EXISTS idx_ip_status ON ip_addresses(status);

                CREATE TABLE IF NOT EXISTS dhcp_scopes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    scope_cidr TEXT NOT NULL,
                    server_ip TEXT DEFAULT '',
                    subnet_id TEXT DEFAULT '',
                    total_leases INTEGER DEFAULT 0,
                    active_leases INTEGER DEFAULT 0,
                    free_count INTEGER DEFAULT 0,
                    source TEXT DEFAULT 'manual',
                    last_updated TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS reserved_ranges (
                    id TEXT PRIMARY KEY,
                    subnet_id TEXT NOT NULL,
                    start_ip TEXT NOT NULL,
                    end_ip TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    owner_team TEXT DEFAULT '',
                    created_at TEXT DEFAULT '',
                    FOREIGN KEY (subnet_id) REFERENCES subnets(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS free_ranges (
                    id TEXT PRIMARY KEY,
                    subnet_id TEXT NOT NULL,
                    start_ip TEXT NOT NULL,
                    end_ip TEXT NOT NULL,
                    host_count INTEGER DEFAULT 0,
                    FOREIGN KEY (subnet_id) REFERENCES subnets(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_free_ranges_subnet ON free_ranges(subnet_id);

                CREATE TABLE IF NOT EXISTS vrfs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    rd TEXT DEFAULT '',
                    rt_import TEXT DEFAULT '[]',
                    rt_export TEXT DEFAULT '[]',
                    description TEXT DEFAULT '',
                    device_ids TEXT DEFAULT '[]',
                    is_default INTEGER DEFAULT 0
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_vrf_name ON vrfs(name);

                CREATE TABLE IF NOT EXISTS regions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS sites (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    region_id TEXT DEFAULT '',
                    site_type TEXT DEFAULT '',
                    address TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    FOREIGN KEY (region_id) REFERENCES regions(id)
                );

                CREATE TABLE IF NOT EXISTS address_blocks (
                    id TEXT PRIMARY KEY,
                    cidr TEXT NOT NULL,
                    name TEXT DEFAULT '',
                    vrf_id TEXT DEFAULT 'default',
                    site_id TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    rir TEXT DEFAULT 'private',
                    FOREIGN KEY (vrf_id) REFERENCES vrfs(id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_addrblock_cidr_vrf ON address_blocks(cidr, vrf_id);

                CREATE TABLE IF NOT EXISTS cloud_accounts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    account_id TEXT DEFAULT '',
                    region TEXT DEFAULT '',
                    credentials_ref TEXT DEFAULT '',
                    sync_enabled INTEGER DEFAULT 0,
                    last_sync TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS cloud_interfaces (
                    id TEXT PRIMARY KEY,
                    cloud_account_id TEXT NOT NULL,
                    instance_id TEXT DEFAULT '',
                    instance_name TEXT DEFAULT '',
                    vpc_id TEXT DEFAULT '',
                    subnet_id TEXT DEFAULT '',
                    security_group_ids TEXT DEFAULT '[]',
                    private_ips TEXT DEFAULT '[]',
                    public_ip TEXT DEFAULT '',
                    mac_address TEXT DEFAULT '',
                    status TEXT DEFAULT 'in-use',
                    FOREIGN KEY (cloud_account_id) REFERENCES cloud_accounts(id) ON DELETE CASCADE
                );
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
                "ALTER TABLE subnets ADD COLUMN parent_subnet_id TEXT DEFAULT ''",
                "ALTER TABLE subnets ADD COLUMN region TEXT DEFAULT ''",
                "ALTER TABLE subnets ADD COLUMN environment TEXT DEFAULT ''",
                "ALTER TABLE subnets ADD COLUMN ip_version INTEGER DEFAULT 4",
                "ALTER TABLE ip_addresses ADD COLUMN mac_address TEXT DEFAULT ''",
                "ALTER TABLE ip_addresses ADD COLUMN vendor TEXT DEFAULT ''",
                "ALTER TABLE subnets ADD COLUMN vpc_id TEXT DEFAULT ''",
                "ALTER TABLE subnets ADD COLUMN cloud_provider TEXT DEFAULT ''",
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_ip_unique_addr_subnet ON ip_addresses(address, subnet_id)",
                # Phase 1: IP ownership + discovery fields
                "ALTER TABLE ip_addresses ADD COLUMN owner_team TEXT DEFAULT ''",
                "ALTER TABLE ip_addresses ADD COLUMN application TEXT DEFAULT ''",
                "ALTER TABLE ip_addresses ADD COLUMN environment TEXT DEFAULT ''",
                "ALTER TABLE ip_addresses ADD COLUMN discovery_source TEXT DEFAULT ''",
                "ALTER TABLE ip_addresses ADD COLUMN confidence_score REAL DEFAULT 1.0",
                # Phase 2: VRF + subnet fields
                "ALTER TABLE subnets ADD COLUMN vrf_id TEXT DEFAULT 'default'",
                "ALTER TABLE subnets ADD COLUMN subnet_role TEXT DEFAULT ''",
                "ALTER TABLE subnets ADD COLUMN address_block_id TEXT DEFAULT ''",
                "ALTER TABLE subnets ADD COLUMN site_id TEXT DEFAULT ''",
                # Phase 4: VLAN + interface enhancements
                "ALTER TABLE interfaces ADD COLUMN vlan_id INTEGER DEFAULT 0",
                "ALTER TABLE vlans ADD COLUMN description TEXT DEFAULT ''",
                "ALTER TABLE vlans ADD COLUMN vrf_id TEXT DEFAULT 'default'",
                "ALTER TABLE vlans ADD COLUMN site_id TEXT DEFAULT ''",
                "ALTER TABLE vlans ADD COLUMN subnet_ids TEXT DEFAULT '[]'",
                # Phase 6: Discovery confidence
                "ALTER TABLE discovery_candidates ADD COLUMN confidence_score REAL DEFAULT 0.5",
                # Phase 1: Migration — remove eagerly-materialized available rows
                "DELETE FROM ip_addresses WHERE status = 'available' AND ip_type = 'static'",
            ]
            for sql in migrations:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                        import logging
                        logging.getLogger(__name__).warning("Migration failed: %s — %s", sql, e)
            # Seed default VRF
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO vrfs (id, name, is_default) VALUES ('default', 'default', 1)"
                )
            except sqlite3.OperationalError:
                pass
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
        self._invalidate_cache("list_devices")

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

    def list_devices(self, offset: int = 0, limit: int | None = None) -> list[Device]:
        # Only use cache for the full unfiltered list (no offset/limit)
        use_cache = offset == 0 and limit is None
        if use_cache:
            cache_key = "list_devices"
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        conn = self._conn()
        try:
            if limit is not None:
                rows = conn.execute(
                    "SELECT * FROM devices LIMIT ? OFFSET ?", (limit, offset)
                ).fetchall()
            else:
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
            if use_cache:
                self._cache[cache_key] = results
            return results
        finally:
            conn.close()

    def count_devices(self) -> int:
        """Return total number of devices."""
        conn = self._conn()
        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM devices").fetchone()
            return row["cnt"]
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
        self._invalidate_cache("list_devices", f"list_interfaces:{device_id}", "list_device_statuses")

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
        self._invalidate_cache("list_devices")
        return self.get_device(device_id)

    # ── Subnet CRUD ──
    def _validate_parent_subnet(self, subnet_id: str, parent_subnet_id: str) -> None:
        """Validate parent_subnet_id exists and doesn't create a cycle."""
        if not parent_subnet_id:
            return
        # Can't be own parent
        if parent_subnet_id == subnet_id:
            raise ValueError(f"Subnet cannot be its own parent: {subnet_id}")
        # Parent must exist
        conn = self._conn()
        try:
            parent = conn.execute("SELECT id, parent_subnet_id FROM subnets WHERE id=?", (parent_subnet_id,)).fetchone()
            if not parent:
                raise ValueError(f"Parent subnet not found: {parent_subnet_id}")
            # Check for circular reference (walk up the chain)
            visited = {subnet_id}
            current = parent_subnet_id
            while current:
                if current in visited:
                    raise ValueError(f"Circular parent chain detected involving: {current}")
                visited.add(current)
                row = conn.execute("SELECT parent_subnet_id FROM subnets WHERE id=?", (current,)).fetchone()
                current = row["parent_subnet_id"] if row and row["parent_subnet_id"] else ""
        finally:
            conn.close()

    def _validate_no_vrf_overlap(self, subnet: Subnet) -> None:
        """Prevent overlapping CIDRs within the same VRF (supernet/subnet relationships allowed)."""
        import ipaddress as _ipaddress
        conn = self._conn()
        try:
            siblings = conn.execute(
                "SELECT id, cidr FROM subnets WHERE vrf_id=? AND id!=?",
                (subnet.vrf_id, subnet.id)
            ).fetchall()
            new_net = _ipaddress.ip_network(subnet.cidr, strict=False)
            for row in siblings:
                if subnet.parent_subnet_id == row["id"]:
                    continue
                existing = _ipaddress.ip_network(row["cidr"], strict=False)
                if new_net.overlaps(existing) and not new_net.supernet_of(existing) and not existing.supernet_of(new_net):
                    raise ValueError(f"CIDR {subnet.cidr} overlaps with {row['cidr']} in VRF {subnet.vrf_id}")
        finally:
            conn.close()

    def add_subnet(self, subnet: Subnet) -> None:
        if subnet.parent_subnet_id:
            self._validate_parent_subnet(subnet.id, subnet.parent_subnet_id)
        self._validate_no_vrf_overlap(subnet)
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO subnets
                   (id, cidr, vlan_id, zone_id, gateway_ip, description, site,
                    parent_subnet_id, region, environment, ip_version,
                    vpc_id, cloud_provider, vrf_id, subnet_role, address_block_id, site_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (subnet.id, subnet.cidr, subnet.vlan_id, subnet.zone_id,
                 subnet.gateway_ip, subnet.description, subnet.site,
                 subnet.parent_subnet_id, subnet.region, subnet.environment,
                 subnet.ip_version, subnet.vpc_id, subnet.cloud_provider,
                 subnet.vrf_id, subnet.subnet_role, subnet.address_block_id, subnet.site_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_subnet(self, subnet_id: str) -> Optional[Subnet]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM subnets WHERE id=?", (subnet_id,)).fetchone()
            return Subnet(**dict(row)) if row else None
        finally:
            conn.close()

    def list_subnets(self) -> list[Subnet]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM subnets").fetchall()
            return [Subnet(**dict(r)) for r in rows]
        finally:
            conn.close()

    def update_subnet(self, subnet_id: str, **kwargs) -> Optional[Subnet]:
        existing = self.get_subnet(subnet_id)
        if not existing:
            return None
        data = existing.model_dump()
        data.update({k: v for k, v in kwargs.items() if k != "id"})
        # Validate parent before updating
        new_parent = data.get("parent_subnet_id", "")
        if new_parent and new_parent != existing.parent_subnet_id:
            self._validate_parent_subnet(subnet_id, new_parent)
        updated = Subnet(**data)
        # Skip validation again in add_subnet since we just validated
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO subnets
                   (id, cidr, vlan_id, zone_id, gateway_ip, description, site,
                    parent_subnet_id, region, environment, ip_version,
                    vpc_id, cloud_provider, vrf_id, subnet_role, address_block_id, site_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (updated.id, updated.cidr, updated.vlan_id, updated.zone_id,
                 updated.gateway_ip, updated.description, updated.site,
                 updated.parent_subnet_id, updated.region, updated.environment,
                 updated.ip_version, updated.vpc_id, updated.cloud_provider,
                 updated.vrf_id, updated.subnet_role, updated.address_block_id, updated.site_id),
            )
            conn.commit()
        finally:
            conn.close()
        return updated

    def delete_subnet(self, subnet_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM subnets WHERE id=?", (subnet_id,))
            conn.commit()
        finally:
            conn.close()

    def get_subnet_children(self, parent_id: str) -> list[Subnet]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM subnets WHERE parent_subnet_id=?", (parent_id,)
            ).fetchall()
            return [Subnet(**dict(r)) for r in rows]
        finally:
            conn.close()

    def get_subnet_tree(self) -> list[dict]:
        """Build hierarchical tree: Region → Site → VRF → AddressBlock → Subnet.
        Falls back to legacy region→zone grouping for subnets without new hierarchy fields.
        """
        subnets = self.list_subnets()
        regions = self.list_regions()
        sites = self.list_sites()
        vrfs = self.list_vrfs()
        blocks = self.list_address_blocks()

        # Pre-compute utilization for all subnets
        util_cache: dict[str, dict] = {}
        for s in subnets:
            util_cache[s.id] = self.get_subnet_utilization(s.id)

        # Build subnet nodes
        subnet_by_id: dict[str, dict] = {}
        for s in subnets:
            subnet_by_id[s.id] = {
                "id": s.id,
                "label": s.description or s.cidr,
                "type": "subnet",
                "cidr": s.cidr,
                "utilization_pct": util_cache[s.id].get("utilization_pct", 0),
                "subnet_role": s.subnet_role,
                "children": [],
                "_parent": s.parent_subnet_id,
                "_vrf_id": s.vrf_id or "default",
                "_block_id": s.address_block_id,
                "_site_id": s.site_id,
                "_region": s.region or s.site or "",
                "_zone": s.zone_id or "",
            }

        # Nest child subnets under parents
        top_level: list[dict] = []
        for sid, node in subnet_by_id.items():
            parent_id = node["_parent"]
            if parent_id and parent_id in subnet_by_id:
                subnet_by_id[parent_id]["children"].append(node)
            else:
                top_level.append(node)

        def _clean(node: dict) -> dict:
            for k in list(node.keys()):
                if k.startswith("_"):
                    del node[k]
            for child in node.get("children", []):
                _clean(child)
            return node

        # Group by block → VRF → site → region
        block_subnets: dict[str, list[dict]] = {}
        vrf_subnets: dict[str, list[dict]] = {}
        orphan_subnets: list[dict] = []

        for node in top_level:
            block_id = node["_block_id"]
            vrf_id = node["_vrf_id"]
            if block_id:
                block_subnets.setdefault(block_id, []).append(node)
            elif vrf_id and vrf_id != "default":
                vrf_subnets.setdefault(vrf_id, []).append(node)
            else:
                orphan_subnets.append(node)

        # Build block nodes
        block_nodes: dict[str, dict] = {}
        for b in blocks:
            block_util = self.get_address_block_utilization(b.id)
            block_nodes[b.id] = {
                "id": b.id,
                "label": b.name or b.cidr,
                "type": "address_block",
                "cidr": b.cidr,
                "utilization_pct": block_util.get("utilization_pct", 0),
                "children": [_clean(n) for n in block_subnets.get(b.id, [])],
                "_vrf_id": b.vrf_id or "default",
                "_site_id": b.site_id,
            }

        # Build VRF nodes
        vrf_nodes: dict[str, dict] = {}
        for v in vrfs:
            vrf_children = []
            # Add blocks belonging to this VRF
            for bid, bnode in block_nodes.items():
                if bnode["_vrf_id"] == v.id:
                    vrf_children.append(_clean(bnode))
            # Add direct subnets belonging to this VRF
            for sn in vrf_subnets.get(v.id, []):
                vrf_children.append(_clean(sn))
            if vrf_children or v.id == "default":
                vrf_nodes[v.id] = {
                    "id": v.id,
                    "label": v.name,
                    "type": "vrf",
                    "children": vrf_children,
                }

        # Add orphan subnets under default VRF
        if "default" in vrf_nodes:
            for sn in orphan_subnets:
                vrf_nodes["default"]["children"].append(_clean(sn))
        elif orphan_subnets:
            vrf_nodes["default"] = {
                "id": "default",
                "label": "default",
                "type": "vrf",
                "children": [_clean(sn) for sn in orphan_subnets],
            }

        # Build site nodes
        site_nodes: dict[str, dict] = {}
        for s in sites:
            site_nodes[s.id] = {
                "id": s.id,
                "label": s.name,
                "type": "site",
                "site_type": s.site_type,
                "children": [],
            }

        # Ensure a "default" site exists when no sites are created
        if not sites:
            site_nodes["default-site"] = {
                "id": "default-site",
                "label": "default",
                "type": "site",
                "site_type": "datacenter",
                "children": [],
            }

        # Assign VRF nodes to sites (use block model data, not cleaned nodes)
        assigned_vrfs: set[str] = set()
        for b in blocks:
            sid = b.site_id
            if sid and sid in site_nodes and b.vrf_id in vrf_nodes and b.vrf_id not in assigned_vrfs:
                site_nodes[sid]["children"].append(vrf_nodes[b.vrf_id])
                assigned_vrfs.add(b.vrf_id)

        # Place unassigned VRFs under default site
        default_site_id = "default-site" if not sites else None
        for vid, vnode in vrf_nodes.items():
            if vid not in assigned_vrfs and vnode["children"]:
                if default_site_id and default_site_id in site_nodes:
                    site_nodes[default_site_id]["children"].append(vnode)
                    assigned_vrfs.add(vid)

        # Build region nodes
        region_nodes: dict[str, dict] = {}
        for r in regions:
            region_nodes[r.id] = {
                "id": r.id,
                "label": r.name,
                "type": "region",
                "children": [],
            }

        # Assign sites to regions
        assigned_sites: set[str] = set()
        for s in sites:
            if s.region_id and s.region_id in region_nodes:
                region_nodes[s.region_id]["children"].append(site_nodes[s.id])
                assigned_sites.add(s.id)

        # If default site exists and there are regions, assign it to the first region
        if default_site_id and default_site_id in site_nodes and site_nodes[default_site_id]["children"]:
            if regions:
                first_region_id = regions[0].id
                region_nodes[first_region_id]["children"].append(site_nodes[default_site_id])
                assigned_sites.add(default_site_id)

        # Build children for Global root
        global_children: list[dict] = list(region_nodes.values())

        # Add unassigned sites (including default if no regions exist)
        for sid, snode in site_nodes.items():
            if sid not in assigned_sites and snode["children"]:
                global_children.append(snode)

        # Add unassigned VRFs (not linked to any site)
        for vid, vnode in vrf_nodes.items():
            if vid not in assigned_vrfs and vnode["children"]:
                global_children.append(vnode)

        # If no hierarchy entities exist, fall back to legacy grouping
        if not regions and not sites and not blocks:
            legacy_tree: dict[str, dict[str, list[dict]]] = {}
            for node in top_level:
                region = node.get("_region") or "default"
                zone = node.get("_zone") or "default"
                legacy_tree.setdefault(region, {}).setdefault(zone, []).append(node)
            global_children = []
            for region_name, zones in legacy_tree.items():
                zone_nodes_list = []
                for zone_name, snodes in zones.items():
                    zone_nodes_list.append({
                        "id": f"zone-{zone_name}",
                        "label": zone_name,
                        "type": "zone",
                        "children": [_clean(n) for n in snodes],
                    })
                global_children.append({
                    "id": f"region-{region_name}",
                    "label": region_name,
                    "type": "region",
                    "children": zone_nodes_list,
                })

        # Wrap everything under a Global root node
        global_root = {
            "id": "global",
            "label": "Global",
            "type": "global",
            "children": global_children,
        }

        return [global_root]

    # ── IP Address CRUD ──
    def add_ip_address(self, ip: IPAddress) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO ip_addresses
                   (id, address, subnet_id, status, ip_type, assigned_device_id,
                    assigned_interface_id, hostname, mac_address, vendor,
                    description, last_seen, created_at,
                    owner_team, application, environment, discovery_source, confidence_score)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ip.id, ip.address, ip.subnet_id, ip.status, ip.ip_type,
                 ip.assigned_device_id, ip.assigned_interface_id,
                 ip.hostname, ip.mac_address, ip.vendor,
                 ip.description, ip.last_seen, ip.created_at,
                 ip.owner_team, ip.application, ip.environment,
                 ip.discovery_source, ip.confidence_score),
            )
            conn.commit()
        finally:
            conn.close()

    def get_ip_address(self, ip_id: str) -> Optional[IPAddress]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM ip_addresses WHERE id=?", (ip_id,)).fetchone()
            return IPAddress(**dict(row)) if row else None
        finally:
            conn.close()

    def get_ip_by_address(self, address: str) -> Optional[IPAddress]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM ip_addresses WHERE address=?", (address,)).fetchone()
            return IPAddress(**dict(row)) if row else None
        finally:
            conn.close()

    def list_ip_addresses(self, subnet_id: Optional[str] = None,
                          status: Optional[str] = None,
                          search: Optional[str] = None,
                          offset: int = 0, limit: int = 0) -> dict:
        conn = self._conn()
        try:
            sql = "SELECT * FROM ip_addresses WHERE 1=1"
            count_sql = "SELECT COUNT(*) as total FROM ip_addresses WHERE 1=1"
            params: list = []
            count_params: list = []
            if subnet_id:
                sql += " AND subnet_id=?"
                count_sql += " AND subnet_id=?"
                params.append(subnet_id)
                count_params.append(subnet_id)
            if status:
                sql += " AND status=?"
                count_sql += " AND status=?"
                params.append(status)
                count_params.append(status)
            if search:
                sql += " AND (address LIKE ? OR hostname LIKE ? OR description LIKE ?)"
                count_sql += " AND (address LIKE ? OR hostname LIKE ? OR description LIKE ?)"
                params.extend([f"%{search}%"] * 3)
                count_params.extend([f"%{search}%"] * 3)
            total = conn.execute(count_sql, count_params).fetchone()["total"]
            sql += " ORDER BY address"
            if limit > 0:
                sql += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            rows = conn.execute(sql, params).fetchall()
            return {"ips": [IPAddress(**dict(r)) for r in rows], "total": total}
        finally:
            conn.close()

    def update_ip_status(self, ip_id: str, status: str,
                         device_id: str = "", interface_id: str = "") -> Optional[IPAddress]:
        conn = self._conn()
        try:
            # Read old state within same connection
            old_row = conn.execute("SELECT * FROM ip_addresses WHERE id=?", (ip_id,)).fetchone()
            if not old_row:
                return None
            old_status = old_row["status"]
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """UPDATE ip_addresses SET status=?, assigned_device_id=?,
                   assigned_interface_id=?, last_seen=? WHERE id=?""",
                (status, device_id, interface_id, now, ip_id),
            )
            # Audit log within same transaction
            try:
                conn.execute(
                    """INSERT INTO ip_audit_log
                       (ip_id, address, action, old_status, new_status, device_id, details)
                       VALUES (?,?,?,?,?,?,?)""",
                    (ip_id, old_row["address"], status, old_status, status, device_id, ""),
                )
            except Exception:
                pass
            conn.commit()
            # Read result
            result_row = conn.execute("SELECT * FROM ip_addresses WHERE id=?", (ip_id,)).fetchone()
            return IPAddress(**dict(result_row)) if result_row else None
        finally:
            conn.close()

    def update_ip_address(self, ip_id: str, **kwargs) -> Optional[IPAddress]:
        existing = self.get_ip_address(ip_id)
        if not existing:
            return None
        data = existing.model_dump()
        data.update({k: v for k, v in kwargs.items() if k != "id"})
        updated = IPAddress(**data)
        self.add_ip_address(updated)
        return updated

    def delete_ip_address(self, ip_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM ip_audit_log WHERE ip_id=?", (ip_id,))
            conn.execute("DELETE FROM ip_addresses WHERE id=?", (ip_id,))
            conn.commit()
        finally:
            conn.close()

    def bulk_create_ip_addresses(self, ips: list[IPAddress]) -> int:
        if not ips:
            return 0
        conn = self._conn()
        try:
            conn.executemany(
                """INSERT OR IGNORE INTO ip_addresses
                   (id, address, subnet_id, status, ip_type, assigned_device_id,
                    assigned_interface_id, hostname, mac_address, vendor,
                    description, last_seen, created_at,
                    owner_team, application, environment, discovery_source, confidence_score)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(ip.id, ip.address, ip.subnet_id, ip.status, ip.ip_type,
                  ip.assigned_device_id, ip.assigned_interface_id,
                  ip.hostname, ip.mac_address, ip.vendor,
                  ip.description, ip.last_seen, ip.created_at,
                  ip.owner_team, ip.application, ip.environment,
                  ip.discovery_source, ip.confidence_score)
                 for ip in ips],
            )
            created = conn.total_changes
            conn.commit()
            return created
        finally:
            conn.close()

    def get_subnet_utilization(self, subnet_id: str) -> dict:
        """Compute utilization dynamically from CIDR host count (lazy allocation)."""
        import ipaddress as _ipaddress
        conn = self._conn()
        try:
            subnet_row = conn.execute("SELECT cidr, gateway_ip FROM subnets WHERE id=?", (subnet_id,)).fetchone()
            if not subnet_row:
                return {"total": 0, "available": 0, "assigned": 0, "reserved": 0, "deprecated": 0, "utilization_pct": 0}
            net = _ipaddress.ip_network(subnet_row["cidr"], strict=False)
            total_hosts = max(net.num_addresses - 2, 0)  # exclude network + broadcast
            if net.prefixlen >= 31:
                total_hosts = net.num_addresses  # /31 and /32 use all addresses
            # Count IP records by status (only assigned/reserved/deprecated/gateway rows exist)
            row = conn.execute(
                """SELECT
                   SUM(CASE WHEN status='assigned' THEN 1 ELSE 0 END) as assigned,
                   SUM(CASE WHEN status='reserved' THEN 1 ELSE 0 END) as reserved,
                   SUM(CASE WHEN status='deprecated' THEN 1 ELSE 0 END) as deprecated,
                   SUM(CASE WHEN ip_type='gateway' THEN 1 ELSE 0 END) as gateway_count
                   FROM ip_addresses WHERE subnet_id=?""",
                (subnet_id,),
            ).fetchone()
            assigned = row["assigned"] or 0
            reserved = row["reserved"] or 0
            deprecated = row["deprecated"] or 0
            gateway_count = row["gateway_count"] or 0
            # Count reserved range IPs
            reserved_range_ips = 0
            try:
                for rr in conn.execute("SELECT start_ip, end_ip FROM reserved_ranges WHERE subnet_id=?", (subnet_id,)).fetchall():
                    start = int(_ipaddress.ip_address(rr["start_ip"]))
                    end = int(_ipaddress.ip_address(rr["end_ip"]))
                    reserved_range_ips += end - start + 1
            except Exception:
                pass
            used = assigned + reserved + deprecated + gateway_count + reserved_range_ips
            available = max(total_hosts - used, 0)
            pct = round((used / total_hosts) * 100, 1) if total_hosts > 0 else 0
            return {
                "total": total_hosts,
                "available": available,
                "assigned": assigned,
                "reserved": reserved + reserved_range_ips,
                "deprecated": deprecated,
                "utilization_pct": pct,
            }
        finally:
            conn.close()

    def get_ipam_stats(self) -> dict:
        """Compute global IPAM stats from subnet CIDRs (lazy allocation)."""
        import ipaddress as _ipaddress
        conn = self._conn()
        try:
            # Compute total IPs from subnet CIDRs
            subnets = conn.execute("SELECT cidr FROM subnets").fetchall()
            total_ips = 0
            for s in subnets:
                try:
                    net = _ipaddress.ip_network(s["cidr"], strict=False)
                    hosts = max(net.num_addresses - 2, 0)
                    if net.prefixlen >= 31:
                        hosts = net.num_addresses
                    total_ips += hosts
                except ValueError:
                    pass
            subnet_count = len(subnets)
            # Count actual IP records by status
            row = conn.execute(
                """SELECT
                   SUM(CASE WHEN status='assigned' THEN 1 ELSE 0 END) as assigned,
                   SUM(CASE WHEN status='reserved' THEN 1 ELSE 0 END) as reserved,
                   SUM(CASE WHEN status='deprecated' THEN 1 ELSE 0 END) as deprecated
                   FROM ip_addresses""",
            ).fetchone()
            assigned = row["assigned"] or 0
            reserved = row["reserved"] or 0
            deprecated = row["deprecated"] or 0
            used = assigned + reserved + deprecated
            available = max(total_ips - used, 0)
            pct = round((used / total_ips) * 100, 1) if total_ips > 0 else 0
            return {
                "total_subnets": subnet_count,
                "total_ips": total_ips,
                "assigned_ips": assigned,
                "available_ips": available,
                "reserved_ips": reserved,
                "deprecated_ips": deprecated,
                "overall_utilization_pct": pct,
            }
        finally:
            conn.close()

    # ── IP Audit Log ──
    def log_ip_event(self, ip_id: str, address: str, action: str,
                     old_status: str = "", new_status: str = "",
                     device_id: str = "", details: str = "") -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO ip_audit_log
                   (ip_id, address, action, old_status, new_status, device_id, details)
                   VALUES (?,?,?,?,?,?,?)""",
                (ip_id, address, action, old_status, new_status, device_id, details),
            )
            conn.commit()
        except Exception:
            pass  # Audit logging should never break main operations
        finally:
            conn.close()

    def get_ip_audit_log(self, ip_id: str = "", limit: int = 50) -> list[dict]:
        conn = self._conn()
        try:
            if ip_id:
                rows = conn.execute(
                    "SELECT * FROM ip_audit_log WHERE ip_id=? ORDER BY timestamp DESC LIMIT ?",
                    (ip_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ip_audit_log ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def bulk_update_ip_status(self, ip_ids: list[str], status: str,
                              device_id: str = "") -> int:
        """Update status for multiple IPs at once. Returns count updated."""
        if not ip_ids:
            return 0
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            placeholders = ",".join("?" for _ in ip_ids)
            # Log old statuses first
            rows = conn.execute(
                f"SELECT id, address, status FROM ip_addresses WHERE id IN ({placeholders})",
                ip_ids,
            ).fetchall()
            cur = conn.execute(
                f"""UPDATE ip_addresses SET status=?, assigned_device_id=?, last_seen=?
                    WHERE id IN ({placeholders})""",
                [status, device_id, now] + ip_ids,
            )
            updated = cur.rowcount
            conn.commit()
            # Audit log each change
            for r in rows:
                try:
                    conn.execute(
                        """INSERT INTO ip_audit_log
                           (ip_id, address, action, old_status, new_status, device_id, details)
                           VALUES (?,?,?,?,?,?,?)""",
                        (r["id"], r["address"], f"bulk_{status}", r["status"],
                         status, device_id, f"Bulk update {len(ip_ids)} IPs"),
                    )
                except Exception:
                    pass
            conn.commit()
            return updated
        finally:
            conn.close()

    def search_ips_global(self, query: str, limit: int = 50) -> list[dict]:
        """Global search across all IPs — search by address, hostname, MAC, vendor, or description."""
        conn = self._conn()
        try:
            q = f"%{query}%"
            rows = conn.execute(
                """SELECT ip.*, s.cidr as subnet_cidr, s.region as subnet_region
                   FROM ip_addresses ip
                   LEFT JOIN subnets s ON ip.subnet_id = s.id
                   WHERE ip.address LIKE ? OR ip.hostname LIKE ?
                   OR ip.mac_address LIKE ? OR ip.vendor LIKE ?
                   OR ip.description LIKE ?
                   ORDER BY ip.address LIMIT ?""",
                (q, q, q, q, q, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def detect_ip_conflicts(self) -> list[dict]:
        """Find IP addresses that appear in multiple subnets (conflicts)."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT address, COUNT(*) as cnt,
                   GROUP_CONCAT(subnet_id, ',') as subnet_ids,
                   GROUP_CONCAT(status, ',') as statuses
                   FROM ip_addresses
                   WHERE status != 'deprecated'
                   GROUP BY address HAVING cnt > 1
                   ORDER BY cnt DESC""",
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def get_next_available_ip(self, subnet_id: str) -> Optional[str]:
        """Find the first available IP using free_ranges (O(1) lookup).
        Returns the IP address string, or None if no space."""
        import ipaddress as _ipaddress
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM free_ranges WHERE subnet_id=? ORDER BY start_ip LIMIT 1",
                (subnet_id,),
            ).fetchone()
            if row:
                return row["start_ip"]
            # Fallback: compute from CIDR if no free_ranges exist yet
            subnet_row = conn.execute("SELECT cidr, gateway_ip FROM subnets WHERE id=?", (subnet_id,)).fetchone()
            if not subnet_row:
                return None
            net = _ipaddress.ip_network(subnet_row["cidr"], strict=False)
            assigned = set()
            for r in conn.execute("SELECT address FROM ip_addresses WHERE subnet_id=?", (subnet_id,)).fetchall():
                assigned.add(r["address"])
            for host in net.hosts():
                addr = str(host)
                if addr not in assigned:
                    return addr
            return None
        finally:
            conn.close()

    def split_subnet(self, subnet_id: str, new_prefix: int) -> list[Subnet]:
        """Split a subnet into smaller subnets with the given prefix length."""
        import ipaddress as _ipaddress
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM subnets WHERE id=?", (subnet_id,)).fetchone()
            if not row:
                return []
            subnet = Subnet(**dict(row))
            net = _ipaddress.ip_network(subnet.cidr, strict=False)
            if new_prefix <= net.prefixlen:
                return []
            try:
                sub_nets = list(net.subnets(new_prefix=new_prefix))
            except ValueError:
                return []
            created: list[Subnet] = []
            for i, sn in enumerate(sub_nets):
                hosts = list(sn.hosts())
                gw = str(hosts[0]) if hosts else ""
                new_sub = Subnet(
                    id=f"{subnet_id}-split-{i}",
                    cidr=str(sn),
                    vlan_id=subnet.vlan_id,
                    zone_id=subnet.zone_id,
                    gateway_ip=gw,
                    description=f"{subnet.description} (split {i+1}/{len(sub_nets)})" if subnet.description else str(sn),
                    site=subnet.site,
                    parent_subnet_id=subnet_id,
                    region=subnet.region,
                    environment=subnet.environment,
                    ip_version=subnet.ip_version,
                    vpc_id=subnet.vpc_id,
                    cloud_provider=subnet.cloud_provider,
                    vrf_id=subnet.vrf_id,
                    subnet_role=subnet.subnet_role,
                    address_block_id=subnet.address_block_id,
                    site_id=subnet.site_id,
                )
                conn.execute(
                    """INSERT OR REPLACE INTO subnets
                       (id, cidr, vlan_id, zone_id, gateway_ip, description, site,
                        parent_subnet_id, region, environment, ip_version,
                        vpc_id, cloud_provider, vrf_id, subnet_role, address_block_id, site_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (new_sub.id, new_sub.cidr, new_sub.vlan_id, new_sub.zone_id,
                     new_sub.gateway_ip, new_sub.description, new_sub.site,
                     new_sub.parent_subnet_id, new_sub.region, new_sub.environment,
                     new_sub.ip_version, new_sub.vpc_id, new_sub.cloud_provider,
                     new_sub.vrf_id, new_sub.subnet_role, new_sub.address_block_id, new_sub.site_id),
                )
                created.append(new_sub)
            conn.commit()
            return created
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def merge_subnets(self, subnet_ids: list[str]) -> Optional[Subnet]:
        """Merge subnets into their supernet if they form a complete set."""
        import ipaddress as _ipaddress
        if len(subnet_ids) < 2:
            return None
        subnets = [self.get_subnet(sid) for sid in subnet_ids]
        subnets = [s for s in subnets if s is not None]
        if len(subnets) < 2:
            return None
        nets = [_ipaddress.ip_network(s.cidr, strict=False) for s in subnets]
        try:
            collapsed = list(_ipaddress.collapse_addresses(nets))
        except Exception:
            return None
        if len(collapsed) != 1:
            return None  # Can't merge into a single supernet
        supernet = collapsed[0]
        base = subnets[0]
        merged = Subnet(
            id=f"subnet-merged-{str(supernet).replace('/', '-')}",
            cidr=str(supernet),
            vlan_id=base.vlan_id,
            zone_id=base.zone_id,
            gateway_ip=str(list(supernet.hosts())[0]) if list(supernet.hosts()) else "",
            description=f"Merged from {len(subnets)} subnets",
            site=base.site,
            parent_subnet_id=base.parent_subnet_id,
            region=base.region,
            environment=base.environment,
            ip_version=base.ip_version,
            vpc_id=base.vpc_id,
            cloud_provider=base.cloud_provider,
        )
        self.add_subnet(merged)
        # Re-parent old IPs to merged subnet
        conn = self._conn()
        try:
            placeholders = ",".join("?" for _ in subnet_ids)
            conn.execute(
                f"UPDATE ip_addresses SET subnet_id=? WHERE subnet_id IN ({placeholders})",
                [merged.id] + subnet_ids,
            )
            conn.commit()
        finally:
            conn.close()
        # Delete old subnets
        for sid in subnet_ids:
            self.delete_subnet(sid)
        return merged

    def get_available_ranges(self, parent_subnet_id: str) -> list[dict]:
        """Compute available (unallocated) IP ranges within a parent subnet.
        Returns list of {cidr, start_ip, end_ip, host_count}.
        """
        import ipaddress as _ipaddress
        parent = self.get_subnet(parent_subnet_id)
        if not parent:
            return []
        parent_net = _ipaddress.ip_network(parent.cidr, strict=False)
        children = self.get_subnet_children(parent_subnet_id)
        child_nets = []
        for c in children:
            try:
                child_nets.append(_ipaddress.ip_network(c.cidr, strict=False))
            except ValueError:
                continue
        # Sort child networks by start address
        child_nets.sort(key=lambda n: int(n.network_address))

        # Find gaps
        available = []
        current = int(parent_net.network_address)
        parent_end = int(parent_net.broadcast_address)

        for child in child_nets:
            child_start = int(child.network_address)
            child_end = int(child.broadcast_address)
            if current < child_start:
                # There's a gap before this child
                gap_start = _ipaddress.ip_address(current)
                gap_end = _ipaddress.ip_address(child_start - 1)
                # Try to express as CIDR(s)
                gap_cidrs = list(_ipaddress.summarize_address_range(gap_start, gap_end))
                for gc in gap_cidrs:
                    available.append({
                        "cidr": str(gc),
                        "start_ip": str(gc.network_address),
                        "end_ip": str(gc.broadcast_address),
                        "host_count": gc.num_addresses,
                    })
            current = max(current, child_end + 1)

        # Gap after last child
        if current <= parent_end:
            gap_start = _ipaddress.ip_address(current)
            gap_end = _ipaddress.ip_address(parent_end)
            gap_cidrs = list(_ipaddress.summarize_address_range(gap_start, gap_end))
            for gc in gap_cidrs:
                available.append({
                    "cidr": str(gc),
                    "start_ip": str(gc.network_address),
                    "end_ip": str(gc.broadcast_address),
                    "host_count": gc.num_addresses,
                })

        return available

    # ── DHCP Scope CRUD ──

    def add_dhcp_scope(self, scope: dict) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO dhcp_scopes
                   (id, name, scope_cidr, server_ip, subnet_id, total_leases,
                    active_leases, free_count, source, last_updated)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (scope["id"], scope["name"], scope["scope_cidr"],
                 scope.get("server_ip", ""), scope.get("subnet_id", ""),
                 scope.get("total_leases", 0), scope.get("active_leases", 0),
                 scope.get("free_count", 0), scope.get("source", "manual"),
                 scope.get("last_updated", "")),
            )
            conn.commit()
        finally:
            conn.close()

    def list_dhcp_scopes(self, subnet_id: str = "") -> list[dict]:
        conn = self._conn()
        try:
            if subnet_id:
                rows = conn.execute("SELECT * FROM dhcp_scopes WHERE subnet_id=?", (subnet_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM dhcp_scopes").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_dhcp_scope(self, scope_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM dhcp_scopes WHERE id=?", (scope_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Free Range Management (Lazy Allocation) ──

    def init_free_ranges(self, subnet_id: str, cidr: str, gateway_ip: str = "") -> None:
        """Create initial free range(s) for a subnet."""
        import ipaddress as _ipaddress
        net = _ipaddress.ip_network(cidr, strict=False)
        hosts = list(net.hosts())
        if not hosts:
            return
        first_host = str(hosts[0])
        last_host = str(hosts[-1])
        conn = self._conn()
        try:
            # Clear existing free ranges for this subnet
            conn.execute("DELETE FROM free_ranges WHERE subnet_id=?", (subnet_id,))
            if gateway_ip and first_host <= gateway_ip <= last_host:
                gw_int = int(_ipaddress.ip_address(gateway_ip))
                first_int = int(_ipaddress.ip_address(first_host))
                last_int = int(_ipaddress.ip_address(last_host))
                # Split around gateway
                if gw_int > first_int:
                    before_end = str(_ipaddress.ip_address(gw_int - 1))
                    conn.execute(
                        "INSERT INTO free_ranges (id, subnet_id, start_ip, end_ip, host_count) VALUES (?,?,?,?,?)",
                        (f"fr-{subnet_id}-0", subnet_id, first_host, before_end, gw_int - first_int),
                    )
                if gw_int < last_int:
                    after_start = str(_ipaddress.ip_address(gw_int + 1))
                    conn.execute(
                        "INSERT INTO free_ranges (id, subnet_id, start_ip, end_ip, host_count) VALUES (?,?,?,?,?)",
                        (f"fr-{subnet_id}-1", subnet_id, after_start, last_host, last_int - gw_int),
                    )
            else:
                host_count = int(_ipaddress.ip_address(last_host)) - int(_ipaddress.ip_address(first_host)) + 1
                conn.execute(
                    "INSERT INTO free_ranges (id, subnet_id, start_ip, end_ip, host_count) VALUES (?,?,?,?,?)",
                    (f"fr-{subnet_id}-0", subnet_id, first_host, last_host, host_count),
                )
            conn.commit()
        finally:
            conn.close()

    def allocate_ip_from_range(self, subnet_id: str) -> Optional[str]:
        """O(1) IP allocation: take first IP from first free range."""
        import ipaddress as _ipaddress
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM free_ranges WHERE subnet_id=? ORDER BY start_ip LIMIT 1",
                (subnet_id,),
            ).fetchone()
            if not row:
                return None
            allocated_ip = row["start_ip"]
            if row["host_count"] <= 1:
                conn.execute("DELETE FROM free_ranges WHERE id=?", (row["id"],))
            else:
                new_start = str(_ipaddress.ip_address(int(_ipaddress.ip_address(allocated_ip)) + 1))
                conn.execute(
                    "UPDATE free_ranges SET start_ip=?, host_count=host_count-1 WHERE id=?",
                    (new_start, row["id"]),
                )
            conn.commit()
            return allocated_ip
        finally:
            conn.close()

    def release_ip_to_range(self, subnet_id: str, ip: str) -> None:
        """Return IP to free pool, merge adjacent ranges."""
        import ipaddress as _ipaddress
        ip_int = int(_ipaddress.ip_address(ip))
        conn = self._conn()
        try:
            # Find adjacent ranges
            before = conn.execute(
                "SELECT * FROM free_ranges WHERE subnet_id=? AND end_ip=?",
                (subnet_id, str(_ipaddress.ip_address(ip_int - 1))),
            ).fetchone()
            after = conn.execute(
                "SELECT * FROM free_ranges WHERE subnet_id=? AND start_ip=?",
                (subnet_id, str(_ipaddress.ip_address(ip_int + 1))),
            ).fetchone()
            if before and after:
                # Merge all three
                new_count = before["host_count"] + 1 + after["host_count"]
                conn.execute(
                    "UPDATE free_ranges SET end_ip=?, host_count=? WHERE id=?",
                    (after["end_ip"], new_count, before["id"]),
                )
                conn.execute("DELETE FROM free_ranges WHERE id=?", (after["id"],))
            elif before:
                conn.execute(
                    "UPDATE free_ranges SET end_ip=?, host_count=host_count+1 WHERE id=?",
                    (ip, before["id"]),
                )
            elif after:
                conn.execute(
                    "UPDATE free_ranges SET start_ip=?, host_count=host_count+1 WHERE id=?",
                    (ip, after["id"]),
                )
            else:
                import uuid as _uuid
                conn.execute(
                    "INSERT INTO free_ranges (id, subnet_id, start_ip, end_ip, host_count) VALUES (?,?,?,?,?)",
                    (f"fr-{_uuid.uuid4().hex[:8]}", subnet_id, ip, ip, 1),
                )
            conn.commit()
        finally:
            conn.close()

    def consume_from_range(self, subnet_id: str, ip: str) -> None:
        """Remove specific IP from free ranges (for assign/reserve)."""
        import ipaddress as _ipaddress
        ip_int = int(_ipaddress.ip_address(ip))
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM free_ranges WHERE subnet_id=?", (subnet_id,)
            ).fetchall()
            for row in rows:
                start_int = int(_ipaddress.ip_address(row["start_ip"]))
                end_int = int(_ipaddress.ip_address(row["end_ip"]))
                if start_int <= ip_int <= end_int:
                    conn.execute("DELETE FROM free_ranges WHERE id=?", (row["id"],))
                    import uuid as _uuid
                    if ip_int > start_int:
                        before_end = str(_ipaddress.ip_address(ip_int - 1))
                        conn.execute(
                            "INSERT INTO free_ranges (id, subnet_id, start_ip, end_ip, host_count) VALUES (?,?,?,?,?)",
                            (f"fr-{_uuid.uuid4().hex[:8]}", subnet_id, row["start_ip"], before_end, ip_int - start_int),
                        )
                    if ip_int < end_int:
                        after_start = str(_ipaddress.ip_address(ip_int + 1))
                        conn.execute(
                            "INSERT INTO free_ranges (id, subnet_id, start_ip, end_ip, host_count) VALUES (?,?,?,?,?)",
                            (f"fr-{_uuid.uuid4().hex[:8]}", subnet_id, after_start, row["end_ip"], end_int - ip_int),
                        )
                    break
            conn.commit()
        finally:
            conn.close()

    # ── Reserved Ranges CRUD ──

    def add_reserved_range(self, subnet_id: str, start_ip: str, end_ip: str,
                           reason: str = "", owner_team: str = "") -> dict:
        import uuid as _uuid
        range_id = f"rr-{_uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO reserved_ranges (id, subnet_id, start_ip, end_ip, reason, owner_team, created_at) VALUES (?,?,?,?,?,?,?)",
                (range_id, subnet_id, start_ip, end_ip, reason, owner_team, now),
            )
            conn.commit()
        finally:
            conn.close()
        return {"id": range_id, "subnet_id": subnet_id, "start_ip": start_ip, "end_ip": end_ip,
                "reason": reason, "owner_team": owner_team, "created_at": now}

    def list_reserved_ranges(self, subnet_id: str) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM reserved_ranges WHERE subnet_id=?", (subnet_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_reserved_range(self, range_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM reserved_ranges WHERE id=?", (range_id,))
            conn.commit()
        finally:
            conn.close()

    # ── VRF CRUD ──

    def add_vrf(self, vrf: VRF) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO vrfs (id, name, rd, rt_import, rt_export, description, device_ids, is_default) VALUES (?,?,?,?,?,?,?,?)",
                (vrf.id, vrf.name, vrf.rd, json.dumps(vrf.rt_import), json.dumps(vrf.rt_export),
                 vrf.description, json.dumps(vrf.device_ids), int(vrf.is_default)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_vrf(self, vrf_id: str) -> Optional[VRF]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM vrfs WHERE id=?", (vrf_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["rt_import"] = self._safe_json_loads(d.get("rt_import"))
            d["rt_export"] = self._safe_json_loads(d.get("rt_export"))
            d["device_ids"] = self._safe_json_loads(d.get("device_ids"))
            d["is_default"] = bool(d.get("is_default", 0))
            return VRF(**d)
        finally:
            conn.close()

    def list_vrfs(self) -> list[VRF]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM vrfs").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["rt_import"] = self._safe_json_loads(d.get("rt_import"))
                d["rt_export"] = self._safe_json_loads(d.get("rt_export"))
                d["device_ids"] = self._safe_json_loads(d.get("device_ids"))
                d["is_default"] = bool(d.get("is_default", 0))
                results.append(VRF(**d))
            return results
        finally:
            conn.close()

    def update_vrf(self, vrf_id: str, **kwargs) -> Optional[VRF]:
        existing = self.get_vrf(vrf_id)
        if not existing:
            return None
        data = existing.model_dump()
        data.update({k: v for k, v in kwargs.items() if k != "id"})
        updated = VRF(**data)
        self.add_vrf(updated)
        return updated

    def delete_vrf(self, vrf_id: str) -> None:
        conn = self._conn()
        try:
            # Reassign orphaned subnets to default VRF
            conn.execute("UPDATE subnets SET vrf_id='default' WHERE vrf_id=?", (vrf_id,))
            conn.execute("DELETE FROM vrfs WHERE id=? AND is_default=0", (vrf_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Region CRUD ──

    def add_region(self, region: Region) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO regions (id, name, description) VALUES (?,?,?)",
                (region.id, region.name, region.description),
            )
            conn.commit()
        finally:
            conn.close()

    def get_region(self, region_id: str) -> Optional[Region]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM regions WHERE id=?", (region_id,)).fetchone()
            return Region(**dict(row)) if row else None
        finally:
            conn.close()

    def list_regions(self) -> list[Region]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM regions").fetchall()
            return [Region(**dict(r)) for r in rows]
        finally:
            conn.close()

    def update_region(self, region_id: str, **kwargs) -> Optional[Region]:
        existing = self.get_region(region_id)
        if not existing:
            return None
        data = existing.model_dump()
        data.update({k: v for k, v in kwargs.items() if k != "id"})
        updated = Region(**data)
        self.add_region(updated)
        return updated

    def delete_region(self, region_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM regions WHERE id=?", (region_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Site CRUD ──

    def add_site(self, site: Site) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO sites (id, name, region_id, site_type, address, description) VALUES (?,?,?,?,?,?)",
                (site.id, site.name, site.region_id, site.site_type, site.address, site.description),
            )
            conn.commit()
        finally:
            conn.close()

    def get_site(self, site_id: str) -> Optional[Site]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
            return Site(**dict(row)) if row else None
        finally:
            conn.close()

    def list_sites(self) -> list[Site]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM sites").fetchall()
            return [Site(**dict(r)) for r in rows]
        finally:
            conn.close()

    def update_site(self, site_id: str, **kwargs) -> Optional[Site]:
        existing = self.get_site(site_id)
        if not existing:
            return None
        data = existing.model_dump()
        data.update({k: v for k, v in kwargs.items() if k != "id"})
        updated = Site(**data)
        self.add_site(updated)
        return updated

    def delete_site(self, site_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM sites WHERE id=?", (site_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Address Block CRUD ──

    def add_address_block(self, block: AddressBlock) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO address_blocks (id, cidr, name, vrf_id, site_id, description, rir) VALUES (?,?,?,?,?,?,?)",
                (block.id, block.cidr, block.name, block.vrf_id, block.site_id, block.description, block.rir),
            )
            conn.commit()
        finally:
            conn.close()

    def get_address_block(self, block_id: str) -> Optional[AddressBlock]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM address_blocks WHERE id=?", (block_id,)).fetchone()
            return AddressBlock(**dict(row)) if row else None
        finally:
            conn.close()

    def list_address_blocks(self) -> list[AddressBlock]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM address_blocks").fetchall()
            return [AddressBlock(**dict(r)) for r in rows]
        finally:
            conn.close()

    def delete_address_block(self, block_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM address_blocks WHERE id=?", (block_id,))
            conn.commit()
        finally:
            conn.close()

    def get_address_block_utilization(self, block_id: str) -> dict:
        """Compute utilization of an address block from its child subnets."""
        import ipaddress as _ipaddress
        block = self.get_address_block(block_id)
        if not block:
            return {"total": 0, "allocated": 0, "free": 0, "utilization_pct": 0}
        net = _ipaddress.ip_network(block.cidr, strict=False)
        total = net.num_addresses
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT cidr FROM subnets WHERE address_block_id=?", (block_id,)
            ).fetchall()
            allocated = 0
            for r in rows:
                try:
                    allocated += _ipaddress.ip_network(r["cidr"], strict=False).num_addresses
                except ValueError:
                    pass
            free = max(total - allocated, 0)
            pct = round((allocated / total) * 100, 1) if total > 0 else 0
            return {"total": total, "allocated": allocated, "free": free, "utilization_pct": pct}
        finally:
            conn.close()

    def allocate_subnet_from_block(self, block_id: str, prefix: int) -> Optional[Subnet]:
        """Auto-allocate first available subnet with given prefix from address block."""
        import ipaddress as _ipaddress
        block = self.get_address_block(block_id)
        if not block:
            return None
        block_net = _ipaddress.ip_network(block.cidr, strict=False)
        if prefix < block_net.prefixlen:
            return None
        conn = self._conn()
        try:
            existing = conn.execute(
                "SELECT cidr FROM subnets WHERE address_block_id=?", (block_id,)
            ).fetchall()
            existing_nets = []
            for r in existing:
                try:
                    existing_nets.append(_ipaddress.ip_network(r["cidr"], strict=False))
                except ValueError:
                    pass
        finally:
            conn.close()
        # Walk address space looking for non-overlapping candidate
        for candidate in block_net.subnets(new_prefix=prefix):
            overlaps = False
            for en in existing_nets:
                if candidate.overlaps(en):
                    overlaps = True
                    break
            if not overlaps:
                import uuid as _uuid
                subnet = Subnet(
                    id=f"subnet-{_uuid.uuid4().hex[:8]}",
                    cidr=str(candidate),
                    vrf_id=block.vrf_id,
                    address_block_id=block_id,
                    site_id=block.site_id,
                    gateway_ip=str(list(candidate.hosts())[0]) if list(candidate.hosts()) else "",
                )
                self.add_subnet(subnet)
                self.init_free_ranges(subnet.id, subnet.cidr, subnet.gateway_ip)
                return subnet
        return None

    # ── VLAN Enhanced CRUD ──

    def get_vlan(self, vlan_id: str) -> Optional[VLAN]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM vlans WHERE id=?", (vlan_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["trunk_ports"] = self._safe_json_loads(d.get("trunk_ports"))
            d["access_ports"] = self._safe_json_loads(d.get("access_ports"))
            d["subnet_ids"] = self._safe_json_loads(d.get("subnet_ids"))
            return VLAN(**d)
        finally:
            conn.close()

    def update_vlan(self, vlan_id: str, **kwargs) -> Optional[VLAN]:
        existing = self.get_vlan(vlan_id)
        if not existing:
            return None
        data = existing.model_dump()
        data.update({k: v for k, v in kwargs.items() if k != "id"})
        updated = VLAN(**data)
        self.add_vlan(updated)
        return updated

    def delete_vlan(self, vlan_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM vlans WHERE id=?", (vlan_id,))
            conn.commit()
        finally:
            conn.close()

    def get_vlan_interfaces(self, vlan_id: str) -> list[Interface]:
        """Get interfaces assigned to a VLAN by vlan_id column."""
        vlan = self.get_vlan(vlan_id)
        if not vlan:
            return []
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM interfaces WHERE vlan_id=?", (vlan.vlan_number,)
            ).fetchall()
            return [Interface(**dict(r)) for r in rows]
        finally:
            conn.close()

    def get_vlan_devices(self, vlan_id: str) -> list[Device]:
        """Get distinct devices that have interfaces in a VLAN."""
        interfaces = self.get_vlan_interfaces(vlan_id)
        device_ids = list(set(i.device_id for i in interfaces))
        devices = []
        for did in device_ids:
            d = self.get_device(did)
            if d:
                devices.append(d)
        return devices

    # ── Cloud Account CRUD ──

    def add_cloud_account(self, account: CloudAccount) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO cloud_accounts
                   (id, name, provider, account_id, region, credentials_ref, sync_enabled, last_sync)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (account.id, account.name, account.provider.value, account.account_id,
                 account.region, account.credentials_ref, int(account.sync_enabled), account.last_sync),
            )
            conn.commit()
        finally:
            conn.close()

    def get_cloud_account(self, account_id: str) -> Optional[CloudAccount]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM cloud_accounts WHERE id=?", (account_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["sync_enabled"] = bool(d.get("sync_enabled", 0))
            return CloudAccount(**d)
        finally:
            conn.close()

    def list_cloud_accounts(self) -> list[CloudAccount]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM cloud_accounts").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["sync_enabled"] = bool(d.get("sync_enabled", 0))
                results.append(CloudAccount(**d))
            return results
        finally:
            conn.close()

    def update_cloud_account(self, account_id: str, **kwargs) -> Optional[CloudAccount]:
        existing = self.get_cloud_account(account_id)
        if not existing:
            return None
        data = existing.model_dump()
        data.update({k: v for k, v in kwargs.items() if k != "id"})
        # Handle provider as string -> enum
        if isinstance(data.get("provider"), str):
            from .models import CloudProvider
            data["provider"] = CloudProvider(data["provider"])
        updated = CloudAccount(**data)
        self.add_cloud_account(updated)
        return updated

    def delete_cloud_account(self, account_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM cloud_interfaces WHERE cloud_account_id=?", (account_id,))
            conn.execute("DELETE FROM cloud_accounts WHERE id=?", (account_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Cloud Interface CRUD ──

    def add_cloud_interface(self, ci: CloudInterface) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO cloud_interfaces
                   (id, cloud_account_id, instance_id, instance_name, vpc_id, subnet_id,
                    security_group_ids, private_ips, public_ip, mac_address, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (ci.id, ci.cloud_account_id, ci.instance_id, ci.instance_name,
                 ci.vpc_id, ci.subnet_id, json.dumps(ci.security_group_ids),
                 json.dumps(ci.private_ips), ci.public_ip, ci.mac_address, ci.status),
            )
            conn.commit()
        finally:
            conn.close()

    def list_cloud_interfaces(self, cloud_account_id: str = "") -> list[CloudInterface]:
        conn = self._conn()
        try:
            if cloud_account_id:
                rows = conn.execute("SELECT * FROM cloud_interfaces WHERE cloud_account_id=?", (cloud_account_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM cloud_interfaces").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["security_group_ids"] = self._safe_json_loads(d.get("security_group_ids"))
                d["private_ips"] = self._safe_json_loads(d.get("private_ips"))
                results.append(CloudInterface(**d))
            return results
        finally:
            conn.close()

    # ── IP → Interface → Device → VLAN Correlation ──

    def get_ip_correlation_chain(self, ip_id: str) -> dict:
        """Build: IP → Interface → Device → VLAN → Subnet with status at each level."""
        ip = self.get_ip_address(ip_id)
        if not ip:
            return {}
        result: dict = {
            "ip": {"id": ip.id, "address": ip.address, "status": ip.status,
                   "owner_team": ip.owner_team, "application": ip.application},
            "interface": None, "device": None, "vlan": None, "subnet": None,
        }
        # Find interface
        iface = None
        if ip.assigned_interface_id:
            conn = self._conn()
            try:
                row = conn.execute("SELECT * FROM interfaces WHERE id=?", (ip.assigned_interface_id,)).fetchone()
                if row:
                    iface = Interface(**dict(row))
            finally:
                conn.close()
        if not iface:
            iface = self.find_interface_by_ip(ip.address)
        if iface:
            result["interface"] = {"id": iface.id, "name": iface.name, "status": iface.status,
                                   "vlan_id": getattr(iface, 'vlan_id', 0)}
            # Find device
            device = self.get_device(iface.device_id)
            if device:
                result["device"] = {"id": device.id, "name": device.name, "device_type": device.device_type.value}
                # Get device status
                conn = self._conn()
                try:
                    ds = conn.execute("SELECT * FROM device_status WHERE device_id=?", (device.id,)).fetchone()
                    if ds:
                        result["device"]["status"] = ds["status"]
                        result["device"]["latency_ms"] = ds["latency_ms"]
                finally:
                    conn.close()
        # Find subnet
        subnet = self.get_subnet(ip.subnet_id)
        if subnet:
            util = self.get_subnet_utilization(subnet.id)
            result["subnet"] = {"id": subnet.id, "cidr": subnet.cidr,
                                "utilization_pct": util.get("utilization_pct", 0),
                                "subnet_role": subnet.subnet_role}
            # Find VLAN
            if subnet.vlan_id:
                conn = self._conn()
                try:
                    vrow = conn.execute("SELECT * FROM vlans WHERE vlan_number=?", (subnet.vlan_id,)).fetchone()
                    if vrow:
                        result["vlan"] = {"id": vrow["id"], "vlan_number": vrow["vlan_number"], "name": vrow["name"]}
                finally:
                    conn.close()
        return result

    # ── Enhanced Tree Builder ──

    def export_ipam_csv(self) -> str:
        """Export all subnets and IPs as CSV string."""
        import io, csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "address", "subnet_cidr", "status", "ip_type", "hostname",
            "mac_address", "vendor", "device_id", "description",
            "region", "zone_id", "vlan_id", "environment", "cloud_provider",
        ])
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT ip.address, s.cidr as subnet_cidr, ip.status, ip.ip_type,
                   ip.hostname, ip.mac_address, ip.vendor, ip.assigned_device_id,
                   ip.description, s.region, s.zone_id, s.vlan_id, s.environment,
                   s.cloud_provider
                   FROM ip_addresses ip
                   LEFT JOIN subnets s ON ip.subnet_id = s.id
                   ORDER BY s.cidr, ip.address"""
            ).fetchall()
            for r in rows:
                writer.writerow([r[k] for k in [
                    "address", "subnet_cidr", "status", "ip_type", "hostname",
                    "mac_address", "vendor", "assigned_device_id", "description",
                    "region", "zone_id", "vlan_id", "environment", "cloud_provider",
                ]])
        finally:
            conn.close()
        return output.getvalue()

    def detect_dns_mismatches(self) -> list[dict]:
        """Detect IPs whose hostname doesn't match DNS watched hostnames.
        Compares ip_addresses.hostname against dns watched hostnames if configured.
        Also flags assigned IPs without hostnames.
        """
        conn = self._conn()
        try:
            # IPs that are assigned but have no hostname
            no_hostname = conn.execute(
                """SELECT ip.id, ip.address, ip.subnet_id, ip.assigned_device_id,
                   s.cidr as subnet_cidr
                   FROM ip_addresses ip
                   LEFT JOIN subnets s ON ip.subnet_id = s.id
                   WHERE ip.status = 'assigned' AND (ip.hostname = '' OR ip.hostname IS NULL)
                   LIMIT 50"""
            ).fetchall()
            results = []
            for r in no_hostname:
                results.append({
                    "type": "missing_hostname",
                    "address": r["address"],
                    "subnet_cidr": r["subnet_cidr"] or "",
                    "device_id": r["assigned_device_id"] or "",
                    "detail": "Assigned IP has no hostname/DNS record",
                })
            # Duplicate hostnames across different IPs
            dup_hostnames = conn.execute(
                """SELECT hostname, COUNT(*) as cnt,
                   GROUP_CONCAT(address, ', ') as addresses
                   FROM ip_addresses
                   WHERE hostname != '' AND status != 'deprecated'
                   GROUP BY hostname HAVING cnt > 1
                   LIMIT 50"""
            ).fetchall()
            for r in dup_hostnames:
                results.append({
                    "type": "duplicate_hostname",
                    "hostname": r["hostname"],
                    "count": r["cnt"],
                    "addresses": r["addresses"],
                    "detail": f"Hostname '{r['hostname']}' resolves to {r['cnt']} IPs",
                })
            return results
        except Exception:
            return []
        finally:
            conn.close()

    def get_capacity_forecast(self) -> list[dict]:
        """Get utilization trend data for capacity forecasting."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT s.id, s.cidr, s.region, s.environment,
                   COUNT(*) as total_ips,
                   SUM(CASE WHEN ip.status='available' THEN 1 ELSE 0 END) as available,
                   SUM(CASE WHEN ip.status='assigned' THEN 1 ELSE 0 END) as assigned,
                   SUM(CASE WHEN ip.status='reserved' THEN 1 ELSE 0 END) as reserved
                   FROM subnets s
                   LEFT JOIN ip_addresses ip ON s.id = ip.subnet_id
                   GROUP BY s.id
                   ORDER BY (CAST(SUM(CASE WHEN ip.status!='available' THEN 1 ELSE 0 END) AS REAL) /
                             NULLIF(COUNT(*), 0)) DESC"""
            ).fetchall()
            result = []
            for r in rows:
                total = r["total_ips"] or 0
                available = r["available"] or 0
                assigned = r["assigned"] or 0
                reserved = r["reserved"] or 0
                used = total - available
                pct = round((used / total) * 100, 1) if total > 0 else 0
                # Simple linear projection: if >50% used, flag as needing attention
                days_until_full = None
                if assigned > 0 and available > 0:
                    # Rough estimate based on current assignment rate
                    days_until_full = round((available / max(assigned, 1)) * 90)
                result.append({
                    "subnet_id": r["id"],
                    "cidr": r["cidr"],
                    "region": r["region"] or "",
                    "environment": r["environment"] or "",
                    "total": total,
                    "available": available,
                    "assigned": assigned,
                    "reserved": reserved,
                    "utilization_pct": pct,
                    "days_until_full": days_until_full,
                    "risk_level": "critical" if pct >= 90 else "warning" if pct >= 75 else "ok",
                })
            return result
        except Exception:
            return []
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
        self._invalidate_cache(f"list_interfaces:{iface.device_id}")

    def list_interfaces(self, device_id: Optional[str] = None) -> list[Interface]:
        cache_key = f"list_interfaces:{device_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        conn = self._conn()
        try:
            if device_id:
                rows = conn.execute("SELECT * FROM interfaces WHERE device_id=?", (device_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM interfaces").fetchall()
            results = [Interface(**dict(r)) for r in rows]
            self._cache[cache_key] = results
            return results
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
            row = conn.execute("SELECT device_id FROM interfaces WHERE id=?", (interface_id,)).fetchone()
            device_id = row["device_id"] if row else None
            # Clear IP assignments that reference this interface
            conn.execute("UPDATE ip_addresses SET assigned_interface_id='' WHERE assigned_interface_id=?", (interface_id,))
            conn.execute("DELETE FROM interfaces WHERE id=?", (interface_id,))
            conn.commit()
        finally:
            conn.close()
        if device_id:
            self._invalidate_cache(f"list_interfaces:{device_id}")

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
                """INSERT OR REPLACE INTO vlans
                   (id, vlan_number, name, trunk_ports, access_ports, site,
                    description, vrf_id, site_id, subnet_ids)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (vlan.id, vlan.vlan_number, vlan.name,
                 json.dumps(vlan.trunk_ports), json.dumps(vlan.access_ports), vlan.site,
                 vlan.description, vlan.vrf_id, vlan.site_id, json.dumps(vlan.subnet_ids)),
            )
            conn.commit()
        finally:
            conn.close()

    def list_vlans(self) -> list[VLAN]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM vlans").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["trunk_ports"] = self._safe_json_loads(d.get("trunk_ports"))
                d["access_ports"] = self._safe_json_loads(d.get("access_ports"))
                d["subnet_ids"] = self._safe_json_loads(d.get("subnet_ids"))
                results.append(VLAN(**d))
            return results
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
        self._invalidate_cache("list_device_statuses")

    def get_device_status(self, device_id: str):
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM device_status WHERE device_id=?", (device_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_device_statuses(self, offset: int = 0, limit: int | None = None) -> list:
        # Only use cache for the full unfiltered list (no offset/limit)
        use_cache = offset == 0 and limit is None
        if use_cache:
            cache_key = "list_device_statuses"
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        conn = self._conn()
        try:
            if limit is not None:
                rows = conn.execute(
                    "SELECT * FROM device_status LIMIT ? OFFSET ?", (limit, offset)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM device_status").fetchall()
            results = [dict(r) for r in rows]
            if use_cache:
                self._cache[cache_key] = results
            return results
        finally:
            conn.close()

    def count_device_statuses(self) -> int:
        """Return total number of device statuses."""
        conn = self._conn()
        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM device_status").fetchone()
            return row["cnt"]
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

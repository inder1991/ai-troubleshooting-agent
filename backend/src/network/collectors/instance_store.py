"""SQLite CRUD for DeviceInstances and DiscoveryConfigs."""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from .models import DeviceInstance, DeviceStatus, DiscoveryConfig

logger = logging.getLogger(__name__)

DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "debugduck.db"


class InstanceStore:
    """SQLite persistence for protocol-monitored devices and discovery configs."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db = str(db_path or DEFAULT_DB)
        self._ensure_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collector_devices (
                    device_id      TEXT PRIMARY KEY,
                    hostname       TEXT NOT NULL DEFAULT '',
                    management_ip  TEXT NOT NULL,
                    sys_object_id  TEXT,
                    matched_profile TEXT,
                    vendor         TEXT DEFAULT '',
                    model          TEXT DEFAULT '',
                    os_family      TEXT DEFAULT '',
                    protocols_json TEXT DEFAULT '[]',
                    vendor_adapter_id TEXT,
                    discovered     INTEGER DEFAULT 0,
                    tags_json      TEXT DEFAULT '[]',
                    ping_config_json TEXT,
                    last_collected REAL,
                    last_ping_json TEXT,
                    status         TEXT DEFAULT 'new'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS discovery_configs (
                    config_id      TEXT PRIMARY KEY,
                    cidr           TEXT NOT NULL,
                    snmp_version   TEXT DEFAULT '2c',
                    community      TEXT DEFAULT 'public',
                    v3_user        TEXT,
                    v3_auth_protocol TEXT,
                    v3_auth_key    TEXT,
                    v3_priv_protocol TEXT,
                    v3_priv_key    TEXT,
                    port           INTEGER DEFAULT 161,
                    interval_seconds INTEGER DEFAULT 300,
                    excluded_ips_json TEXT DEFAULT '[]',
                    tags_json      TEXT DEFAULT '[]',
                    ping_json      TEXT,
                    enabled        INTEGER DEFAULT 1,
                    last_scan      REAL,
                    devices_found  INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_collector_devices_ip
                ON collector_devices(management_ip)
            """)

    # ── Device CRUD ──

    def upsert_device(self, device: DeviceInstance) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO collector_devices
                    (device_id, hostname, management_ip, sys_object_id, matched_profile,
                     vendor, model, os_family, protocols_json, vendor_adapter_id,
                     discovered, tags_json, ping_config_json, last_collected,
                     last_ping_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    hostname=excluded.hostname,
                    management_ip=excluded.management_ip,
                    sys_object_id=excluded.sys_object_id,
                    matched_profile=excluded.matched_profile,
                    vendor=excluded.vendor,
                    model=excluded.model,
                    os_family=excluded.os_family,
                    protocols_json=excluded.protocols_json,
                    vendor_adapter_id=excluded.vendor_adapter_id,
                    discovered=excluded.discovered,
                    tags_json=excluded.tags_json,
                    ping_config_json=excluded.ping_config_json,
                    last_collected=excluded.last_collected,
                    last_ping_json=excluded.last_ping_json,
                    status=excluded.status
            """, (
                device.device_id, device.hostname, device.management_ip,
                device.sys_object_id, device.matched_profile,
                device.vendor, device.model, device.os_family,
                json.dumps([p.model_dump() for p in device.protocols]),
                device.vendor_adapter_id,
                1 if device.discovered else 0,
                json.dumps(device.tags),
                device.ping_config.model_dump_json() if device.ping_config else None,
                device.last_collected,
                device.last_ping.model_dump_json() if device.last_ping else None,
                device.status.value if isinstance(device.status, DeviceStatus) else device.status,
            ))

    def get_device(self, device_id: str) -> DeviceInstance | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM collector_devices WHERE device_id = ?", (device_id,)
            ).fetchone()
        return self._row_to_device(row) if row else None

    def get_device_by_ip(self, ip: str) -> DeviceInstance | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM collector_devices WHERE management_ip = ?", (ip,)
            ).fetchone()
        return self._row_to_device(row) if row else None

    def list_devices(self) -> list[DeviceInstance]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM collector_devices ORDER BY hostname").fetchall()
        return [self._row_to_device(r) for r in rows]

    def delete_device(self, device_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM collector_devices WHERE device_id = ?", (device_id,))
        return cur.rowcount > 0

    def update_device_status(self, device_id: str, status: str, last_collected: float | None = None) -> None:
        with self._conn() as conn:
            if last_collected is not None:
                conn.execute(
                    "UPDATE collector_devices SET status = ?, last_collected = ? WHERE device_id = ?",
                    (status, last_collected, device_id),
                )
            else:
                conn.execute(
                    "UPDATE collector_devices SET status = ? WHERE device_id = ?",
                    (status, device_id),
                )

    def update_device_ping(self, device_id: str, ping_json: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE collector_devices SET last_ping_json = ? WHERE device_id = ?",
                (ping_json, device_id),
            )

    # ── Discovery Config CRUD ──

    def upsert_discovery_config(self, config: DiscoveryConfig) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO discovery_configs
                    (config_id, cidr, snmp_version, community,
                     v3_user, v3_auth_protocol, v3_auth_key,
                     v3_priv_protocol, v3_priv_key, port,
                     interval_seconds, excluded_ips_json, tags_json,
                     ping_json, enabled, last_scan, devices_found)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(config_id) DO UPDATE SET
                    cidr=excluded.cidr,
                    snmp_version=excluded.snmp_version,
                    community=excluded.community,
                    v3_user=excluded.v3_user,
                    v3_auth_protocol=excluded.v3_auth_protocol,
                    v3_auth_key=excluded.v3_auth_key,
                    v3_priv_protocol=excluded.v3_priv_protocol,
                    v3_priv_key=excluded.v3_priv_key,
                    port=excluded.port,
                    interval_seconds=excluded.interval_seconds,
                    excluded_ips_json=excluded.excluded_ips_json,
                    tags_json=excluded.tags_json,
                    ping_json=excluded.ping_json,
                    enabled=excluded.enabled,
                    last_scan=excluded.last_scan,
                    devices_found=excluded.devices_found
            """, (
                config.config_id, config.cidr, config.snmp_version.value,
                config.community, config.v3_user,
                config.v3_auth_protocol.value if config.v3_auth_protocol else None,
                config.v3_auth_key,
                config.v3_priv_protocol.value if config.v3_priv_protocol else None,
                config.v3_priv_key, config.port,
                config.interval_seconds, json.dumps(config.excluded_ips),
                json.dumps(config.tags), config.ping.model_dump_json(),
                1 if config.enabled else 0, config.last_scan, config.devices_found,
            ))

    def get_discovery_config(self, config_id: str) -> DiscoveryConfig | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM discovery_configs WHERE config_id = ?", (config_id,)
            ).fetchone()
        return self._row_to_config(row) if row else None

    def list_discovery_configs(self) -> list[DiscoveryConfig]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM discovery_configs ORDER BY cidr").fetchall()
        return [self._row_to_config(r) for r in rows]

    def delete_discovery_config(self, config_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM discovery_configs WHERE config_id = ?", (config_id,))
        return cur.rowcount > 0

    # ── Helpers ──

    @staticmethod
    def _row_to_device(row: sqlite3.Row) -> DeviceInstance:
        from .models import PingConfig, PingResult, ProtocolConfig

        protocols = []
        try:
            for p in json.loads(row["protocols_json"] or "[]"):
                protocols.append(ProtocolConfig(**p))
        except Exception:
            pass

        ping_config = None
        if row["ping_config_json"]:
            try:
                ping_config = PingConfig.model_validate_json(row["ping_config_json"])
            except Exception:
                pass

        last_ping = None
        if row["last_ping_json"]:
            try:
                last_ping = PingResult.model_validate_json(row["last_ping_json"])
            except Exception:
                pass

        return DeviceInstance(
            device_id=row["device_id"],
            hostname=row["hostname"],
            management_ip=row["management_ip"],
            sys_object_id=row["sys_object_id"],
            matched_profile=row["matched_profile"],
            vendor=row["vendor"] or "",
            model=row["model"] or "",
            os_family=row["os_family"] or "",
            protocols=protocols,
            vendor_adapter_id=row["vendor_adapter_id"],
            discovered=bool(row["discovered"]),
            tags=json.loads(row["tags_json"] or "[]"),
            ping_config=ping_config,
            last_collected=row["last_collected"],
            last_ping=last_ping,
            status=row["status"] or "new",
        )

    @staticmethod
    def _row_to_config(row: sqlite3.Row) -> DiscoveryConfig:
        from .models import PingConfig, SNMPVersion, SNMPv3AuthProtocol, SNMPv3PrivProtocol

        ping = PingConfig()
        if row["ping_json"]:
            try:
                ping = PingConfig.model_validate_json(row["ping_json"])
            except Exception:
                pass

        auth_proto = None
        if row["v3_auth_protocol"]:
            try:
                auth_proto = SNMPv3AuthProtocol(row["v3_auth_protocol"])
            except ValueError:
                pass

        priv_proto = None
        if row["v3_priv_protocol"]:
            try:
                priv_proto = SNMPv3PrivProtocol(row["v3_priv_protocol"])
            except ValueError:
                pass

        return DiscoveryConfig(
            config_id=row["config_id"],
            cidr=row["cidr"],
            snmp_version=SNMPVersion(row["snmp_version"]) if row["snmp_version"] else SNMPVersion.V2C,
            community=row["community"] or "public",
            v3_user=row["v3_user"],
            v3_auth_protocol=auth_proto,
            v3_auth_key=row["v3_auth_key"],
            v3_priv_protocol=priv_proto,
            v3_priv_key=row["v3_priv_key"],
            port=row["port"] or 161,
            interval_seconds=row["interval_seconds"] or 300,
            excluded_ips=json.loads(row["excluded_ips_json"] or "[]"),
            tags=json.loads(row["tags_json"] or "[]"),
            ping=ping,
            enabled=bool(row["enabled"]),
            last_scan=row["last_scan"],
            devices_found=row["devices_found"] or 0,
        )

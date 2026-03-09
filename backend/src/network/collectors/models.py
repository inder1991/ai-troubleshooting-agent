"""Data models for protocol-first network device collectors."""
from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Enums ──

class SNMPVersion(str, Enum):
    V1 = "1"
    V2C = "2c"
    V3 = "3"


class SNMPv3AuthProtocol(str, Enum):
    MD5 = "MD5"
    SHA = "SHA"
    SHA224 = "SHA224"
    SHA256 = "SHA256"
    SHA384 = "SHA384"
    SHA512 = "SHA512"


class SNMPv3PrivProtocol(str, Enum):
    DES = "DES"
    AES = "AES"
    AES192 = "AES192"
    AES256 = "AES256"


class DeviceStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    UNREACHABLE = "unreachable"
    NEW = "new"


class MetricType(str, Enum):
    GAUGE = "gauge"
    COUNTER = "counter"
    RATE = "rate"
    MONOTONIC_COUNT = "monotonic_count"


# ── Credential Models ──

class SNMPCredentials(BaseModel):
    version: SNMPVersion = SNMPVersion.V2C
    community: str = "public"
    port: int = 161
    # v3 fields
    v3_user: str | None = None
    v3_auth_protocol: SNMPv3AuthProtocol | None = None
    v3_auth_key: str | None = None
    v3_priv_protocol: SNMPv3PrivProtocol | None = None
    v3_priv_key: str | None = None


class GNMICredentials(BaseModel):
    port: int = 6030
    username: str = ""
    password: str = ""
    tls_cert: str | None = None
    tls_key: str | None = None
    tls_ca: str | None = None
    encoding: str = "json_ietf"


class RESTCONFCredentials(BaseModel):
    port: int = 443
    username: str = ""
    password: str = ""
    verify_ssl: bool = True


class SSHCredentials(BaseModel):
    port: int = 22
    username: str = ""
    password: str | None = None
    key_file: str | None = None


# ── Protocol Config ──

class ProtocolConfig(BaseModel):
    """Configuration for a single protocol on a device."""
    protocol: str  # "snmp", "gnmi", "restconf", "ssh_cli"
    priority: int = 5  # Higher = preferred. gNMI=10, RESTCONF=9, SNMP=5, SSH=3
    enabled: bool = True
    snmp: SNMPCredentials | None = None
    gnmi: GNMICredentials | None = None
    restconf: RESTCONFCredentials | None = None
    ssh: SSHCredentials | None = None


# ── Ping ──

class PingConfig(BaseModel):
    enabled: bool = True
    count: int = 4
    interval: int = 1000  # ms between pings
    timeout: int = 3000   # ms


class PingResult(BaseModel):
    rtt_avg: float = 0.0
    rtt_min: float = 0.0
    rtt_max: float = 0.0
    packet_loss_pct: float = 0.0
    reachable: bool = True
    timestamp: float = 0.0


# ── Profile Definitions ──

class MetricSymbol(BaseModel):
    OID: str
    name: str
    metric_type: MetricType = MetricType.GAUGE


class MetricTagDef(BaseModel):
    tag: str
    index: int | None = None
    column: MetricSymbol | None = None


class MetricDefinition(BaseModel):
    """A single metric or table to collect from a device profile."""
    MIB: str = ""
    # Scalar metric
    symbol: MetricSymbol | None = None
    # Table metric
    table: MetricSymbol | None = None
    symbols: list[MetricSymbol] = Field(default_factory=list)
    metric_tags: list[MetricTagDef] = Field(default_factory=list)


class MetadataFieldDef(BaseModel):
    value: str | None = None
    symbol: MetricSymbol | None = None


# ── Device Profile ──

class DeviceProfile(BaseModel):
    """Represents a loaded YAML device profile (sysObjectID → metrics mapping)."""
    name: str  # "cisco-catalyst", "arista-eos", etc.
    sysobjectid: list[str] = Field(default_factory=list)
    extends: list[str] = Field(default_factory=list)
    vendor: str = ""
    device_type: str = ""  # "switch", "router", "firewall", "ap"
    metrics: list[MetricDefinition] = Field(default_factory=list)
    metadata_fields: dict[str, MetadataFieldDef] = Field(default_factory=dict)


# ── Device Instance ──

class DeviceInstance(BaseModel):
    """Runtime state of a discovered/configured network device."""
    device_id: str = Field(default_factory=lambda: str(uuid4()))
    hostname: str = ""
    management_ip: str
    sys_object_id: str | None = None
    matched_profile: str | None = None
    vendor: str = ""
    model: str = ""
    os_family: str = ""
    protocols: list[ProtocolConfig] = Field(default_factory=list)
    vendor_adapter_id: str | None = None
    discovered: bool = False
    tags: list[str] = Field(default_factory=list)
    ping_config: PingConfig | None = Field(default_factory=PingConfig)
    last_collected: float | None = None
    last_ping: PingResult | None = None
    status: DeviceStatus = DeviceStatus.NEW


# ── Discovery Config ──

class DiscoveryConfig(BaseModel):
    """Configuration for SNMP autodiscovery on a subnet."""
    config_id: str = Field(default_factory=lambda: str(uuid4()))
    cidr: str
    snmp_version: SNMPVersion = SNMPVersion.V2C
    community: str = "public"
    v3_user: str | None = None
    v3_auth_protocol: SNMPv3AuthProtocol | None = None
    v3_auth_key: str | None = None
    v3_priv_protocol: SNMPv3PrivProtocol | None = None
    v3_priv_key: str | None = None
    port: int = 161
    interval_seconds: int = 300
    excluded_ips: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    ping: PingConfig = Field(default_factory=PingConfig)
    enabled: bool = True
    last_scan: float | None = None
    devices_found: int = 0


# ── Collected Data ──

class CollectedData(BaseModel):
    """Unified output from any protocol collector."""
    device_id: str
    protocol: str  # CollectorProtocol value
    timestamp: float
    cpu_pct: float | None = None
    mem_pct: float | None = None
    uptime_seconds: int | None = None
    temperature: float | None = None
    interface_metrics: dict[str, dict[str, float]] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)
    custom_metrics: dict[str, float] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


# ── Collector Health ──

class CollectorHealth(BaseModel):
    protocol: str
    status: str  # "ok", "degraded", "error"
    message: str = ""
    devices_collected: int = 0
    last_collection: float | None = None

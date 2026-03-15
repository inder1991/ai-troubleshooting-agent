"""Network troubleshooting data models."""
from __future__ import annotations
from enum import Enum
from typing import Optional, Literal
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from datetime import datetime
import ipaddress as _ipaddress


def _validate_ip(v: str, field_name: str) -> str:
    """Validate IP address format. Empty string is allowed (optional)."""
    if not v:
        return v
    try:
        _ipaddress.ip_address(v)
    except ValueError:
        raise ValueError(f"Invalid IP address for {field_name}: '{v}'")
    return v


def _validate_cidr(v: str, field_name: str) -> str:
    """Validate CIDR notation. Empty string is allowed.

    For IPv4 networks, prefix length must be 8-32.
    """
    if not v:
        return v
    try:
        net = _ipaddress.ip_network(v, strict=False)
    except ValueError:
        raise ValueError(f"Invalid CIDR for {field_name}: '{v}'")
    if net.version == 4:
        if net.prefixlen < 8 or net.prefixlen > 32:
            raise ValueError(
                f"IPv4 CIDR prefix length must be 8-32 for {field_name}, got /{net.prefixlen}"
            )
    return v


VALID_PROTOCOLS = {"tcp", "udp", "icmp", "any"}


# ── Enums ──

class DeviceType(str, Enum):
    ROUTER = "router"
    SWITCH = "switch"
    FIREWALL = "firewall"
    PROXY = "proxy"
    GATEWAY = "gateway"
    HOST = "host"
    VPC = "vpc"
    TRANSIT_GATEWAY = "transit_gateway"
    LOAD_BALANCER = "load_balancer"
    VPN_GATEWAY = "vpn_gateway"
    DIRECT_CONNECT = "direct_connect"
    NACL = "nacl"
    NAT_GATEWAY = "nat_gateway"
    INTERNET_GATEWAY = "internet_gateway"
    LAMBDA = "lambda"
    ROUTE_TABLE = "route_table"
    SECURITY_GROUP = "security_group"
    ELASTIC_IP = "elastic_ip"
    # Enterprise network device types
    VPN_CONCENTRATOR = "vpn_concentrator"
    SDWAN_EDGE = "sdwan_edge"
    IDS_IPS = "ids_ips"
    WAF = "waf"
    CLOUD_GATEWAY = "cloud_gateway"
    WIRELESS_CONTROLLER = "wireless_controller"
    ACCESS_POINT = "access_point"
    VIRTUAL_APPLIANCE = "virtual_appliance"

class FirewallVendor(str, Enum):
    PALO_ALTO = "palo_alto"
    AZURE_NSG = "azure_nsg"
    AWS_SG = "aws_sg"
    ORACLE_NSG = "oracle_nsg"
    ZSCALER = "zscaler"
    CISCO = "cisco"
    F5 = "f5"
    CHECKPOINT = "checkpoint"

class EdgeSource(str, Enum):
    MANUAL = "manual"
    IPAM = "ipam"
    TRACEROUTE = "traceroute"
    API = "api"
    INFERRED = "inferred"
    DIAGNOSIS = "diagnosis"

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
    EXACT = "exact"
    IMPLICIT_DENY = "implicit_deny"
    SHADOWED = "shadowed"
    ADAPTER_INFERENCE = "adapter_inference"
    ADAPTER_UNAVAILABLE = "adapter_unavailable"
    INSUFFICIENT_DATA = "insufficient_data"

class CloudProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    OCI = "oci"

class TunnelType(str, Enum):
    IPSEC = "ipsec"
    GRE = "gre"
    SSL = "ssl"

class DirectConnectProvider(str, Enum):
    AWS_DX = "aws_dx"
    AZURE_ER = "azure_er"
    OCI_FC = "oci_fc"

class LBType(str, Enum):
    ALB = "alb"
    NLB = "nlb"
    AZURE_LB = "azure_lb"
    HAPROXY = "haproxy"

class LBScheme(str, Enum):
    INTERNET_FACING = "internet_facing"
    INTERNAL = "internal"

class ComplianceStandard(str, Enum):
    PCI_DSS = "pci_dss"
    SOC2 = "soc2"
    HIPAA = "hipaa"
    CUSTOM = "custom"

class NACLDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"

class ConnectivityStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"

class HAMode(str, Enum):
    ACTIVE_PASSIVE = "active_passive"
    ACTIVE_ACTIVE = "active_active"
    VRRP = "vrrp"
    CLUSTER = "cluster"

class HARole(str, Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    MEMBER = "member"

class InterfaceRole(str, Enum):
    MANAGEMENT = "management"
    INSIDE = "inside"
    OUTSIDE = "outside"
    DMZ = "dmz"
    SYNC = "sync"
    LOOPBACK = "loopback"

class ZoneType(str, Enum):
    MANAGEMENT = "management"
    DATA = "data"
    DMZ = "dmz"

class IPStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    ASSIGNED = "assigned"
    DEPRECATED = "deprecated"

class IPType(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    GATEWAY = "gateway"
    NETWORK = "network"
    BROADCAST = "broadcast"


# ── Infrastructure Entities (persist in graph + SQLite) ──

class Device(BaseModel):
    id: str
    name: str
    vendor: str = ""
    device_type: DeviceType = DeviceType.HOST
    management_ip: str = ""
    model: str = ""
    location: str = ""
    zone_id: str = ""
    vlan_id: int = 0
    description: str = ""
    ha_group_id: str = ""
    ha_role: str = ""  # "active", "standby", "member", or ""
    # Enterprise inventory fields
    role: str = ""              # "core" | "distribution" | "access" | "edge" | "cloud_gateway" | ""
    serial_number: str = ""
    os_version: str = ""
    site_id: str = ""
    region: str = ""
    cloud_provider: str = ""   # "aws" | "azure" | "gcp" | "oci" | ""
    discovered_at: str = ""
    last_seen: str = ""

    @field_validator("management_ip")
    @classmethod
    def validate_management_ip(cls, v: str) -> str:
        return _validate_ip(v, "management_ip")

    @field_validator("vlan_id")
    @classmethod
    def validate_vlan_id(cls, v: int) -> int:
        if v != 0 and (v < 1 or v > 4094):
            raise ValueError(f"VLAN ID must be 0 (unset) or 1-4094, got {v}")
        return v

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
    role: str = ""       # InterfaceRole value or empty
    subnet_id: str = ""  # FK to subnet
    vlan_id: int = 0
    # Physical / operational attributes
    mtu: int = 0
    duplex: str = ""          # "full" | "half" | "auto" | ""
    admin_status: str = "up"  # "up" | "down"
    oper_status: str = "up"   # "up" | "down" | "testing"
    description: str = ""
    channel_group: str = ""   # For LAG/port-channel membership
    media_type: str = ""      # "copper" | "fiber" | "virtual" | ""

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return _validate_ip(v, "interface ip")

class Subnet(BaseModel):
    id: str
    cidr: str
    vlan_id: int = 0
    zone_id: str = ""
    gateway_ip: str = ""
    description: str = ""
    site: str = ""
    parent_subnet_id: str = ""
    region: str = ""
    environment: str = ""
    ip_version: int = 4
    vpc_id: str = ""           # FK to vpcs table
    cloud_provider: str = ""   # aws, azure, gcp, oci
    vrf_id: str = "default"
    subnet_role: str = ""      # "server", "storage", "voice", "dmz", "management", "user", "iot"
    address_block_id: str = ""
    site_id: str = ""

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        return _validate_cidr(v, "cidr")

    @field_validator("gateway_ip")
    @classmethod
    def validate_gateway_ip(cls, v: str) -> str:
        return _validate_ip(v, "gateway_ip")

    @field_validator("vlan_id")
    @classmethod
    def validate_vlan_id(cls, v: int) -> int:
        if v != 0 and (v < 1 or v > 4094):
            raise ValueError(f"VLAN ID must be 0 (unset) or 1-4094, got {v}")
        return v

    @model_validator(mode='after')
    def validate_gateway_in_subnet(self) -> 'Subnet':
        if self.gateway_ip and self.cidr:
            try:
                net = _ipaddress.ip_network(self.cidr, strict=False)
                gw = _ipaddress.ip_address(self.gateway_ip)
                if gw not in net:
                    raise ValueError(f"Gateway IP {self.gateway_ip} is not within subnet {self.cidr}")
            except ValueError as e:
                if "not within subnet" in str(e):
                    raise
                pass  # IP/CIDR format errors handled by field validators
        return self

class IPAddress(BaseModel):
    id: str
    address: str
    subnet_id: str
    status: str = "available"  # IPStatus value
    ip_type: str = "static"    # IPType value
    assigned_device_id: str = ""
    assigned_interface_id: str = ""
    hostname: str = ""
    mac_address: str = ""      # e.g. "00-15-5D-C1-01-2C"
    vendor: str = ""           # e.g. "Microsoft Corporation", "VMware, Inc."
    description: str = ""
    last_seen: str = ""
    created_at: str = ""
    owner_team: str = ""       # e.g. "Payments", "Infrastructure"
    application: str = ""      # e.g. "PaymentGateway", "Redis"
    environment: str = ""      # e.g. "production", "staging"
    discovery_source: str = "" # e.g. "manual", "arp", "snmp"
    confidence_score: float = 1.0

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        return _validate_ip(v, "address")

    @field_validator("mac_address")
    @classmethod
    def validate_mac_address(cls, v: str) -> str:
        """Validate MAC address format (colon, hyphen, or Cisco dot notation)."""
        if not v:
            return v
        import re
        # Colon format: 00:1A:2B:3C:4D:5E
        # Hyphen format: 00-1A-2B-3C-4D-5E
        # Cisco dot format: 001A.2B3C.4D5E
        mac_patterns = [
            r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$',
            r'^([0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}$',
            r'^([0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}$',
        ]
        if not any(re.match(p, v) for p in mac_patterns):
            raise ValueError(f"Invalid MAC address format: '{v}'. Use XX:XX:XX:XX:XX:XX, XX-XX-XX-XX-XX-XX, or XXXX.XXXX.XXXX")
        return v

class Zone(BaseModel):
    id: str
    name: str
    security_level: int = 0
    description: str = ""
    firewall_id: str = ""
    zone_type: str = ""  # ZoneType value or empty

class Workload(BaseModel):
    id: str
    name: str
    namespace: str = ""
    cluster: str = ""
    ips: list[str] = Field(default_factory=list)
    description: str = ""


# ── Enterprise Hybrid Entities ──

class VPC(BaseModel):
    id: str
    name: str
    cloud_provider: CloudProvider = CloudProvider.AWS
    region: str = ""
    cidr_blocks: list[str] = Field(default_factory=list)
    account_id: str = ""
    compliance_zone: str = ""

class RouteTable(BaseModel):
    id: str
    vpc_id: str
    name: str = ""
    is_main: bool = False

class VPCPeering(BaseModel):
    id: str
    requester_vpc_id: str
    accepter_vpc_id: str
    status: str = "active"
    cidr_routes: list[str] = Field(default_factory=list)

class TransitGateway(BaseModel):
    id: str
    name: str
    cloud_provider: CloudProvider = CloudProvider.AWS
    region: str = ""
    attached_vpc_ids: list[str] = Field(default_factory=list)
    route_table_id: str = ""

class VPNTunnel(BaseModel):
    id: str
    name: str
    tunnel_type: TunnelType = TunnelType.IPSEC
    local_gateway_id: str = ""
    remote_gateway_ip: str = ""
    local_cidrs: list[str] = Field(default_factory=list)
    remote_cidrs: list[str] = Field(default_factory=list)
    encryption: str = "AES-256-GCM"
    ike_version: str = "IKEv2"
    status: ConnectivityStatus = ConnectivityStatus.UP

class DirectConnect(BaseModel):
    id: str
    name: str
    provider: DirectConnectProvider = DirectConnectProvider.AWS_DX
    bandwidth_mbps: int = 1000
    location: str = ""
    vlan_id: int = 0
    bgp_asn: int = 0
    status: ConnectivityStatus = ConnectivityStatus.UP

class NACL(BaseModel):
    id: str
    name: str
    vpc_id: str = ""
    subnet_ids: list[str] = Field(default_factory=list)
    is_default: bool = False

class NACLRule(BaseModel):
    id: str
    nacl_id: str
    direction: NACLDirection = NACLDirection.INBOUND
    rule_number: int = 100
    protocol: str = "tcp"
    cidr: str = "0.0.0.0/0"
    port_range_from: int = 0
    port_range_to: int = 65535
    action: PolicyAction = PolicyAction.ALLOW

class LoadBalancer(BaseModel):
    id: str
    name: str
    lb_type: LBType = LBType.ALB
    scheme: LBScheme = LBScheme.INTERNAL
    vpc_id: str = ""
    listeners: list[dict] = Field(default_factory=list)
    health_check_path: str = "/health"

class LBTargetGroup(BaseModel):
    id: str
    lb_id: str
    name: str = ""
    protocol: str = "tcp"
    port: int = 80
    target_ids: list[str] = Field(default_factory=list)
    health_status: str = "healthy"

class VRF(BaseModel):
    id: str
    name: str
    rd: str = ""                  # Route Distinguisher "65000:1"
    rt_import: list[str] = Field(default_factory=list)
    rt_export: list[str] = Field(default_factory=list)
    description: str = ""
    device_ids: list[str] = Field(default_factory=list)
    is_default: bool = False

    @field_validator("rd")
    @classmethod
    def validate_rd(cls, v: str) -> str:
        if not v:
            return v
        import re
        # ASN:nn or IP:nn
        if not re.match(r'^(\d+:\d+|\d+\.\d+\.\d+\.\d+:\d+)$', v):
            raise ValueError(f"Invalid Route Distinguisher format: '{v}'. Use ASN:nn or IP:nn")
        return v


class Region(BaseModel):
    id: str
    name: str                    # "US-East", "EU-West"
    description: str = ""


class Site(BaseModel):
    id: str
    name: str                    # "DC-East-1"
    region_id: str = ""          # FK to Region
    site_type: str = ""          # "datacenter" | "branch" | "cloud" | "colo"
    address: str = ""
    description: str = ""


class AddressBlock(BaseModel):
    id: str
    cidr: str                    # "10.0.0.0/8"
    name: str = ""               # "RFC1918 Block A"
    vrf_id: str = "default"
    site_id: str = ""
    description: str = ""
    rir: str = "private"         # "ARIN", "RIPE", "APNIC", "private"

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        return _validate_cidr(v, "address_block cidr")


class CloudAccount(BaseModel):
    id: str
    name: str                          # "prod-aws-east"
    provider: CloudProvider            # aws, azure, gcp, oci
    account_id: str = ""               # AWS account ID, Azure subscription
    region: str = ""
    credentials_ref: str = ""          # Reference to secrets store
    sync_enabled: bool = False
    last_sync: str = ""


class CloudInterface(BaseModel):
    """Maps to AWS ENI, Azure NIC, GCP Network Interface."""
    id: str
    cloud_account_id: str
    instance_id: str = ""
    instance_name: str = ""
    vpc_id: str = ""
    subnet_id: str = ""
    security_group_ids: list[str] = Field(default_factory=list)
    private_ips: list[str] = Field(default_factory=list)
    public_ip: str = ""
    mac_address: str = ""
    status: str = "in-use"


class VLAN(BaseModel):
    id: str
    vlan_number: int
    name: str = ""
    trunk_ports: list[str] = Field(default_factory=list)
    access_ports: list[str] = Field(default_factory=list)
    site: str = ""
    description: str = ""
    vrf_id: str = "default"
    site_id: str = ""
    subnet_ids: list[str] = Field(default_factory=list)

    @field_validator("vlan_number")
    @classmethod
    def validate_vlan_number(cls, v: int) -> int:
        if v < 1 or v > 4094:
            raise ValueError(f"VLAN number must be 1-4094, got {v}")
        return v

class MPLSCircuit(BaseModel):
    id: str
    name: str
    label: int = 0
    provider: str = ""
    bandwidth_mbps: int = 100
    endpoints: list[str] = Field(default_factory=list)
    qos_class: str = ""

class ComplianceZone(BaseModel):
    id: str
    name: str
    standard: ComplianceStandard = ComplianceStandard.PCI_DSS
    description: str = ""
    subnet_ids: list[str] = Field(default_factory=list)
    vpc_ids: list[str] = Field(default_factory=list)

class HAGroup(BaseModel):
    id: str
    name: str
    ha_mode: HAMode
    member_ids: list[str]
    virtual_ips: list[str] = Field(default_factory=list)
    active_member_id: str = ""
    priority_map: dict[str, int] = Field(default_factory=dict)
    sync_interface: str = ""

    @field_validator("member_ids")
    @classmethod
    def validate_member_ids(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError("HA group must have at least 2 members")
        return v

    @field_validator("virtual_ips")
    @classmethod
    def validate_virtual_ips(cls, v: list[str]) -> list[str]:
        for vip in v:
            _validate_ip(vip, "virtual_ip")
        return v


# ── Relationship Tables (SQLite, loaded dynamically) ──

class Route(BaseModel):
    id: str
    device_id: str
    destination_cidr: str
    next_hop: str
    interface: str = ""
    metric: int = 0
    protocol: str = "static"
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

    @field_validator("src_ip", "dst_ip")
    @classmethod
    def validate_flow_ips(cls, v: str) -> str:
        return _validate_ip(v, "ip")

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v < 1 or v > 65535:
            raise ValueError(f"port must be 1-65535, got {v}")
        return v

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        if v not in VALID_PROTOCOLS:
            raise ValueError(f"protocol must be one of {VALID_PROTOCOLS}, got '{v}'")
        return v

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
    matched_source: str = ""
    matched_destination: str = ""
    matched_ports: str = ""

class AdapterConfig(BaseModel):
    vendor: FirewallVendor
    api_endpoint: str = ""
    api_key: str = ""
    extra_config: dict = Field(default_factory=dict)


class AdapterInstance(BaseModel):
    instance_id: str = Field(default_factory=lambda: str(uuid4()))
    label: str
    vendor: FirewallVendor
    api_endpoint: str = ""
    api_key: str = ""
    extra_config: dict = Field(default_factory=dict)
    device_groups: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


# ── Identity Chain (NAT tracking) ──

class IdentityStage(BaseModel):
    stage: str
    ip: str
    port: int = 0
    device_id: Optional[str] = None


# ── Diagnostic State (for LangGraph) ──

class NetworkDiagnosticState(BaseModel):
    """LangGraph shared state for network diagnosis pipeline."""
    flow_id: str = ""
    src_ip: str = ""
    dst_ip: str = ""
    port: int = 0
    protocol: str = "tcp"
    src_device: Optional[dict] = None
    dst_device: Optional[dict] = None
    src_subnet: Optional[dict] = None
    dst_subnet: Optional[dict] = None
    resolution_status: str = "pending"
    ambiguous_candidates: list[dict] = Field(default_factory=list)
    candidate_paths: list[dict] = Field(default_factory=list)
    traced_path: Optional[dict] = None
    trace_method: str = "pending"
    final_path: Optional[dict] = None
    firewalls_in_path: list[dict] = Field(default_factory=list)
    firewall_verdicts: list[dict] = Field(default_factory=list)
    nat_translations: list[dict] = Field(default_factory=list)
    identity_chain: list[dict] = Field(default_factory=list)
    trace_id: Optional[str] = None
    trace_hops: list[dict] = Field(default_factory=list)
    routing_loop_detected: bool = False
    diagnosis_status: str = "running"
    confidence: float = 0.0
    evidence: list[dict] = Field(default_factory=list)
    contradictions: list[dict] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    executive_summary: str = ""
    error: Optional[str] = None


# ── Notification Channels ─────────────────────────────────────────────

class ChannelType(str, Enum):
    WEBHOOK = "webhook"
    SLACK = "slack"
    EMAIL = "email"
    PAGERDUTY = "pagerduty"
    TEAMS = "teams"


class NotificationChannel(BaseModel):
    """A configured notification destination."""
    id: str
    name: str
    channel_type: ChannelType
    config: dict = Field(default_factory=dict)
    enabled: bool = True


class NotificationRouting(BaseModel):
    """Routes alerts of given severities to specific channels."""
    id: str
    severity_filter: list[str] = Field(default_factory=lambda: ["critical", "warning"])
    channel_ids: list[str] = Field(..., min_length=1)
    enabled: bool = True


# ── DNS Monitoring ───────────────────────────────────────────────────

class DNSRecordType(str, Enum):
    A = "A"
    AAAA = "AAAA"
    MX = "MX"
    NS = "NS"
    CNAME = "CNAME"
    TXT = "TXT"
    SOA = "SOA"
    PTR = "PTR"


class DNSServerConfig(BaseModel):
    id: str
    name: str
    ip: str
    port: int = 53
    enabled: bool = True

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return _validate_ip(v, "dns_server ip")

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v < 1 or v > 65535:
            raise ValueError(f"port must be 1-65535, got {v}")
        return v


class DNSWatchedHostname(BaseModel):
    hostname: str = Field(max_length=253)
    record_type: DNSRecordType = DNSRecordType.A
    expected_values: list[str] = []
    critical: bool = False


class DNSMonitorConfig(BaseModel):
    servers: list[DNSServerConfig] = []
    watched_hostnames: list[DNSWatchedHostname] = []
    query_timeout: float = 5.0
    enabled: bool = True

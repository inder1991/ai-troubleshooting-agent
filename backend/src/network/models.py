"""Network troubleshooting data models."""
from __future__ import annotations
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator
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
    """Validate CIDR notation. Empty string is allowed."""
    if not v:
        return v
    try:
        _ipaddress.ip_network(v, strict=False)
    except ValueError:
        raise ValueError(f"Invalid CIDR for {field_name}: '{v}'")
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

class Subnet(BaseModel):
    id: str
    cidr: str
    vlan_id: int = 0
    zone_id: str = ""
    gateway_ip: str = ""
    description: str = ""
    site: str = ""

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

class VLAN(BaseModel):
    id: str
    vlan_number: int
    name: str = ""
    trunk_ports: list[str] = Field(default_factory=list)
    access_ports: list[str] = Field(default_factory=list)
    site: str = ""

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
        if v < 0 or v > 65535:
            raise ValueError(f"port must be 0-65535, got {v}")
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

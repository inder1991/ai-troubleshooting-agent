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
    EXACT = "exact"
    IMPLICIT_DENY = "implicit_deny"
    SHADOWED = "shadowed"
    ADAPTER_INFERENCE = "adapter_inference"
    ADAPTER_UNAVAILABLE = "adapter_unavailable"
    INSUFFICIENT_DATA = "insufficient_data"


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

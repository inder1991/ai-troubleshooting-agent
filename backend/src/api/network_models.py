"""Request/response Pydantic models for the network troubleshooting API."""
import ipaddress
from pydantic import BaseModel, Field, field_validator
from typing import Optional

VALID_PROTOCOLS = {"tcp", "udp", "icmp", "any"}


class DiagnoseRequest(BaseModel):
    src_ip: str
    dst_ip: str
    port: int = 80
    protocol: str = "tcp"
    session_id: Optional[str] = None  # reuse existing session
    bidirectional: bool = False

    @field_validator("src_ip", "dst_ip")
    @classmethod
    def validate_ips(cls, v: str) -> str:
        if not v:
            raise ValueError("IP address is required")
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError(f"Invalid IP address: '{v}'")
        return v

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


class DiagnoseResponse(BaseModel):
    session_id: str
    flow_id: str
    status: str
    message: str


class TopologySaveRequest(BaseModel):
    diagram_json: str
    description: str = ""


class AdapterConfigureRequest(BaseModel):
    vendor: str = "palo_alto"
    node_id: Optional[str] = None
    api_endpoint: str
    api_key: str = ""
    extra_config: dict = Field(default_factory=dict)


class TopologyPromoteRequest(BaseModel):
    nodes: list[dict] = []
    edges: list[dict] = []


class MatrixRequest(BaseModel):
    zone_ids: list[str]


class HAGroupRequest(BaseModel):
    name: str
    ha_mode: str  # "active_passive", "active_active", "vrrp", "cluster"
    member_ids: list[str]
    virtual_ips: list[str] = []
    active_member_id: str = ""


class AdapterInstanceCreateRequest(BaseModel):
    label: str
    vendor: str
    api_endpoint: str = ""
    api_key: str = ""
    extra_config: dict = Field(default_factory=dict)


class AdapterInstanceUpdateRequest(BaseModel):
    label: str | None = None
    api_endpoint: str | None = None
    api_key: str | None = None
    extra_config: dict | None = None
    device_groups: list[str] | None = None


class AdapterBindRequest(BaseModel):
    device_ids: list[str]


# ── Topology Design Lifecycle ──

class DesignCreateRequest(BaseModel):
    name: str
    description: str = ""
    snapshot_json: str = "{}"


class DesignUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    snapshot_json: str | None = None
    expected_version: int | None = None


class DesignStatusRequest(BaseModel):
    status: str
    applied_by: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"draft", "reviewed", "simulated", "approved", "parked", "applied", "verified"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}, got '{v}'")
        return v


class SimulateConnectivityRequest(BaseModel):
    source_id: str
    target_id: str


class SimulateFirewallRequest(BaseModel):
    src_ip: str
    dst_ip: str
    port: int = 80
    protocol: str = "tcp"

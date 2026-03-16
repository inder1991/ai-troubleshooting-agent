"""Canonical domain models for network topology entities.

These are pure Python dataclasses — intentionally separate from the Pydantic
API models so the domain layer has zero framework dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ── Device ──────────────────────────────────────────────────────────────────


@dataclass
class Device:
    """A network device (switch, router, firewall, load-balancer, …)."""

    id: str
    hostname: str
    vendor: str
    model: str
    serial: str
    device_type: str
    site_id: str
    sources: list[str]
    first_seen: datetime
    last_seen: datetime
    confidence: float

    # Optional
    managed_by: Optional[str] = None
    mode: Optional[str] = None
    ha_mode: Optional[str] = None
    state_sync: bool = False


# ── Interface ───────────────────────────────────────────────────────────────


@dataclass
class Interface:
    """A physical or logical interface on a device.

    ``id`` uses the stable format ``<device_id>:<name>``.
    """

    id: str  # device_id:name
    device_id: str
    name: str
    sources: list[str]
    first_seen: datetime
    last_seen: datetime
    confidence: float

    # Optional
    mac: Optional[str] = None
    admin_state: str = "up"
    oper_state: str = "up"
    speed: Optional[str] = None
    mtu: Optional[int] = None
    duplex: Optional[str] = None
    port_channel_id: Optional[str] = None
    description: Optional[str] = None
    vrf_instance_id: Optional[str] = None
    vlan_membership: list[int] = field(default_factory=list)


# ── IPAddress ───────────────────────────────────────────────────────────────


@dataclass
class IPAddress:
    """An IP address assigned to an interface."""

    id: str
    ip: str
    assigned_to: str  # interface id
    sources: list[str]
    first_seen: datetime
    last_seen: datetime
    confidence: float

    # Optional
    prefix_len: Optional[int] = None
    assigned_from: Optional[str] = None
    lease_ts: Optional[datetime] = None


# ── Subnet ──────────────────────────────────────────────────────────────────


@dataclass
class Subnet:
    """An IP subnet / prefix."""

    id: str
    cidr: str
    sources: list[str]
    first_seen: datetime
    last_seen: datetime

    # Optional
    vpc_id: Optional[str] = None
    vrf_id: Optional[str] = None
    purpose: Optional[str] = None
    owner: Optional[str] = None


# ── VLAN ────────────────────────────────────────────────────────────────────


@dataclass
class VLAN:
    """A VLAN definition."""

    id: str
    vlan_id: int
    name: str

    # Optional
    site_id: Optional[str] = None


# ── Site ────────────────────────────────────────────────────────────────────


@dataclass
class Site:
    """A physical or logical site / data-center."""

    id: str
    name: str

    # Optional
    location: Optional[str] = None
    site_type: Optional[str] = None


# ── Zone ────────────────────────────────────────────────────────────────────


@dataclass
class Zone:
    """A security / network zone."""

    id: str
    name: str

    # Optional
    security_level: int = 0
    zone_type: Optional[str] = None


# ── VRFInstance ─────────────────────────────────────────────────────────────


@dataclass
class VRFInstance:
    """A VRF instance on a specific device.

    ``id`` uses the stable format ``<device_id>:<vrf_name>``.
    """

    id: str  # device_id:vrf_name
    vrf_id: str
    device_id: str
    sources: list[str]
    first_seen: datetime
    last_seen: datetime

    # Optional
    table_id: Optional[int] = None


# ── Route ───────────────────────────────────────────────────────────────────


@dataclass
class Route:
    """A routing table entry."""

    id: str
    device_id: str
    vrf_instance_id: str
    destination_cidr: str
    prefix_len: int
    protocol: str
    sources: list[str]
    first_seen: datetime
    last_seen: datetime

    # Optional
    admin_distance: Optional[int] = None
    metric: Optional[int] = None
    next_hop_type: Optional[str] = None
    next_hop_refs: list[dict] = field(default_factory=list)


# ── NeighborLink ────────────────────────────────────────────────────────────


@dataclass
class NeighborLink:
    """A discovered adjacency between two devices (LLDP / CDP)."""

    id: str
    device_id: str
    local_interface: str   # interface id
    remote_device: str
    remote_interface: str  # interface id
    protocol: str          # lldp / cdp
    sources: list[str]
    first_seen: datetime
    last_seen: datetime
    confidence: float


# ── SecurityPolicy ──────────────────────────────────────────────────────────


@dataclass
class SecurityPolicy:
    """A firewall / ACL rule."""

    id: str
    device_id: str
    rule_order: int
    name: str
    action: str  # permit / deny / drop / reset
    sources: list[str]
    first_seen: datetime
    last_seen: datetime

    # Optional
    src_zone: Optional[str] = None
    dst_zone: Optional[str] = None
    src_ip: Optional[str] = None
    dst_ip: Optional[str] = None
    src_port_range: Optional[str] = None
    dst_port_range: Optional[str] = None
    protocol: Optional[str] = None
    log: bool = False
    stateful: bool = True


# ── NATRule ─────────────────────────────────────────────────────────────────


@dataclass
class NATRule:
    """A NAT translation rule."""

    id: str
    device_id: str
    nat_type: str  # SNAT / DNAT / PAT / twice_nat
    priority: int
    sources: list[str]
    first_seen: datetime
    last_seen: datetime

    # Optional
    original_src: Optional[str] = None
    original_dst: Optional[str] = None
    translated_src: Optional[str] = None
    translated_dst: Optional[str] = None
    original_port: Optional[str] = None
    translated_port: Optional[str] = None
    direction: Optional[str] = None

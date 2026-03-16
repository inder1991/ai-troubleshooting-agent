"""ObservationType enum and DiscoveryObservation dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ObservationType(str, Enum):
    """Types of network observations that discovery adapters can produce."""

    DEVICE = "device"
    INTERFACE = "interface"
    NEIGHBOR = "neighbor"
    ROUTE = "route"
    BGP_PEER = "bgp_peer"
    OSPF_NEIGHBOR = "ospf_neighbor"
    ARP_ENTRY = "arp_entry"
    MAC_ENTRY = "mac_entry"
    LAG_MEMBER = "lag_member"
    VPC = "vpc"
    SUBNET = "subnet"
    SECURITY_GROUP = "security_group"
    CLOUD_INTERFACE = "cloud_interface"
    ROUTE_TABLE = "route_table"
    LOAD_BALANCER = "load_balancer"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DiscoveryObservation:
    """A single observation produced by a discovery adapter."""

    observation_type: ObservationType
    source: str
    device_id: str
    data: dict = field(default_factory=dict)
    confidence: float = 0.5
    observed_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary with observation_type as its string value."""
        return {
            "observation_type": self.observation_type.value,
            "source": self.source,
            "device_id": self.device_id,
            "data": self.data,
            "confidence": self.confidence,
            "observed_at": self.observed_at,
        }

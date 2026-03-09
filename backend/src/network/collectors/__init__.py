"""Protocol-first network device collectors (Datadog NDM-inspired)."""

from .base import ProtocolCollector, CollectorProtocol, CollectedData, CollectorHealth
from .models import (
    DeviceInstance, DeviceProfile, ProtocolConfig,
    SNMPCredentials, GNMICredentials, RESTCONFCredentials, SSHCredentials,
    DiscoveryConfig, PingConfig, PingResult,
    MetricDefinition, MetricTagDef, MetadataFieldDef,
)
from .collector_registry import CollectorRegistry
from .profile_loader import ProfileLoader

__all__ = [
    "ProtocolCollector", "CollectorProtocol", "CollectedData", "CollectorHealth",
    "DeviceInstance", "DeviceProfile", "ProtocolConfig",
    "SNMPCredentials", "GNMICredentials", "RESTCONFCredentials", "SSHCredentials",
    "DiscoveryConfig", "PingConfig", "PingResult",
    "MetricDefinition", "MetricTagDef", "MetadataFieldDef",
    "CollectorRegistry", "ProfileLoader",
]

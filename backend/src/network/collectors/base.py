"""Protocol collector abstract base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from .models import CollectedData, CollectorHealth, DeviceInstance, DeviceProfile


class CollectorProtocol(str, Enum):
    SNMP = "snmp"
    GNMI = "gnmi"
    RESTCONF = "restconf"
    SSH_CLI = "ssh_cli"
    CLOUD_API = "cloud_api"


class ProtocolCollector(ABC):
    """Abstract base class for protocol-specific collectors.

    Each collector is a singleton that handles ALL devices using its protocol.
    The DeviceProfile tells it which OIDs / paths / commands to query.
    """

    protocol: CollectorProtocol

    @abstractmethod
    async def collect(
        self, instance: DeviceInstance, profile: DeviceProfile
    ) -> CollectedData:
        """Collect metrics from a single device using matched profile."""
        ...

    @abstractmethod
    async def health_check(self, instance: DeviceInstance) -> CollectorHealth:
        """Check connectivity to device via this protocol."""
        ...

    async def collect_batch(
        self, instances: list[tuple[DeviceInstance, DeviceProfile]]
    ) -> list[CollectedData]:
        """Collect from multiple devices. Default: sequential."""
        results = []
        for inst, prof in instances:
            try:
                data = await self.collect(inst, prof)
                results.append(data)
            except Exception:
                pass  # Individual failures don't block batch
        return results

    async def query_sys_object_id(self, ip: str, creds: dict) -> str | None:
        """Query sysObjectID from a device. Override for SNMP."""
        return None

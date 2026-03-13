"""Abstract base class for cloud provider drivers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from src.cloud.models import CloudAccount, DiscoveryBatch, DriverHealth


class CloudProviderDriver(ABC):
    """Provider-agnostic interface for cloud resource discovery."""

    @abstractmethod
    async def discover(
        self,
        account: CloudAccount,
        region: str,
        resource_types: list[str],
    ) -> AsyncIterator[DiscoveryBatch]:
        """Yield batches of discovered resources."""
        ...  # pragma: no cover

    @abstractmethod
    async def health_check(self, account: CloudAccount) -> DriverHealth:
        """Validate credentials and connectivity."""
        ...  # pragma: no cover

    @abstractmethod
    def supported_resource_types(self) -> dict[str, int]:
        """Return {resource_type: sync_tier} mapping."""
        ...  # pragma: no cover

    def resource_types_for_tier(self, tier: int) -> list[str]:
        """Return resource types belonging to a specific tier."""
        return [
            rt for rt, t in self.supported_resource_types().items() if t == tier
        ]

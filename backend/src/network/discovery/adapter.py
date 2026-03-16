"""Abstract base class for discovery adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .observation import DiscoveryObservation


class DiscoveryAdapter(ABC):
    """Base class that all discovery adapters must implement."""

    @abstractmethod
    async def discover(self, target: dict) -> AsyncIterator[DiscoveryObservation]:
        """Discover network observations for a given target.

        Args:
            target: A dict describing what to discover (e.g. host, credentials, scope).

        Yields:
            DiscoveryObservation instances as they are found.
        """
        ...  # pragma: no cover

    @abstractmethod
    def supports(self, target: dict) -> bool:
        """Return True if this adapter can handle the given target.

        Args:
            target: A dict describing the discovery target.
        """
        ...  # pragma: no cover

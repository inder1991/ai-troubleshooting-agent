"""Registry mapping protocols to their singleton collector instances."""
from __future__ import annotations

import logging
from typing import Iterator

from .base import CollectorProtocol, ProtocolCollector

logger = logging.getLogger(__name__)


class CollectorRegistry:
    """Protocol → Collector singleton mapping.

    Each protocol (SNMP, gNMI, RESTCONF, …) has exactly one collector instance.
    """

    def __init__(self) -> None:
        self._collectors: dict[CollectorProtocol, ProtocolCollector] = {}

    def register(self, collector: ProtocolCollector) -> None:
        proto = collector.protocol
        self._collectors[proto] = collector
        logger.info("Registered %s collector", proto.value)

    def get(self, protocol: CollectorProtocol) -> ProtocolCollector | None:
        return self._collectors.get(protocol)

    def get_by_name(self, name: str) -> ProtocolCollector | None:
        try:
            proto = CollectorProtocol(name)
        except ValueError:
            return None
        return self._collectors.get(proto)

    def all(self) -> dict[CollectorProtocol, ProtocolCollector]:
        return dict(self._collectors)

    def __iter__(self) -> Iterator[ProtocolCollector]:
        return iter(self._collectors.values())

    def __len__(self) -> int:
        return len(self._collectors)

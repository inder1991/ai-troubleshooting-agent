"""LLDP/CDP discovery adapter for neighbor detection."""

from __future__ import annotations

import logging
from typing import AsyncIterator, Dict, List, Optional

from .adapter import DiscoveryAdapter
from .observation import DiscoveryObservation, ObservationType

logger = logging.getLogger(__name__)

# Confidence scores per protocol
_CONFIDENCE = {
    "lldp": 0.95,
    "cdp": 0.90,
}
_DEFAULT_CONFIDENCE = 0.85


class LLDPDiscoveryAdapter(DiscoveryAdapter):
    """Discovers device neighbors via LLDP/CDP.

    In mock mode (``mock_neighbors`` provided), yields observations from
    the supplied dictionary.  In production mode, logs a placeholder
    message — real SNMP/CLI collection is not yet implemented.
    """

    def __init__(self, mock_neighbors: Optional[Dict[str, List[dict]]] = None) -> None:
        self._mock_neighbors = mock_neighbors

    def supports(self, target: dict) -> bool:
        """Return True for device-type targets."""
        return target.get("type") == "device"

    async def discover(self, target: dict) -> AsyncIterator[DiscoveryObservation]:
        """Yield NEIGHBOR observations for each LLDP/CDP neighbor of a device."""
        device_id: str = target.get("device_id", "unknown")

        if self._mock_neighbors is not None:
            neighbors = self._mock_neighbors.get(device_id, [])
            for neighbor in neighbors:
                protocol = neighbor.get("protocol", "lldp")
                confidence = _CONFIDENCE.get(protocol, _DEFAULT_CONFIDENCE)
                yield DiscoveryObservation(
                    observation_type=ObservationType.NEIGHBOR,
                    source="lldp",
                    device_id=device_id,
                    confidence=confidence,
                    data={
                        "local_interface": neighbor.get("local_interface"),
                        "remote_device": neighbor.get("remote_device"),
                        "remote_interface": neighbor.get("remote_interface"),
                        "remote_ip": neighbor.get("remote_ip"),
                        "protocol": protocol,
                        "chassis_id": neighbor.get("chassis_id"),
                    },
                )
        else:
            logger.info(
                "Production LLDP/CDP discovery not yet implemented for %s",
                device_id,
            )

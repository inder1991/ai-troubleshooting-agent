"""Auto-discovery scheduler — discovers network neighbors via LLDP/CDP/ARP.

Production: SNMP walks against LLDP-MIB, CISCO-CDP-MIB, IP-MIB.
Current: Mock discovery that returns realistic neighbor data.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any
from src.config import is_demo_mode
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Mock neighbor database — represents what LLDP/CDP/ARP would discover
MOCK_NEIGHBORS = {
    "rtr-core-01": [
        {"local_port": "Te1/0/1", "remote_device": "pa-core-fw-01", "remote_port": "ethernet1/5", "protocol": "LLDP", "remote_ip": "10.0.0.9"},
        {"local_port": "Te1/0/2", "remote_device": "rtr-core-02", "remote_port": "Te1/0/2", "protocol": "CDP", "remote_ip": "10.0.0.30"},
        {"local_port": "Te1/0/3", "remote_device": "rtr-dc-edge-01", "remote_port": "Gi0/0/0", "protocol": "CDP", "remote_ip": "10.0.0.33"},
        {"local_port": "Gi0/0/1", "remote_device": "sw-access-01", "remote_port": "Te1/1/1", "protocol": "LLDP", "remote_ip": "10.1.10.2"},
    ],
    "rtr-core-02": [
        {"local_port": "Te1/0/2", "remote_device": "rtr-core-01", "remote_port": "Te1/0/2", "protocol": "CDP", "remote_ip": "10.0.0.29"},
        {"local_port": "Te1/0/3", "remote_device": "rtr-dc-edge-02", "remote_port": "Gi0/0/0", "protocol": "CDP", "remote_ip": "10.0.0.37"},
    ],
    "sw-access-01": [
        {"local_port": "Te1/1/1", "remote_device": "rtr-core-01", "remote_port": "Gi0/0/1", "protocol": "LLDP", "remote_ip": "10.1.10.2"},
        {"local_port": "Gi1/0/48", "remote_device": "f5-lb-01", "remote_port": "1.2", "protocol": "LLDP", "remote_ip": "10.1.10.100"},
    ],
    "pa-core-fw-01": [
        {"local_port": "ethernet1/1", "remote_device": "cp-perim-fw-01", "remote_port": "eth3", "protocol": "LLDP", "remote_ip": "10.0.0.2"},
        {"local_port": "ethernet1/5", "remote_device": "rtr-core-01", "remote_port": "Te1/0/1", "protocol": "LLDP", "remote_ip": "10.0.0.10"},
    ],
}


async def discover_device_neighbors(device_id: str) -> list[dict]:
    """Discover neighbors for a device (mock LLDP/CDP/ARP)."""
    if is_demo_mode():
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return MOCK_NEIGHBORS.get(device_id, [])
    else:
        # Real discovery via SNMP LLDP/CDP walks
        # TODO: Implement real SNMP walks
        logger.debug("Real discovery not yet implemented for %s", device_id)
        return []


class DiscoveryScheduler:
    """Periodically discovers network topology via LLDP/CDP/ARP."""

    def __init__(self, interval_seconds: int = 300):
        self.interval = interval_seconds
        self._devices: list[dict] = []
        self._last_results: dict[str, list[dict]] = {}
        self._candidates: list[dict] = []
        self._running = False

    def set_devices(self, devices: list[dict]) -> None:
        self._devices = devices

    async def start(self) -> None:
        self._running = True
        logger.info("Discovery scheduler started (interval: %ds)", self.interval)
        while self._running:
            await self._run_discovery()
            await asyncio.sleep(self.interval)

    async def _run_discovery(self) -> None:
        known_ids = {d["id"] for d in self._devices}
        all_neighbors: dict[str, list[dict]] = {}
        new_candidates: list[dict] = []

        for device in self._devices:
            neighbors = await discover_device_neighbors(device["id"])
            all_neighbors[device["id"]] = neighbors

            for n in neighbors:
                if n["remote_device"] not in known_ids:
                    new_candidates.append({
                        "discovered_via": device["id"],
                        "remote_device": n["remote_device"],
                        "remote_ip": n.get("remote_ip", ""),
                        "remote_port": n.get("remote_port", ""),
                        "protocol": n.get("protocol", ""),
                    })

        self._last_results = all_neighbors
        self._candidates = new_candidates
        if new_candidates:
            logger.info("Discovery found %d new candidate devices", len(new_candidates))

    def get_results(self) -> dict:
        return {"neighbors": self._last_results, "total_links": sum(len(v) for v in self._last_results.values())}

    def get_candidates(self) -> list[dict]:
        return self._candidates

    def stop(self) -> None:
        self._running = False

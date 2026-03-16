"""BFS network crawler — expand topology from seed devices."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional

from .adapter import DiscoveryAdapter
from .observation import ObservationType
from .observation_handler import ObservationHandler

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    """Aggregated result of a BFS crawl run."""

    devices_discovered: int = 0
    links_discovered: int = 0
    max_depth_reached: int = 0
    errors: list[dict] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)


def _ip_in_cidrs(ip: str, cidrs: list[str]) -> bool:
    """Return True if *ip* falls within any of the given CIDR ranges."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


class NetworkCrawler:
    """Breadth-first network crawler that expands topology from seed devices.

    Args:
        adapters: Discovery adapters to use for each target.
        handler: ObservationHandler that persists discovered observations.
    """

    def __init__(
        self,
        adapters: List[DiscoveryAdapter],
        handler: ObservationHandler,
    ) -> None:
        self._adapters = adapters
        self._handler = handler

    async def crawl(
        self,
        seeds: List[dict],
        max_depth: int = 5,
        max_devices: int = 1000,
        allowed_cidrs: Optional[List[str]] = None,
        rate_limit: float = 0.0,
    ) -> CrawlResult:
        """BFS crawl starting from *seeds*.

        Args:
            seeds: List of target dicts (e.g. ``{"type": "device", "device_id": "rtr-01"}``).
            max_depth: Maximum BFS depth (0 = seed only).
            max_devices: Stop after discovering this many devices.
            allowed_cidrs: If set, only enqueue neighbors whose remote_ip
                falls within one of these CIDR ranges.
            rate_limit: Seconds to sleep between device discoveries (0 = no limit).

        Returns:
            A :class:`CrawlResult` summarising the crawl.
        """
        result = CrawlResult()

        # BFS queue: (target_dict, depth)
        queue: deque[tuple[dict, int]] = deque()
        visited: set[str] = set()

        # Seed the queue
        for seed in seeds:
            queue.append((seed, 0))

        while queue:
            target, depth = queue.popleft()

            device_key = target.get("device_id", "")
            if not device_key:
                continue

            # Skip already-visited
            if device_key in visited:
                continue

            # Depth guard
            if depth > max_depth:
                continue

            # Max devices guard
            if result.devices_discovered >= max_devices:
                break

            # Mark visited
            visited.add(device_key)
            result.devices_discovered += 1
            result.devices.append(device_key)
            if depth > result.max_depth_reached:
                result.max_depth_reached = depth

            # Rate limiting
            if rate_limit > 0 and result.devices_discovered > 1:
                await asyncio.sleep(rate_limit)

            # Run each adapter that supports this target
            for adapter in self._adapters:
                if not adapter.supports(target):
                    continue

                try:
                    async for obs in adapter.discover(target):
                        # Persist the observation
                        self._handler.handle(obs)

                        # If NEIGHBOR, enqueue the remote device
                        if obs.observation_type == ObservationType.NEIGHBOR:
                            result.links_discovered += 1

                            remote_device = obs.data.get("remote_device")
                            remote_ip = obs.data.get("remote_ip")

                            link_info = {
                                "local_device": device_key,
                                "remote_device": remote_device or "",
                                "remote_ip": remote_ip or "",
                            }
                            result.links.append(link_info)

                            if remote_device and remote_device not in visited:
                                # CIDR filter
                                if allowed_cidrs and remote_ip:
                                    if not _ip_in_cidrs(remote_ip, allowed_cidrs):
                                        continue

                                neighbor_target = {
                                    "type": "device",
                                    "device_id": remote_device,
                                }
                                if remote_ip:
                                    neighbor_target["ip"] = remote_ip

                                queue.append((neighbor_target, depth + 1))

                except Exception as exc:  # noqa: BLE001
                    error_info = {
                        "device": device_key,
                        "adapter": type(adapter).__name__,
                        "error": str(exc),
                    }
                    result.errors.append(error_info)
                    logger.warning(
                        "Adapter %s failed for %s: %s",
                        type(adapter).__name__,
                        device_key,
                        exc,
                    )

        return result

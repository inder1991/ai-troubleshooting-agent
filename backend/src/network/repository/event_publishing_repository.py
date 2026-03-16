"""EventPublishingRepository — decorator that publishes topology events on writes.

Wraps any ``TopologyRepository`` implementation and transparently publishes
events to an ``EventBus`` whenever a write method mutates the topology graph.
Read and graph-query methods are delegated unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..event_bus.base import EventBus
from ..event_bus.topology_channels import (
    DEVICE_CHANGED,
    INTERFACE_CHANGED,
    LINK_DISCOVERED,
    ROUTE_CHANGED,
    POLICY_CHANGED,
    STALE_DETECTED,
    EventType,
    make_device_event,
    make_interface_event,
    make_link_event,
    make_route_event,
    make_stale_event,
)
from .domain import (
    Device,
    Interface,
    IPAddress,
    NeighborLink,
    Route,
    SecurityPolicy,
)
from .interface import TopologyRepository

logger = logging.getLogger(__name__)


class EventPublishingRepository(TopologyRepository):
    """Decorator that publishes topology events after successful writes.

    All read methods and graph-query methods delegate directly to the
    wrapped ``inner`` repository.  Write methods delegate first, then
    publish a corresponding event to the ``event_bus``.
    """

    def __init__(self, inner: TopologyRepository, event_bus: EventBus) -> None:
        self._inner = inner
        self._bus = event_bus

    # ── Event publishing helper ───────────────────────────────────────────

    def _publish(self, channel: str, event_dict: dict) -> None:
        """Fire-and-forget publish that works whether or not a loop is running."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._bus.publish(channel, event_dict))
            else:
                loop.run_until_complete(self._bus.publish(channel, event_dict))
        except RuntimeError:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._bus.publish(channel, event_dict))
            except Exception as e:
                logger.warning("Event publish failed: %s", e)
        except Exception as e:
            logger.warning("Event publish failed: %s", e)

    # ── Read methods (delegate unchanged) ─────────────────────────────────

    def get_device(self, device_id: str) -> Optional[Device]:
        return self._inner.get_device(device_id)

    def get_devices(
        self, site_id: str = None, device_type: str = None
    ) -> list[Device]:
        return self._inner.get_devices(site_id=site_id, device_type=device_type)

    def get_interfaces(self, device_id: str) -> list[Interface]:
        return self._inner.get_interfaces(device_id)

    def get_ip_addresses(self, interface_id: str) -> list[IPAddress]:
        return self._inner.get_ip_addresses(interface_id)

    def get_routes(
        self, device_id: str, vrf_instance_id: str = None
    ) -> list[Route]:
        return self._inner.get_routes(device_id, vrf_instance_id=vrf_instance_id)

    def get_neighbors(self, device_id: str) -> list[NeighborLink]:
        return self._inner.get_neighbors(device_id)

    def get_security_policies(self, device_id: str) -> list[SecurityPolicy]:
        return self._inner.get_security_policies(device_id)

    def find_device_by_ip(self, ip: str) -> Optional[Device]:
        return self._inner.find_device_by_ip(ip)

    def find_device_by_serial(self, serial: str) -> Optional[Device]:
        return self._inner.find_device_by_serial(serial)

    def find_device_by_hostname(self, hostname: str) -> Optional[Device]:
        return self._inner.find_device_by_hostname(hostname)

    # ── Write methods (delegate, then publish) ────────────────────────────

    def upsert_device(self, device: Device) -> Device:
        result = self._inner.upsert_device(device)
        event = make_device_event(
            device_id=device.id,
            event_type=EventType.UPDATED,
            source="event_publishing_repository",
        )
        self._publish(DEVICE_CHANGED, event.to_dict())
        return result

    def upsert_interface(self, interface: Interface) -> Interface:
        result = self._inner.upsert_interface(interface)
        event = make_interface_event(
            interface_id=interface.id,
            event_type=EventType.UPDATED,
            source="event_publishing_repository",
        )
        self._publish(INTERFACE_CHANGED, event.to_dict())
        return result

    def upsert_ip_address(self, ip_address: IPAddress) -> IPAddress:
        # Delegate only — no event for IP address changes
        return self._inner.upsert_ip_address(ip_address)

    def upsert_neighbor_link(self, link: NeighborLink) -> NeighborLink:
        result = self._inner.upsert_neighbor_link(link)
        event = make_link_event(
            link_id=link.id,
            event_type=EventType.UPDATED,
            source="event_publishing_repository",
        )
        self._publish(LINK_DISCOVERED, event.to_dict())
        return result

    def upsert_route(self, route: Route) -> Route:
        result = self._inner.upsert_route(route)
        event = make_route_event(
            route_id=route.id,
            event_type=EventType.UPDATED,
            source="event_publishing_repository",
        )
        self._publish(ROUTE_CHANGED, event.to_dict())
        return result

    def upsert_security_policy(self, policy: SecurityPolicy) -> SecurityPolicy:
        result = self._inner.upsert_security_policy(policy)
        event = make_device_event(
            device_id=policy.id,
            event_type=EventType.UPDATED,
            source="event_publishing_repository",
        )
        # Use POLICY_CHANGED channel (factory creates a device-typed event,
        # but the channel is what matters for routing; override entity_type)
        event_dict = event.to_dict()
        event_dict["entity_type"] = "policy"
        self._publish(POLICY_CHANGED, event_dict)
        return result

    def mark_stale(self, entity_type: str, entity_id: str) -> None:
        self._inner.mark_stale(entity_type, entity_id)
        event = make_stale_event(
            entity_type=entity_type,
            entity_id=entity_id,
        )
        self._publish(STALE_DETECTED, event.to_dict())

    # ── Graph query methods (delegate unchanged) ──────────────────────────

    def find_paths(
        self, src_ip: str, dst_ip: str, vrf: str = "default", k: int = 3
    ) -> list[dict]:
        return self._inner.find_paths(src_ip, dst_ip, vrf=vrf, k=k)

    def blast_radius(self, device_id: str) -> dict:
        return self._inner.blast_radius(device_id)

    def get_topology_export(self, site_id: str = None) -> dict:
        return self._inner.get_topology_export(site_id=site_id)

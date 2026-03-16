"""ObservationHandler — routes DiscoveryObservations to repo upserts.

Each observation type is dispatched to a private ``_handle_<type>`` method
that builds the appropriate domain entity and calls ``repo.upsert_*``.
Unknown or not-yet-implemented types are logged and silently ignored.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .observation import DiscoveryObservation, ObservationType
from ..repository.domain import Device, Interface, NeighborLink, Route

if TYPE_CHECKING:
    from ..repository.interface import TopologyRepository
    from .entity_resolver import EntityResolver

logger = logging.getLogger(__name__)


class ObservationHandler:
    """Consume DiscoveryObservation instances and persist them as domain entities."""

    def __init__(self, repo: "TopologyRepository", resolver: "EntityResolver") -> None:
        self._repo = repo
        self._resolver = resolver

        self._dispatch = {
            ObservationType.DEVICE: self._handle_device,
            ObservationType.INTERFACE: self._handle_interface,
            ObservationType.NEIGHBOR: self._handle_neighbor,
            ObservationType.ROUTE: self._handle_route,
        }

    # ── Public API ───────────────────────────────────────────────────────

    def handle(self, obs: DiscoveryObservation) -> None:
        """Route *obs* to the appropriate handler, or log & skip."""
        handler = self._dispatch.get(obs.observation_type)
        if handler is None:
            logger.debug(
                "No handler for observation type %s — skipping",
                obs.observation_type,
            )
            return
        handler(obs)

    # ── Type-specific handlers ───────────────────────────────────────────

    def _handle_device(self, obs: DiscoveryObservation) -> None:
        data = obs.data
        device_id = self._resolver.resolve_device(data)
        now = datetime.now(timezone.utc)
        confidence = self._resolver.get_confidence(obs.source)

        device = Device(
            id=device_id,
            hostname=data.get("hostname", ""),
            vendor=data.get("vendor", ""),
            model=data.get("model", ""),
            serial=data.get("serial", ""),
            device_type=data.get("device_type", "unknown"),
            site_id=data.get("site_id", ""),
            sources=[obs.source],
            first_seen=now,
            last_seen=now,
            confidence=confidence,
        )
        self._repo.upsert_device(device)

    def _handle_interface(self, obs: DiscoveryObservation) -> None:
        data = obs.data
        device_id = obs.device_id
        iface_name = data.get("name", "")
        iface_id = self._resolver.resolve_interface(device_id, iface_name)
        now = datetime.now(timezone.utc)
        confidence = self._resolver.get_confidence(obs.source)

        interface = Interface(
            id=iface_id,
            device_id=device_id,
            name=iface_name,
            sources=[obs.source],
            first_seen=now,
            last_seen=now,
            confidence=confidence,
            admin_state=data.get("admin_state", "up"),
            oper_state=data.get("oper_state", "up"),
            speed=data.get("speed"),
            mtu=data.get("mtu"),
            mac=data.get("mac"),
            duplex=data.get("duplex"),
            description=data.get("description"),
        )
        self._repo.upsert_interface(interface)

    def _handle_neighbor(self, obs: DiscoveryObservation) -> None:
        data = obs.data
        device_id = obs.device_id
        remote_device = data.get("remote_device", "")
        local_iface = data.get("local_interface", "")
        remote_iface = data.get("remote_interface", "")
        protocol = data.get("protocol", obs.source)
        now = datetime.now(timezone.utc)
        confidence = self._resolver.get_confidence(obs.source)

        local_iface_id = self._resolver.resolve_interface(device_id, local_iface)
        remote_iface_id = self._resolver.resolve_interface(remote_device, remote_iface)
        link_id = f"{local_iface_id}--{remote_iface_id}"

        link = NeighborLink(
            id=link_id,
            device_id=device_id,
            local_interface=local_iface_id,
            remote_device=remote_device,
            remote_interface=remote_iface_id,
            protocol=protocol,
            sources=[obs.source],
            first_seen=now,
            last_seen=now,
            confidence=confidence,
        )
        self._repo.upsert_neighbor_link(link)

    def _handle_route(self, obs: DiscoveryObservation) -> None:
        data = obs.data
        device_id = obs.device_id
        dest_cidr = data.get("destination_cidr", "0.0.0.0/0")
        now = datetime.now(timezone.utc)
        confidence = self._resolver.get_confidence(obs.source)

        prefix_len = 0
        if "/" in dest_cidr:
            try:
                prefix_len = int(dest_cidr.split("/")[1])
            except (ValueError, IndexError):
                pass

        route_id = f"{device_id}:{data.get('vrf', 'default')}:{dest_cidr}"

        route = Route(
            id=route_id,
            device_id=device_id,
            vrf_instance_id=data.get("vrf", "default"),
            destination_cidr=dest_cidr,
            prefix_len=prefix_len,
            protocol=data.get("protocol", "static"),
            sources=[obs.source],
            first_seen=now,
            last_seen=now,
            next_hop_type=data.get("next_hop_type"),
            next_hop_refs=data.get("next_hop_refs", []),
        )
        self._repo.upsert_route(route)

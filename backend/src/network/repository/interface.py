"""Abstract repository interface for the network topology domain.

TopologyRepository defines the contract that any persistence back-end
(SQLite, Neo4j, in-memory, etc.) must implement to store and query the
unified network topology graph.  All concrete implementations must
subclass this ABC and provide every abstract method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .domain import (
    Device,
    Interface,
    IPAddress,
    NeighborLink,
    Route,
    SecurityPolicy,
)


class TopologyRepository(ABC):
    """Abstract base class for topology persistence backends.

    Concrete implementations are responsible for storing devices,
    interfaces, IP addresses, neighbor links, routes, and security
    policies — and for answering graph-oriented queries such as
    path-finding and blast-radius analysis.
    """

    # ── Read methods ─────────────────────────────────────────────────────

    @abstractmethod
    def get_device(self, device_id: str) -> Optional[Device]:
        """Return a single device by its unique ID, or None."""
        ...

    @abstractmethod
    def get_devices(
        self, site_id: str = None, device_type: str = None
    ) -> list[Device]:
        """Return devices, optionally filtered by site and/or type."""
        ...

    @abstractmethod
    def get_interfaces(self, device_id: str) -> list[Interface]:
        """Return all interfaces belonging to a device."""
        ...

    @abstractmethod
    def get_ip_addresses(self, interface_id: str) -> list[IPAddress]:
        """Return all IP addresses assigned to an interface."""
        ...

    @abstractmethod
    def get_routes(
        self, device_id: str, vrf_instance_id: str = None
    ) -> list[Route]:
        """Return routing-table entries for a device, optionally within a VRF."""
        ...

    @abstractmethod
    def get_neighbors(self, device_id: str) -> list[NeighborLink]:
        """Return discovered neighbor adjacencies for a device."""
        ...

    @abstractmethod
    def get_security_policies(self, device_id: str) -> list[SecurityPolicy]:
        """Return firewall / ACL rules installed on a device."""
        ...

    @abstractmethod
    def find_device_by_ip(self, ip: str) -> Optional[Device]:
        """Resolve an IP address to the device that owns it."""
        ...

    @abstractmethod
    def find_device_by_serial(self, serial: str) -> Optional[Device]:
        """Look up a device by its serial number."""
        ...

    @abstractmethod
    def find_device_by_hostname(self, hostname: str) -> Optional[Device]:
        """Look up a device by its hostname."""
        ...

    # ── Write methods ────────────────────────────────────────────────────

    @abstractmethod
    def upsert_device(self, device: Device) -> Device:
        """Insert or update a device, returning the persisted entity."""
        ...

    @abstractmethod
    def upsert_interface(self, interface: Interface) -> Interface:
        """Insert or update an interface, returning the persisted entity."""
        ...

    @abstractmethod
    def upsert_ip_address(self, ip_address: IPAddress) -> IPAddress:
        """Insert or update an IP address, returning the persisted entity."""
        ...

    @abstractmethod
    def upsert_neighbor_link(self, link: NeighborLink) -> NeighborLink:
        """Insert or update a neighbor link, returning the persisted entity."""
        ...

    @abstractmethod
    def upsert_route(self, route: Route) -> Route:
        """Insert or update a route, returning the persisted entity."""
        ...

    @abstractmethod
    def upsert_security_policy(self, policy: SecurityPolicy) -> SecurityPolicy:
        """Insert or update a security policy, returning the persisted entity."""
        ...

    @abstractmethod
    def mark_stale(self, entity_type: str, entity_id: str) -> None:
        """Flag an entity as stale (no longer seen by any active source)."""
        ...

    # ── Graph query methods ──────────────────────────────────────────────

    @abstractmethod
    def find_paths(
        self, src_ip: str, dst_ip: str, vrf: str = "default", k: int = 3
    ) -> list[dict]:
        """Return up to *k* forwarding paths between two IP addresses."""
        ...

    @abstractmethod
    def blast_radius(self, device_id: str) -> dict:
        """Compute the blast radius if the given device fails."""
        ...

    @abstractmethod
    def get_topology_export(self, site_id: str = None) -> dict:
        """Export the topology graph, optionally scoped to a site."""
        ...

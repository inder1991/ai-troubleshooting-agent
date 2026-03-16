"""SQLiteRepository — wraps the existing TopologyStore behind TopologyRepository.

This adapter converts between the Pydantic models used by TopologyStore and
the pure-dataclass domain models defined in ``domain.py``.  It does **not**
replace TopologyStore; it delegates all persistence to it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..topology_store import TopologyStore
from ..models import (
    Device as PydanticDevice,
    DeviceType,
    Interface as PydanticInterface,
    Route as PydanticRoute,
    FirewallRule as PydanticFirewallRule,
    PolicyAction,
)
from .interface import TopologyRepository
from .domain import (
    Device,
    Interface,
    IPAddress,
    NeighborLink,
    Route,
    SecurityPolicy,
)


class SQLiteRepository(TopologyRepository):
    """TopologyRepository backed by the existing SQLite TopologyStore."""

    def __init__(self, store: TopologyStore) -> None:
        self._store = store

    # ── Conversion helpers ────────────────────────────────────────────────

    @staticmethod
    def _parse_datetime(value: str | datetime | None) -> datetime:
        """Convert a string or None into a datetime object."""
        if isinstance(value, datetime):
            return value
        if value:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _strip_cidr(ip_with_cidr: str) -> str:
        """Strip CIDR prefix from an IP string, e.g. '10.0.0.1/30' → '10.0.0.1'."""
        if "/" in ip_with_cidr:
            return ip_with_cidr.split("/")[0]
        return ip_with_cidr

    def _to_domain_device(self, pdev: PydanticDevice) -> Device:
        """Convert a Pydantic Device to a domain Device."""
        return Device(
            id=pdev.id,
            hostname=pdev.name,
            vendor=pdev.vendor or "",
            model=pdev.model or "",
            serial=pdev.serial_number or "",
            device_type=pdev.device_type.value if isinstance(pdev.device_type, DeviceType) else str(pdev.device_type),
            site_id=pdev.site_id or "",
            sources=["topology_store"],
            first_seen=self._parse_datetime(pdev.discovered_at),
            last_seen=self._parse_datetime(pdev.last_seen),
            confidence=0.9,
        )

    def _to_domain_interface(self, piface: PydanticInterface) -> Interface:
        """Convert a Pydantic Interface to a domain Interface."""
        now = datetime.now(timezone.utc)
        return Interface(
            id=piface.id,
            device_id=piface.device_id,
            name=piface.name or "",
            sources=["topology_store"],
            first_seen=now,
            last_seen=now,
            confidence=0.9,
            mac=piface.mac or None,
            admin_state=piface.admin_status or "up",
            oper_state=piface.oper_status or "up",
            speed=piface.speed or None,
            mtu=piface.mtu if piface.mtu else None,
            duplex=piface.duplex or None,
            port_channel_id=piface.channel_group or None,
            description=piface.description or None,
            vrf_instance_id=piface.vrf or None,
        )

    def _to_domain_route(self, proute: PydanticRoute) -> Route:
        """Convert a Pydantic Route to a domain Route."""
        # Extract prefix length from destination_cidr
        prefix_len = 0
        if "/" in proute.destination_cidr:
            try:
                prefix_len = int(proute.destination_cidr.split("/")[1])
            except (ValueError, IndexError):
                pass

        now = datetime.now(timezone.utc)
        return Route(
            id=proute.id,
            device_id=proute.device_id,
            vrf_instance_id=proute.vrf or "default",
            destination_cidr=proute.destination_cidr,
            prefix_len=prefix_len,
            protocol=proute.protocol or "static",
            sources=["topology_store"],
            first_seen=self._parse_datetime(proute.last_updated),
            last_seen=self._parse_datetime(proute.last_updated),
            metric=proute.metric if proute.metric else None,
            next_hop_type="ip" if proute.next_hop else None,
            next_hop_refs=[{"ip": proute.next_hop}] if proute.next_hop else [],
        )

    def _to_domain_security_policy(self, rule: PydanticFirewallRule) -> SecurityPolicy:
        """Convert a Pydantic FirewallRule to a domain SecurityPolicy."""
        now = datetime.now(timezone.utc)
        action_val = rule.action.value if isinstance(rule.action, PolicyAction) else str(rule.action)
        return SecurityPolicy(
            id=rule.id,
            device_id=rule.device_id,
            rule_order=rule.order,
            name=rule.rule_name or "",
            action=action_val,
            sources=["topology_store"],
            first_seen=now,
            last_seen=now,
            src_zone=rule.src_zone or None,
            dst_zone=rule.dst_zone or None,
            src_ip=",".join(rule.src_ips) if rule.src_ips else None,
            dst_ip=",".join(rule.dst_ips) if rule.dst_ips else None,
            dst_port_range=",".join(str(p) for p in rule.ports) if rule.ports else None,
            protocol=rule.protocol or None,
            log=rule.logged,
        )

    def _to_pydantic_device(self, device: Device) -> PydanticDevice:
        """Convert a domain Device to a Pydantic Device for store persistence."""
        try:
            dt = DeviceType(device.device_type)
        except ValueError:
            dt = DeviceType.HOST
        return PydanticDevice(
            id=device.id,
            name=device.hostname,
            vendor=device.vendor,
            device_type=dt,
            model=device.model,
            serial_number=device.serial,
            site_id=device.site_id,
            discovered_at=device.first_seen.isoformat() if isinstance(device.first_seen, datetime) else str(device.first_seen),
            last_seen=device.last_seen.isoformat() if isinstance(device.last_seen, datetime) else str(device.last_seen),
        )

    def _to_pydantic_interface(self, iface: Interface) -> PydanticInterface:
        """Convert a domain Interface to a Pydantic Interface for store persistence."""
        return PydanticInterface(
            id=iface.id,
            device_id=iface.device_id,
            name=iface.name,
            mac=iface.mac or "",
            speed=iface.speed or "",
            admin_status=iface.admin_state,
            oper_status=iface.oper_state,
            mtu=iface.mtu or 0,
            duplex=iface.duplex or "",
            description=iface.description or "",
            channel_group=iface.port_channel_id or "",
            vrf=iface.vrf_instance_id or "",
        )

    # ── Read methods ─────────────────────────────────────────────────────

    def get_device(self, device_id: str) -> Optional[Device]:
        pdev = self._store.get_device(device_id)
        if pdev is None:
            return None
        return self._to_domain_device(pdev)

    def get_devices(
        self, site_id: str = None, device_type: str = None
    ) -> list[Device]:
        all_pydantic = self._store.list_devices()
        results = []
        for pdev in all_pydantic:
            if site_id and (pdev.site_id or "") != site_id:
                continue
            dt_val = pdev.device_type.value if isinstance(pdev.device_type, DeviceType) else str(pdev.device_type)
            if device_type and dt_val != device_type:
                continue
            results.append(self._to_domain_device(pdev))
        return results

    def get_interfaces(self, device_id: str) -> list[Interface]:
        pydantic_ifaces = self._store.list_interfaces(device_id=device_id)
        return [self._to_domain_interface(pi) for pi in pydantic_ifaces]

    def get_ip_addresses(self, interface_id: str) -> list[IPAddress]:
        # Current schema stores IP directly on the interface row.
        # We find the interface and extract the IP from it.
        all_ifaces = self._store.list_interfaces()
        for pi in all_ifaces:
            if pi.id == interface_id and pi.ip:
                ip_str = self._strip_cidr(pi.ip)
                now = datetime.now(timezone.utc)
                return [IPAddress(
                    id=f"{interface_id}:{ip_str}",
                    ip=ip_str,
                    assigned_to=interface_id,
                    sources=["topology_store"],
                    first_seen=now,
                    last_seen=now,
                    confidence=0.9,
                )]
        return []

    def get_routes(
        self, device_id: str, vrf_instance_id: str = None
    ) -> list[Route]:
        pydantic_routes = self._store.list_routes(device_id=device_id)
        results = [self._to_domain_route(pr) for pr in pydantic_routes]
        if vrf_instance_id:
            results = [r for r in results if r.vrf_instance_id == vrf_instance_id]
        return results

    def get_neighbors(self, device_id: str) -> list[NeighborLink]:
        # Task 4 adds the neighbor links table
        return []

    def get_security_policies(self, device_id: str) -> list[SecurityPolicy]:
        pydantic_rules = self._store.list_firewall_rules(device_id=device_id)
        return [self._to_domain_security_policy(r) for r in pydantic_rules]

    def find_device_by_ip(self, ip: str) -> Optional[Device]:
        # 1. Search management_ip first
        all_devices = self._store.list_devices()
        for pdev in all_devices:
            if pdev.management_ip and pdev.management_ip == ip:
                return self._to_domain_device(pdev)

        # 2. Search interface IPs (strip CIDR before comparing)
        all_ifaces = self._store.list_interfaces()
        for pi in all_ifaces:
            if pi.ip and self._strip_cidr(pi.ip) == ip:
                # Found — now get the device
                pdev = self._store.get_device(pi.device_id)
                if pdev:
                    return self._to_domain_device(pdev)

        return None

    def find_device_by_serial(self, serial: str) -> Optional[Device]:
        all_devices = self._store.list_devices()
        for pdev in all_devices:
            if pdev.serial_number and pdev.serial_number == serial:
                return self._to_domain_device(pdev)
        return None

    def find_device_by_hostname(self, hostname: str) -> Optional[Device]:
        all_devices = self._store.list_devices()
        for pdev in all_devices:
            if pdev.name and pdev.name == hostname:
                return self._to_domain_device(pdev)
        return None

    # ── Write methods ────────────────────────────────────────────────────

    def upsert_device(self, device: Device) -> Device:
        pdev = self._to_pydantic_device(device)
        self._store.add_device(pdev)
        return device

    def upsert_interface(self, interface: Interface) -> Interface:
        piface = self._to_pydantic_interface(interface)
        self._store.add_interface(piface)
        return interface

    def upsert_ip_address(self, ip_address: IPAddress) -> IPAddress:
        # IP is stored on the interface in the current schema — pass-through
        return ip_address

    def upsert_neighbor_link(self, link: NeighborLink) -> NeighborLink:
        # Task 4 adds the neighbor links table
        return link

    def upsert_route(self, route: Route) -> Route:
        next_hop = ""
        if route.next_hop_refs:
            next_hop = route.next_hop_refs[0].get("ip", "")
        proute = PydanticRoute(
            id=route.id,
            device_id=route.device_id,
            destination_cidr=route.destination_cidr,
            next_hop=next_hop,
            metric=route.metric or 0,
            protocol=route.protocol,
            vrf=route.vrf_instance_id or "",
        )
        self._store.add_route(proute)
        return route

    def upsert_security_policy(self, policy: SecurityPolicy) -> SecurityPolicy:
        # Not directly supported by current store schema mapping — pass-through
        return policy

    def mark_stale(self, entity_type: str, entity_id: str) -> None:
        # Not supported yet
        pass

    # ── Graph query stubs ────────────────────────────────────────────────

    def find_paths(
        self, src_ip: str, dst_ip: str, vrf: str = "default", k: int = 3
    ) -> list[dict]:
        return []

    def blast_radius(self, device_id: str) -> dict:
        return {}

    def get_topology_export(self, site_id: str = None) -> dict:
        return {}

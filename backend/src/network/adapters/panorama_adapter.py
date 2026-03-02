"""Palo Alto Panorama / PAN-OS firewall adapter.

Uses the pan-os-python SDK to fetch security policies, NAT rules, zones,
interfaces, routes, and virtual routers from Panorama-managed devices or
standalone PAN-OS firewalls.

All panos imports are wrapped in try/except so the module can be imported
even without pan-os-python installed (graceful degradation).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Optional

from .base import FirewallAdapter, DeviceInterface, VirtualRouter
from ..models import (
    PolicyVerdict, FirewallVendor, FirewallRule, NATRule, Zone, Route,
    PolicyAction, VerdictMatchType, NATDirection,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful import of pan-os-python SDK
# ---------------------------------------------------------------------------
try:
    import panos
    import panos.panorama
    import panos.firewall
    import panos.policies
    import panos.network
    import panos.objects
    HAS_PANOS = True
except ImportError:
    panos = None  # type: ignore[assignment]
    HAS_PANOS = False

# ---------------------------------------------------------------------------
# Well-known Palo Alto application-to-port mappings (subset for simulation)
# ---------------------------------------------------------------------------
_APP_PORT_MAP: dict[str, list[int]] = {
    "web-browsing": [80],
    "ssl": [443],
    "dns": [53],
    "ssh": [22],
    "ftp": [21],
    "smtp": [25],
    "ntp": [123],
    "snmp": [161],
    "rdp": [3389],
    "mysql": [3306],
    "ms-sql": [1433],
    "ldap": [389],
    "ldaps": [636],
    "http": [80],
    "https": [443],
    "ping": [],
    "icmp": [],
    "any": [],
}


def _action_from_panos(action_str: str) -> PolicyAction:
    """Map PAN-OS rule action string to our PolicyAction enum."""
    action_lower = (action_str or "").lower()
    if action_lower == "allow":
        return PolicyAction.ALLOW
    if action_lower in ("deny", "reset-client", "reset-server", "reset-both"):
        return PolicyAction.DENY
    if action_lower == "drop":
        return PolicyAction.DROP
    return PolicyAction.DENY


def _stable_id(*parts: str) -> str:
    """Generate a deterministic short ID from key fields."""
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _ports_from_applications(applications: list[str]) -> list[int]:
    """Approximate port list from PAN-OS application names."""
    if not applications or "any" in applications:
        return []
    ports: list[int] = []
    for app in applications:
        mapped = _APP_PORT_MAP.get(app.lower(), [])
        ports.extend(p for p in mapped if p not in ports)
    return ports


def _ports_from_services(services: list[str]) -> list[int]:
    """Extract port numbers from PAN-OS service entries.

    Services can be names like 'application-default' or 'service-http',
    or port-based entries.  We return an empty list for 'any' or
    'application-default' (meaning port matching defers to application).
    """
    if not services or "any" in services or "application-default" in services:
        return []
    ports: list[int] = []
    for svc in services:
        # Try to parse numeric ports (e.g., "tcp/443")
        if "/" in svc:
            try:
                port_str = svc.split("/", 1)[1]
                if "-" in port_str:
                    lo, hi = port_str.split("-", 1)
                    ports.extend(range(int(lo), int(hi) + 1))
                else:
                    ports.append(int(port_str))
            except (ValueError, IndexError):
                pass
    return ports


class PanoramaAdapter(FirewallAdapter):
    """Adapter for Palo Alto Panorama and standalone PAN-OS firewalls.

    Parameters
    ----------
    hostname : str
        Panorama or firewall management IP / FQDN.
    api_key : str
        PAN-OS API key for authentication.
    device_group : str, optional
        Panorama device group name.  When set, rules are fetched from the
        shared/device-group policy; when empty, a direct firewall connection
        is assumed.
    vsys : str
        Virtual system (default ``vsys1``).
    """

    def __init__(
        self,
        hostname: str,
        api_key: str,
        device_group: str = "",
        vsys: str = "vsys1",
    ):
        super().__init__(
            vendor=FirewallVendor.PALO_ALTO,
            api_endpoint=hostname,
            api_key=api_key,
            extra_config={
                "device_group": device_group,
                "vsys": vsys,
            },
        )
        self._device_group = device_group
        self._vsys = vsys
        self._panos_device = None  # lazily created
        self._vr_cache: list[VirtualRouter] = []

    # ------------------------------------------------------------------
    # Lazy connection
    # ------------------------------------------------------------------

    def _connect(self):
        """Lazily create the panos device object.

        Returns a ``panos.panorama.Panorama`` when *device_group* is set,
        otherwise a ``panos.firewall.Firewall``.

        Raises ``NotImplementedError`` if pan-os-python is not installed.
        """
        if not HAS_PANOS:
            raise NotImplementedError(
                "pan-os-python SDK is not installed. "
                "Install it with: pip install pan-os-python"
            )
        if self._panos_device is not None:
            return self._panos_device

        if self._device_group:
            self._panos_device = panos.panorama.Panorama(
                self.api_endpoint, api_key=self.api_key,
            )
        else:
            self._panos_device = panos.firewall.Firewall(
                self.api_endpoint, api_key=self.api_key, vsys=self._vsys,
            )
        return self._panos_device

    # ------------------------------------------------------------------
    # Policy container helper
    # ------------------------------------------------------------------

    def _get_policy_parent(self):
        """Return the panos object from which to fetch policies.

        For Panorama with a device group, returns a ``DeviceGroup`` child.
        For a direct firewall connection, returns the firewall itself.
        """
        device = self._connect()
        if self._device_group:
            dg = panos.panorama.DeviceGroup(self._device_group)
            device.add(dg)
            return dg
        return device

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch security rules from PAN-OS / Panorama."""
        if not HAS_PANOS:
            raise NotImplementedError("pan-os-python SDK is not installed")

        parent = self._get_policy_parent()
        device_id = self.api_endpoint

        def _do_fetch():
            rule_base = panos.policies.SecurityRule.refreshall(parent)
            return rule_base

        raw_rules = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

        rules: list[FirewallRule] = []
        for idx, rule in enumerate(raw_rules):
            name = getattr(rule, "name", f"rule-{idx}")
            src_ips = getattr(rule, "source", ["any"]) or ["any"]
            dst_ips = getattr(rule, "destination", ["any"]) or ["any"]
            src_zone = ""
            dst_zone = ""
            fromzone = getattr(rule, "fromzone", None)
            tozone = getattr(rule, "tozone", None)
            if fromzone and isinstance(fromzone, list) and len(fromzone) > 0:
                src_zone = fromzone[0]
            if tozone and isinstance(tozone, list) and len(tozone) > 0:
                dst_zone = tozone[0]

            # Port resolution: prefer service, fall back to application
            applications = getattr(rule, "application", ["any"]) or ["any"]
            services = getattr(rule, "service", ["application-default"]) or ["application-default"]
            ports = _ports_from_services(services)
            if not ports:
                ports = _ports_from_applications(applications)

            action = _action_from_panos(getattr(rule, "action", "deny"))
            logged = getattr(rule, "log_end", False) or getattr(rule, "log_start", False)

            rules.append(FirewallRule(
                id=_stable_id(device_id, name),
                device_id=device_id,
                rule_name=name,
                src_zone=src_zone,
                dst_zone=dst_zone,
                src_ips=list(src_ips) if src_ips else ["any"],
                dst_ips=list(dst_ips) if dst_ips else ["any"],
                ports=ports,
                protocol="tcp",
                action=action,
                logged=logged,
                order=idx,
            ))

        logger.info("Fetched %d security rules from %s", len(rules), self.api_endpoint)
        return rules

    async def _fetch_nat_rules(self) -> list[NATRule]:
        """Fetch NAT rules from PAN-OS / Panorama."""
        if not HAS_PANOS:
            raise NotImplementedError("pan-os-python SDK is not installed")

        parent = self._get_policy_parent()
        device_id = self.api_endpoint

        def _do_fetch():
            return panos.policies.NatRule.refreshall(parent)

        raw_rules = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

        nat_rules: list[NATRule] = []
        for idx, rule in enumerate(raw_rules):
            name = getattr(rule, "name", f"nat-{idx}")
            # Source translation
            src_translated = getattr(rule, "source_translation_translated_addresses", None)
            dst_translated = getattr(rule, "destination_translated_address", None)
            original_src = getattr(rule, "source", ["any"])
            original_dst = getattr(rule, "destination", ["any"])
            translated_port = getattr(rule, "destination_translated_port", 0)

            # Determine direction
            if dst_translated:
                direction = NATDirection.DNAT
            else:
                direction = NATDirection.SNAT

            nat_rules.append(NATRule(
                id=_stable_id(device_id, name),
                device_id=device_id,
                original_src=original_src[0] if isinstance(original_src, list) and original_src else "",
                original_dst=original_dst[0] if isinstance(original_dst, list) and original_dst else "",
                translated_src=src_translated[0] if isinstance(src_translated, list) and src_translated else "",
                translated_dst=dst_translated if isinstance(dst_translated, str) else "",
                original_port=0,
                translated_port=int(translated_port) if translated_port else 0,
                direction=direction,
                rule_id=name,
                description=getattr(rule, "description", "") or "",
            ))

        logger.info("Fetched %d NAT rules from %s", len(nat_rules), self.api_endpoint)
        return nat_rules

    async def _fetch_zones(self) -> list[Zone]:
        """Fetch security zones from PAN-OS / Panorama."""
        if not HAS_PANOS:
            raise NotImplementedError("pan-os-python SDK is not installed")

        device = self._connect()
        device_id = self.api_endpoint

        def _do_fetch():
            # For Panorama with device group, zones are on template/vsys;
            # for standalone firewall, they're direct children.
            return panos.network.Zone.refreshall(device)

        raw_zones = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

        zones: list[Zone] = []
        for z in raw_zones:
            name = getattr(z, "name", "")
            mode = getattr(z, "mode", "")
            zones.append(Zone(
                id=_stable_id(device_id, name),
                name=name,
                description=f"mode={mode}" if mode else "",
                firewall_id=device_id,
            ))

        logger.info("Fetched %d zones from %s", len(zones), self.api_endpoint)
        return zones

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        """Fetch Ethernet interfaces from PAN-OS / Panorama."""
        if not HAS_PANOS:
            raise NotImplementedError("pan-os-python SDK is not installed")

        device = self._connect()

        def _do_fetch():
            return panos.network.EthernetInterface.refreshall(device)

        raw_ifaces = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

        interfaces: list[DeviceInterface] = []
        for iface in raw_ifaces:
            name = getattr(iface, "name", "")
            ip_addrs = getattr(iface, "ip", None)
            ip_str = ""
            if isinstance(ip_addrs, list) and ip_addrs:
                ip_str = ip_addrs[0]
            elif isinstance(ip_addrs, str):
                ip_str = ip_addrs
            zone_name = getattr(iface, "zone", "") or ""
            comment = getattr(iface, "comment", "") or ""
            link_state = getattr(iface, "link_state", "auto") or "up"

            interfaces.append(DeviceInterface(
                name=name,
                ip=ip_str,
                zone=zone_name,
                status="up" if link_state in ("up", "auto") else "down",
            ))

        logger.info("Fetched %d interfaces from %s", len(interfaces), self.api_endpoint)
        return interfaces

    async def _fetch_routes(self) -> list[Route]:
        """Fetch static routes from all virtual routers."""
        if not HAS_PANOS:
            raise NotImplementedError("pan-os-python SDK is not installed")

        device = self._connect()
        device_id = self.api_endpoint

        def _do_fetch():
            vr_list = panos.network.VirtualRouter.refreshall(device)
            results = []
            for vr in vr_list:
                static_routes = panos.network.StaticRoute.refreshall(vr)
                for sr in static_routes:
                    results.append((vr.name, sr))
            return results

        vr_routes = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

        routes: list[Route] = []
        for vr_name, sr in vr_routes:
            name = getattr(sr, "name", "")
            destination = getattr(sr, "destination", "")
            nexthop = getattr(sr, "nexthop", "") or ""
            interface = getattr(sr, "interface", "") or ""
            metric = getattr(sr, "metric", 10) or 10

            routes.append(Route(
                id=_stable_id(device_id, vr_name, name),
                device_id=device_id,
                destination_cidr=destination,
                next_hop=nexthop,
                interface=interface,
                metric=int(metric),
                protocol="static",
                vrf=vr_name,
            ))

        logger.info("Fetched %d routes from %s", len(routes), self.api_endpoint)
        return routes

    # ------------------------------------------------------------------
    # Virtual routers (PAN-OS specific)
    # ------------------------------------------------------------------

    async def get_virtual_routers(self) -> list[VirtualRouter]:
        """Fetch virtual routers and their associated interfaces / routes."""
        if not HAS_PANOS:
            raise NotImplementedError("pan-os-python SDK is not installed")

        device = self._connect()

        def _do_fetch():
            return panos.network.VirtualRouter.refreshall(device)

        raw_vrs = await asyncio.get_event_loop().run_in_executor(None, _do_fetch)

        vrs: list[VirtualRouter] = []
        for vr in raw_vrs:
            name = getattr(vr, "name", "")
            ifaces = getattr(vr, "interface", []) or []

            # Fetch static routes for this VR
            def _fetch_routes_for_vr(v=vr):
                return panos.network.StaticRoute.refreshall(v)

            static = await asyncio.get_event_loop().run_in_executor(
                None, _fetch_routes_for_vr,
            )
            route_dicts = []
            for sr in static:
                route_dicts.append({
                    "name": getattr(sr, "name", ""),
                    "destination": getattr(sr, "destination", ""),
                    "nexthop": getattr(sr, "nexthop", ""),
                    "metric": getattr(sr, "metric", 10),
                })

            vrs.append(VirtualRouter(
                name=name,
                interfaces=list(ifaces),
                static_routes=route_dicts,
            ))

        self._vr_cache = vrs
        logger.info("Fetched %d virtual routers from %s", len(vrs), self.api_endpoint)
        return vrs

    # ------------------------------------------------------------------
    # Flow simulation
    # ------------------------------------------------------------------

    async def simulate_flow(
        self, src_ip: str, dst_ip: str, port: int, protocol: str = "tcp",
    ) -> PolicyVerdict:
        """Evaluate cached rules in order against the given flow.

        Rules are evaluated in ascending ``order`` (lower = higher priority).
        The first matching rule determines the verdict.  If no rule matches,
        an implicit-deny verdict is returned (standard PAN-OS behavior).
        """
        await self._ensure_snapshot()

        for rule in sorted(self._rules_cache, key=lambda r: r.order):
            src_match = self._match_ip(src_ip, rule.src_ips)
            dst_match = self._match_ip(dst_ip, rule.dst_ips)
            port_match = self._match_port(port, rule.ports)

            if src_match and dst_match and port_match:
                return PolicyVerdict(
                    action=rule.action,
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    match_type=VerdictMatchType.EXACT,
                    confidence=0.95,
                    details=f"Matched PAN-OS rule '{rule.rule_name}' (order {rule.order})",
                )

        # PAN-OS implicit deny at the end of every rulebase
        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="interzone-default",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.90,
            details="No matching rule; PAN-OS implicit interzone-default deny",
        )

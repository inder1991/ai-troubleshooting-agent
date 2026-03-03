"""Base firewall adapter interface. All vendor adapters implement this."""
from abc import ABC, abstractmethod
from typing import Optional
import time
from ..models import (
    PolicyVerdict, AdapterHealth, AdapterHealthStatus, FirewallVendor,
    FirewallRule, NATRule, Zone, Route, PolicyAction, VerdictMatchType,
)


class VRF:
    def __init__(self, name: str, rd: str = "", interfaces: list[str] = None):
        self.name = name
        self.rd = rd
        self.interfaces = interfaces or []


class VirtualRouter:
    def __init__(self, name: str, interfaces: list[str] = None, static_routes: list[dict] = None):
        self.name = name
        self.interfaces = interfaces or []
        self.static_routes = static_routes or []


class DeviceInterface:
    def __init__(self, name: str, ip: str, zone: str = "", vrf: str = "", status: str = "up"):
        self.name = name
        self.ip = ip
        self.zone = zone
        self.vrf = vrf
        self.status = status


class FirewallAdapter(ABC):
    """Abstract base for all firewall vendor adapters.

    Key design principles:
    - Diagnostics NEVER hit live API. Always read from cached snapshot.
    - Snapshot refreshed on TTL expiry or manual trigger.
    - Each adapter normalizes vendor-specific data to common models.
    """

    DEFAULT_TTL = 300  # 5 minutes

    def __init__(self, vendor: FirewallVendor, api_endpoint: str = "", api_key: str = "",
                 extra_config: dict = None):
        self.vendor = vendor
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self.extra_config = extra_config or {}
        self._snapshot_time: float = 0
        self._rules_cache: list[FirewallRule] = []
        self._nat_cache: list[NATRule] = []
        self._zones_cache: list[Zone] = []
        self._routes_cache: list[Route] = []
        self._interfaces_cache: list[DeviceInterface] = []

    # -- Core troubleshooting --

    @abstractmethod
    async def simulate_flow(
        self, src_ip: str, dst_ip: str, port: int, protocol: str = "tcp"
    ) -> PolicyVerdict:
        """Simulate a flow against cached rules. Return verdict with confidence."""

    # -- Policy snapshot (cached) --

    @abstractmethod
    async def _fetch_rules(self) -> list[FirewallRule]:
        """Vendor-specific: fetch rules from API."""

    @abstractmethod
    async def _fetch_nat_rules(self) -> list[NATRule]:
        """Vendor-specific: fetch NAT rules from API."""

    @abstractmethod
    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        """Vendor-specific: fetch interfaces from API."""

    @abstractmethod
    async def _fetch_routes(self) -> list[Route]:
        """Vendor-specific: fetch routing table from API."""

    @abstractmethod
    async def _fetch_zones(self) -> list[Zone]:
        """Vendor-specific: fetch security zones from API."""

    async def get_rules(self, zone_src: str = "", zone_dst: str = "") -> list[FirewallRule]:
        await self._ensure_snapshot()
        if zone_src or zone_dst:
            return [r for r in self._rules_cache
                    if (not zone_src or r.src_zone == zone_src)
                    and (not zone_dst or r.dst_zone == zone_dst)]
        return self._rules_cache

    async def get_nat_rules(self) -> list[NATRule]:
        await self._ensure_snapshot()
        return self._nat_cache

    async def get_interfaces(self) -> list[DeviceInterface]:
        await self._ensure_snapshot()
        return self._interfaces_cache

    async def get_routes(self) -> list[Route]:
        await self._ensure_snapshot()
        return self._routes_cache

    async def get_zones(self) -> list[Zone]:
        await self._ensure_snapshot()
        return self._zones_cache

    async def get_vrfs(self) -> list[VRF]:
        """Override in adapters that support VRFs."""
        return []

    async def get_virtual_routers(self) -> list[VirtualRouter]:
        """Override in adapters that support virtual routers (e.g., PAN-OS)."""
        return []

    # -- Operational --

    async def health_check(self) -> AdapterHealth:
        """Check adapter connectivity and snapshot freshness."""
        if not self.api_endpoint:
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.NOT_CONFIGURED,
                message="No API endpoint configured",
            )
        try:
            await self._fetch_zones()
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.CONNECTED,
                snapshot_age_seconds=self.snapshot_age_seconds(),
                last_refresh=self._format_snapshot_time(),
            )
        except Exception as e:
            if "auth" in str(e).lower() or "401" in str(e) or "403" in str(e):
                return AdapterHealth(
                    vendor=self.vendor,
                    status=AdapterHealthStatus.AUTH_FAILED,
                    message=str(e),
                )
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.UNREACHABLE,
                message=str(e),
            )

    async def refresh_snapshot(self) -> None:
        """Force a full snapshot refresh."""
        self._rules_cache = await self._fetch_rules()
        self._nat_cache = await self._fetch_nat_rules()
        self._interfaces_cache = await self._fetch_interfaces()
        self._routes_cache = await self._fetch_routes()
        self._zones_cache = await self._fetch_zones()
        self._snapshot_time = time.time()

    def snapshot_age_seconds(self) -> float:
        if self._snapshot_time == 0:
            return float("inf")
        return time.time() - self._snapshot_time

    # -- Internal --

    async def _ensure_snapshot(self) -> None:
        if self.snapshot_age_seconds() > self.DEFAULT_TTL:
            await self.refresh_snapshot()

    def _format_snapshot_time(self) -> str:
        if self._snapshot_time == 0:
            return ""
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self._snapshot_time, tz=timezone.utc).isoformat()

    def _match_ip(self, ip: str, patterns: list[str]) -> bool:
        """Check if ip matches any pattern (exact or CIDR)."""
        import ipaddress
        if not patterns or "any" in patterns:
            return True
        try:
            addr = ipaddress.ip_address(ip)
            for p in patterns:
                if "/" in p:
                    if addr in ipaddress.ip_network(p, strict=False):
                        return True
                elif p == ip:
                    return True
        except ValueError:
            pass
        return False

    @staticmethod
    def _match_port(port: int, ports: list) -> bool:
        """Check if port matches rule port list (empty = any).

        Entries may be plain ints or (min, max) tuple ranges.
        """
        if not ports:
            return True  # empty = any port
        for p in ports:
            if isinstance(p, tuple):
                if p[0] <= port <= p[1]:
                    return True
            elif port == p:
                return True
        return False

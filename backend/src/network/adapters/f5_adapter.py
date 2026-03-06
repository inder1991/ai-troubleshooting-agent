"""F5 BIG-IP iControl REST adapter.

Integrates with F5 BIG-IP LTM/AFM via the iControl REST API to fetch
firewall rules (AFM policies), SNAT pools, self IPs, static routes,
and route domains (security zones).

Authentication uses HTTP Basic Auth with username/password.

All diagnostic reads (simulate_flow, get_rules, etc.) operate against
a locally-cached snapshot -- never live API calls in the hot path.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

from .base import FirewallAdapter, DeviceInterface
from ..models import (
    PolicyVerdict,
    FirewallVendor,
    FirewallRule,
    NATRule,
    Zone,
    Route,
    PolicyAction,
    VerdictMatchType,
    AdapterHealth,
    AdapterHealthStatus,
)

# httpx is optional -- adapter degrades gracefully if unavailable
try:
    import httpx  # type: ignore[import-untyped]

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


class F5Adapter(FirewallAdapter):
    """Adapter for F5 BIG-IP iControl REST API.

    Parameters
    ----------
    hostname : str
        The BIG-IP management hostname or IP (e.g. ``"bigip01.example.com"``).
    username : str
        Admin username for iControl REST.
    password : str
        Admin password for iControl REST.
    partition : str
        BIG-IP partition to query (default ``"Common"``).
    verify_ssl : bool
        Whether to verify TLS certificates (default ``False`` for self-signed).
    """

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        partition: str = "Common",
        verify_ssl: bool = False,
    ) -> None:
        api_endpoint = f"https://{hostname}" if hostname else ""
        super().__init__(
            vendor=FirewallVendor.F5,
            api_endpoint=api_endpoint,
            api_key="",
            extra_config={
                "hostname": hostname,
                "username": username,
                "partition": partition,
            },
        )
        self._hostname = hostname
        self._username = username
        self._password = password
        self._partition = partition
        self._verify_ssl = verify_ssl

    # ── Helpers ────────────────────────────────────────────────────────

    def _auth(self) -> tuple[str, str]:
        """Return basic auth tuple for httpx."""
        return (self._username, self._password)

    @staticmethod
    def _stable_id(raw: str) -> str:
        """Generate a deterministic 12-char ID from a string."""
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _client(self) -> "httpx.AsyncClient":
        """Create an httpx async client with auth and SSL settings."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError(
                "httpx is required for F5 iControl REST API calls. "
                "Install it with: pip install httpx"
            )
        return httpx.AsyncClient(
            auth=self._auth(),
            verify=self._verify_ssl,
            timeout=30,
        )

    # ── Core troubleshooting ───────────────────────────────────────────

    async def simulate_flow(
        self,
        src_ip: str,
        dst_ip: str,
        port: int,
        protocol: str = "tcp",
    ) -> PolicyVerdict:
        """Simulate a flow against cached AFM firewall rules.

        Rules are evaluated in order (ascending). The first matching rule
        determines the verdict. If no rule matches, an implicit deny is
        returned (F5 AFM default-deny posture).
        """
        await self._ensure_snapshot()

        for rule in sorted(self._rules_cache, key=lambda r: r.order):
            src_match = self._match_ip(src_ip, rule.src_ips)
            dst_match = self._match_ip(dst_ip, rule.dst_ips)
            port_match = self._match_port(port, rule.ports)
            proto_match = (
                rule.protocol.lower() in (protocol.lower(), "any")
                or protocol.lower() == "any"
            )

            if src_match and dst_match and port_match and proto_match:
                return PolicyVerdict(
                    action=rule.action,
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    match_type=VerdictMatchType.EXACT,
                    confidence=0.90,
                    details=(
                        f"Matched F5 AFM rule '{rule.rule_name}' "
                        f"(order {rule.order})"
                    ),
                )

        # F5 AFM implicit default-deny
        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="f5-implicit-deny",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.75,
            details="No matching F5 AFM rule; implicit deny applied",
        )

    # ── Policy snapshot fetchers ───────────────────────────────────────

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch AFM firewall rules from BIG-IP.

        GET /mgmt/tm/security/firewall/policy to list policies, then
        fetch rules within each policy.
        """
        async with self._client() as client:
            # Fetch all firewall policies
            resp = await client.get(
                f"{self.api_endpoint}/mgmt/tm/security/firewall/policy",
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            policies = resp.json().get("items", [])

            rules: list[FirewallRule] = []
            order_counter = 0

            for policy in policies:
                policy_name = policy.get("name", "")
                # Fetch rules within this policy via the rulesReference link
                rules_link = policy.get("rulesReference", {}).get("link", "")
                if not rules_link:
                    continue
                # iControl REST returns localhost links; rewrite to our endpoint
                rules_url = (
                    f"{self.api_endpoint}/mgmt/tm/security/firewall/policy"
                    f"/~{self._partition}~{policy_name}/rules"
                )
                rules_resp = await client.get(rules_url)
                if rules_resp.status_code == 404:
                    continue
                rules_resp.raise_for_status()
                raw_rules = rules_resp.json().get("items", [])

                for raw in raw_rules:
                    rule = self._normalize_afm_rule(raw, order_counter, policy_name)
                    rules.append(rule)
                    order_counter += 1

        return rules

    async def _fetch_nat_rules(self) -> list[NATRule]:
        """Fetch SNAT pools from BIG-IP LTM.

        GET /mgmt/tm/ltm/snatpool
        """
        async with self._client() as client:
            resp = await client.get(
                f"{self.api_endpoint}/mgmt/tm/ltm/snatpool",
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json().get("items", [])

            nat_rules: list[NATRule] = []
            for item in items:
                pool_name = item.get("name", "")
                members = item.get("members", [])
                for member in members:
                    nat_rules.append(
                        NATRule(
                            id=self._stable_id(f"snat-{pool_name}-{member}"),
                            device_id=f"f5-{self._hostname}",
                            translated_src=member,
                            direction="snat",
                            description=f"SNAT pool '{pool_name}' member {member}",
                        )
                    )

            return nat_rules

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        """Fetch self IPs from BIG-IP as logical interfaces.

        GET /mgmt/tm/net/self
        """
        async with self._client() as client:
            resp = await client.get(
                f"{self.api_endpoint}/mgmt/tm/net/self",
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json().get("items", [])

            interfaces: list[DeviceInterface] = []
            for item in items:
                name = item.get("name", "")
                address = item.get("address", "")
                # Self IP address may include CIDR suffix (e.g. "10.0.0.1/24")
                ip_only = address.split("/")[0] if address else ""
                vlan = item.get("vlan", "")
                traffic_group = item.get("trafficGroup", "")

                interfaces.append(
                    DeviceInterface(
                        name=name,
                        ip=ip_only,
                        zone=vlan,
                        status="up" if item.get("enabled", True) else "down",
                    )
                )

            return interfaces

    async def _fetch_routes(self) -> list[Route]:
        """Fetch static routes from BIG-IP.

        GET /mgmt/tm/net/route
        """
        async with self._client() as client:
            resp = await client.get(
                f"{self.api_endpoint}/mgmt/tm/net/route",
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json().get("items", [])

            routes: list[Route] = []
            for item in items:
                name = item.get("name", "")
                network = item.get("network", "")
                gw = item.get("gw", "")
                tmInterface = item.get("tmInterface", "")

                routes.append(
                    Route(
                        id=self._stable_id(f"route-{name}-{network}"),
                        device_id=f"f5-{self._hostname}",
                        destination_cidr=network,
                        next_hop=gw,
                        interface=tmInterface,
                        protocol="static",
                    )
                )

            return routes

    async def _fetch_zones(self) -> list[Zone]:
        """Fetch route domains from BIG-IP as security zones.

        GET /mgmt/tm/net/route-domain
        """
        async with self._client() as client:
            resp = await client.get(
                f"{self.api_endpoint}/mgmt/tm/net/route-domain",
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json().get("items", [])

            zones: list[Zone] = []
            for item in items:
                rd_id = str(item.get("id", ""))
                name = item.get("name", "")
                desc = item.get("description", "")
                vlans = item.get("vlans", [])

                zones.append(
                    Zone(
                        id=self._stable_id(f"rd-{rd_id}-{name}"),
                        name=name,
                        description=desc or f"Route domain {rd_id}",
                        firewall_id=f"f5-{self._hostname}",
                        security_level=int(rd_id) if rd_id.isdigit() else 0,
                    )
                )

            return zones

    # ── Health check ───────────────────────────────────────────────────

    async def health_check(self) -> AdapterHealth:
        """Check BIG-IP iControl REST reachability.

        Returns NOT_CONFIGURED if hostname is empty.
        """
        if not self._hostname:
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.NOT_CONFIGURED,
                message="No F5 BIG-IP hostname configured",
            )

        if not _HTTPX_AVAILABLE:
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.UNREACHABLE,
                message="httpx library is not installed",
            )

        try:
            async with self._client() as client:
                resp = await client.get(
                    f"{self.api_endpoint}/mgmt/tm/sys/version",
                )
                resp.raise_for_status()

            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.CONNECTED,
                snapshot_age_seconds=self.snapshot_age_seconds(),
                last_refresh=self._format_snapshot_time(),
                message="F5 BIG-IP iControl REST connected",
            )
        except Exception as e:
            err = str(e).lower()
            if "auth" in err or "401" in err or "403" in err:
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

    # ── Internal helpers ───────────────────────────────────────────────

    def _normalize_afm_rule(
        self, raw: dict, index: int, policy_name: str = ""
    ) -> FirewallRule:
        """Convert a raw AFM firewall rule JSON dict to a FirewallRule.

        AFM rule structure (simplified):
        {
            "name": "allow_http",
            "action": "accept",
            "ipProtocol": "tcp",
            "log": "yes",
            "source": {
                "addresses": [{"name": "10.0.0.0/8"}]
            },
            "destination": {
                "addresses": [{"name": "172.16.0.0/12"}],
                "ports": [{"name": "80"}, {"name": "443"}]
            }
        }
        """
        # Map AFM action strings to PolicyAction
        action_str = raw.get("action", "reject").lower()
        if action_str in ("accept", "accept-decisively"):
            action = PolicyAction.ALLOW
        elif action_str == "drop":
            action = PolicyAction.DROP
        else:
            action = PolicyAction.DENY

        # Source IPs from source.addresses[].name
        src_section = raw.get("source", {})
        src_addrs = src_section.get("addresses", [])
        src_ips = [a.get("name", "") for a in src_addrs if a.get("name")]
        if not src_ips:
            src_ips = ["any"]

        # Destination IPs from destination.addresses[].name
        dst_section = raw.get("destination", {})
        dst_addrs = dst_section.get("addresses", [])
        dst_ips = [a.get("name", "") for a in dst_addrs if a.get("name")]
        if not dst_ips:
            dst_ips = ["any"]

        # Destination ports from destination.ports[].name
        ports: list[int] = []
        for port_entry in dst_section.get("ports", []):
            port_name = port_entry.get("name", "")
            if port_name.isdigit():
                ports.append(int(port_name))
            elif "-" in port_name:
                # Port range like "8080-8090"
                parts = port_name.split("-")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    ports.extend(range(int(parts[0]), int(parts[1]) + 1))

        # Protocol
        protocol = raw.get("ipProtocol", "tcp").lower()

        # Logging
        logged = raw.get("log", "no").lower() == "yes"

        rule_name = raw.get("name", f"rule-{index}")
        stable_input = f"{policy_name}-{rule_name}-{index}"

        return FirewallRule(
            id=self._stable_id(stable_input),
            device_id=f"f5-{self._hostname}",
            rule_name=rule_name,
            src_ips=src_ips,
            dst_ips=dst_ips,
            ports=ports,
            action=action,
            order=index,
            logged=logged,
            protocol=protocol,
        )

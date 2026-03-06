"""Cisco IOS-XE RESTCONF adapter.

Integrates with the RESTCONF API (RFC 8040) on Cisco IOS-XE devices
(including Catalyst 8000V in autonomous mode) to fetch ACLs, NAT rules,
interfaces, routes, and ZBFW security zones.

All diagnostic reads (simulate_flow, get_rules, etc.) operate against
a locally-cached snapshot -- never live API calls in the hot path.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from .base import FirewallAdapter, DeviceInterface, VRF
from ..models import (
    PolicyVerdict,
    FirewallVendor,
    FirewallRule,
    NATRule,
    Zone,
    Route,
    PolicyAction,
    VerdictMatchType,
    NATDirection,
)

# httpx is optional -- adapter degrades gracefully if unavailable
try:
    import httpx  # type: ignore[import-untyped]

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RESTCONF media type and common headers
# ---------------------------------------------------------------------------
_RESTCONF_HEADERS = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json",
}


def _stable_id(*parts: str) -> str:
    """Generate a deterministic short ID from key fields."""
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


class CiscoAdapter(FirewallAdapter):
    """Adapter for Cisco IOS-XE devices via RESTCONF API.

    Parameters
    ----------
    hostname : str
        Device management IP or FQDN.
    username : str
        RESTCONF username for HTTP Basic Auth.
    password : str
        RESTCONF password for HTTP Basic Auth.
    verify_ssl : bool
        Whether to verify the TLS certificate (default ``False``
        because lab / self-signed certs are common on IOS-XE).
    """

    def __init__(
        self,
        hostname: str,
        username: str = "",
        password: str = "",
        verify_ssl: bool = False,
    ) -> None:
        api_endpoint = f"https://{hostname}" if hostname else ""
        super().__init__(
            vendor=FirewallVendor.CISCO,
            api_endpoint=api_endpoint,
            api_key="",
            extra_config={
                "hostname": hostname,
                "username": username,
            },
        )
        self._hostname = hostname
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl
        self._vrf_cache: list[VRF] = []

    # ── HTTP helpers ──────────────────────────────────────────────────

    def _client_kwargs(self) -> dict:
        """Common kwargs for httpx.AsyncClient."""
        return {
            "timeout": 30,
            "verify": self._verify_ssl,
            "auth": (self._username, self._password) if self._username else None,
            "headers": _RESTCONF_HEADERS,
        }

    async def _restconf_get(self, path: str) -> dict | list | None:
        """Issue a RESTCONF GET and return parsed JSON, or None on 404."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError(
                "httpx is required for Cisco RESTCONF API calls. "
                "Install it with: pip install httpx"
            )
        url = f"{self.api_endpoint}/restconf/data/{path}"
        async with httpx.AsyncClient(**self._client_kwargs()) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    # ── Core troubleshooting ──────────────────────────────────────────

    async def simulate_flow(
        self,
        src_ip: str,
        dst_ip: str,
        port: int,
        protocol: str = "tcp",
    ) -> PolicyVerdict:
        """Simulate a flow against cached IOS-XE extended ACL rules.

        Rules are evaluated in ascending ``order``.  The first matching
        rule determines the verdict.  If no rule matches, an implicit
        deny is returned (standard IOS-XE ACL behavior).
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
                        f"Matched IOS-XE ACE '{rule.rule_name}' "
                        f"(order {rule.order})"
                    ),
                )

        # IOS-XE implicit deny at end of every ACL
        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="implicit-deny",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.90,
            details="No matching ACE; IOS-XE implicit deny at end of ACL",
        )

    # ── Policy snapshot fetchers ──────────────────────────────────────

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch extended ACLs from IOS-XE via RESTCONF.

        GET /restconf/data/Cisco-IOS-XE-native:native/ip/access-list
        """
        data = await self._restconf_get(
            "Cisco-IOS-XE-native:native/ip/access-list"
        )
        if not data:
            return []

        rules: list[FirewallRule] = []
        device_id = self._hostname

        # Navigate to extended ACLs
        access_list = data.get("Cisco-IOS-XE-native:access-list", data)
        extended_acls = access_list.get("extended", [])
        if isinstance(extended_acls, dict):
            extended_acls = [extended_acls]

        for acl in extended_acls:
            acl_name = str(acl.get("name", ""))
            entries = acl.get("access-list-seq-rule", [])
            if isinstance(entries, dict):
                entries = [entries]

            for idx, entry in enumerate(entries):
                seq = entry.get("sequence", idx * 10)
                ace = entry.get("ace", {})
                rule = self._normalize_ace(ace, acl_name, seq, device_id)
                if rule:
                    rules.append(rule)

        logger.info(
            "Fetched %d ACL rules from %s", len(rules), self._hostname
        )
        return rules

    async def _fetch_nat_rules(self) -> list[NATRule]:
        """Fetch static NAT entries from IOS-XE via RESTCONF.

        GET /restconf/data/Cisco-IOS-XE-native:native/ip/nat
        """
        data = await self._restconf_get(
            "Cisco-IOS-XE-native:native/ip/nat"
        )
        if not data:
            return []

        nat_rules: list[NATRule] = []
        device_id = self._hostname
        nat_data = data.get("Cisco-IOS-XE-native:nat", data)

        # Static NAT entries
        static_entries = nat_data.get("inside", {}).get("source", {}).get(
            "static", []
        )
        if isinstance(static_entries, dict):
            static_entries = [static_entries]

        for idx, entry in enumerate(static_entries):
            local_ip = entry.get("local-ip", "")
            global_ip = entry.get("global-ip", "")
            nat_rules.append(NATRule(
                id=_stable_id(device_id, "nat-static", str(idx)),
                device_id=device_id,
                original_src=local_ip,
                translated_src=global_ip,
                direction=NATDirection.SNAT,
                rule_id=f"static-nat-{idx}",
                description=f"Static NAT {local_ip} -> {global_ip}",
            ))

        logger.info(
            "Fetched %d NAT rules from %s", len(nat_rules), self._hostname
        )
        return nat_rules

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        """Fetch interfaces from IOS-XE via RESTCONF (IETF model).

        GET /restconf/data/ietf-interfaces:interfaces
        """
        data = await self._restconf_get("ietf-interfaces:interfaces")
        if not data:
            return []

        interfaces: list[DeviceInterface] = []
        iface_list = data.get("ietf-interfaces:interfaces", data).get(
            "interface", []
        )
        if isinstance(iface_list, dict):
            iface_list = [iface_list]

        for iface in iface_list:
            name = iface.get("name", "")
            enabled = iface.get("enabled", True)
            # Extract IPv4 address from ietf-ip augmentation
            ipv4 = iface.get("ietf-ip:ipv4", {})
            ip_str = ""
            addrs = ipv4.get("address", [])
            if isinstance(addrs, dict):
                addrs = [addrs]
            if addrs:
                ip_str = addrs[0].get("ip", "")
                prefix_len = addrs[0].get("prefix-length", "")
                if ip_str and prefix_len:
                    ip_str = f"{ip_str}/{prefix_len}"

            interfaces.append(DeviceInterface(
                name=name,
                ip=ip_str,
                status="up" if enabled else "down",
            ))

        logger.info(
            "Fetched %d interfaces from %s", len(interfaces), self._hostname
        )
        return interfaces

    async def _fetch_routes(self) -> list[Route]:
        """Fetch IPv4 routes from IOS-XE via RESTCONF (IETF routing model).

        GET /restconf/data/ietf-routing:routing/routing-instance=default/ribs/rib=ipv4-default/routes
        """
        data = await self._restconf_get(
            "ietf-routing:routing/routing-instance=default/ribs/rib=ipv4-default/routes"
        )
        if not data:
            return []

        routes: list[Route] = []
        device_id = self._hostname
        route_list = data.get("ietf-routing:routes", data).get("route", [])
        if isinstance(route_list, dict):
            route_list = [route_list]

        for idx, rt in enumerate(route_list):
            dest = rt.get("destination-prefix", "")
            next_hop = rt.get("next-hop", {})
            nh_addr = ""
            nh_iface = ""
            if isinstance(next_hop, dict):
                nh_addr = next_hop.get("next-hop-address", "")
                nh_iface = next_hop.get("outgoing-interface", "")
            elif isinstance(next_hop, str):
                nh_addr = next_hop

            source_proto = rt.get("source-protocol", "static")

            routes.append(Route(
                id=_stable_id(device_id, "route", str(idx)),
                device_id=device_id,
                destination_cidr=dest,
                next_hop=nh_addr,
                interface=nh_iface,
                metric=rt.get("metric", 0),
                protocol=source_proto,
            ))

        logger.info(
            "Fetched %d routes from %s", len(routes), self._hostname
        )
        return routes

    async def _fetch_zones(self) -> list[Zone]:
        """Fetch ZBFW security zones from IOS-XE via RESTCONF.

        GET /restconf/data/Cisco-IOS-XE-native:native/zone/security
        """
        data = await self._restconf_get(
            "Cisco-IOS-XE-native:native/zone/security"
        )
        if not data:
            return []

        zones: list[Zone] = []
        device_id = self._hostname
        zone_list = data.get("Cisco-IOS-XE-native:security", data)
        if isinstance(zone_list, dict):
            zone_list = [zone_list]

        for z in zone_list:
            name = z.get("id", z.get("name", ""))
            desc = z.get("description", "")
            zones.append(Zone(
                id=_stable_id(device_id, "zone", name),
                name=name,
                description=desc,
                firewall_id=device_id,
            ))

        logger.info(
            "Fetched %d zones from %s", len(zones), self._hostname
        )
        return zones

    # ── VRF support ───────────────────────────────────────────────────

    async def get_vrfs(self) -> list[VRF]:
        """Fetch VRF definitions from IOS-XE via RESTCONF.

        GET /restconf/data/Cisco-IOS-XE-native:native/vrf/definition
        """
        data = await self._restconf_get(
            "Cisco-IOS-XE-native:native/vrf/definition"
        )
        if not data:
            return []

        vrfs: list[VRF] = []
        vrf_list = data.get("Cisco-IOS-XE-native:definition", data)
        if isinstance(vrf_list, dict):
            vrf_list = [vrf_list]

        for v in vrf_list:
            name = v.get("name", "")
            rd = v.get("rd", "")
            vrfs.append(VRF(name=name, rd=rd))

        self._vrf_cache = vrfs
        logger.info(
            "Fetched %d VRFs from %s", len(vrfs), self._hostname
        )
        return vrfs

    # ── ACE normalization ─────────────────────────────────────────────

    def _normalize_ace(
        self,
        ace: dict,
        acl_name: str,
        sequence: int,
        device_id: str,
    ) -> FirewallRule | None:
        """Convert a raw IOS-XE ACE dict to a FirewallRule.

        A typical ACE structure from RESTCONF (extended ACL):
        {
            "grant": "permit",
            "protocol": "tcp",
            "source-address": "10.0.0.0",
            "source-wildcard": "0.0.0.255",
            "destination-address": "172.16.0.0",
            "destination-wildcard": "0.0.15.255",
            "destination-port": 443
        }

        Also handles:
        - "source-host" / "destination-host" for host addresses
        - "source-any" / "destination-any" for any
        """
        if not ace:
            return None

        # Action
        grant = ace.get("grant", "deny").lower()
        if grant == "permit":
            action = PolicyAction.ALLOW
        else:
            action = PolicyAction.DENY

        # Protocol
        protocol = str(ace.get("protocol", "ip")).lower()
        if protocol == "ip":
            protocol = "any"

        # Source IP
        src_ips = self._extract_address(ace, "source")

        # Destination IP
        dst_ips = self._extract_address(ace, "destination")

        # Ports
        ports: list[int] = []
        dst_port = ace.get("destination-port", ace.get("dst-eq", None))
        if dst_port is not None:
            try:
                ports.append(int(dst_port))
            except (ValueError, TypeError):
                pass

        rule_name = f"{acl_name}:seq-{sequence}"

        return FirewallRule(
            id=_stable_id(device_id, acl_name, str(sequence)),
            device_id=device_id,
            rule_name=rule_name,
            src_ips=src_ips,
            dst_ips=dst_ips,
            ports=ports,
            protocol=protocol,
            action=action,
            order=sequence,
        )

    def _extract_address(self, ace: dict, prefix: str) -> list[str]:
        """Extract source or destination address from an ACE dict.

        Handles:
        - {prefix}-host: "10.0.0.1"          -> ["10.0.0.1/32"]
        - {prefix}-address + {prefix}-wildcard -> CIDR
        - {prefix}-any: true                  -> ["any"]
        """
        # host address
        host = ace.get(f"{prefix}-host")
        if host:
            return [f"{host}/32"]

        # any
        if ace.get(f"{prefix}-any") or ace.get(f"{prefix}-address") == "any":
            return ["any"]

        # address + wildcard
        addr = ace.get(f"{prefix}-address", "")
        wildcard = ace.get(f"{prefix}-wildcard", "")
        if addr and wildcard:
            return [self._wildcard_to_cidr(f"{addr} {wildcard}")]
        elif addr:
            return [f"{addr}/32"]

        return ["any"]

    @staticmethod
    def _wildcard_to_cidr(value: str) -> str:
        """Convert Cisco wildcard notation to CIDR.

        Examples:
            "10.0.0.0 0.0.0.255"  -> "10.0.0.0/24"
            "host 10.0.0.1"       -> "10.0.0.1/32"
            "any"                 -> "any"
        """
        value = value.strip()
        if value.lower() == "any":
            return "any"

        if value.lower().startswith("host "):
            return f"{value[5:].strip()}/32"

        parts = value.split()
        if len(parts) != 2:
            return value

        address, wildcard = parts
        # Convert wildcard mask to prefix length
        # Wildcard bits: 0 = must match, 1 = don't care
        try:
            octets = [int(o) for o in wildcard.split(".")]
            # Invert wildcard to get netmask, then count bits
            mask_bits = 0
            for octet in octets:
                inverted = 255 - octet
                mask_bits += bin(inverted).count("1")
            return f"{address}/{mask_bits}"
        except (ValueError, IndexError):
            return value

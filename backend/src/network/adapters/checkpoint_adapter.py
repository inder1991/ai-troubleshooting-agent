"""Check Point Management API adapter.

Integrates with the Check Point Management API (JSON-RPC over HTTPS) to fetch
access rules, NAT rules, gateway interfaces, and topology zones.
Authentication uses session-based auth via POST /web_api/login which returns
a session ID (sid) used in subsequent X-chkp-sid headers.

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


class CheckpointAdapter(FirewallAdapter):
    """Adapter for Check Point Management API (R80+).

    Parameters
    ----------
    hostname : str
        Management server hostname or IP address.
    username : str
        SmartConsole administrator username.
    password : str
        SmartConsole administrator password.
    domain : str
        Multi-domain server (MDS) domain name. Empty for single-domain.
    port : int
        Management API port (default 443).
    verify_ssl : bool
        Whether to verify TLS certificates (default False for lab environments).
    """

    # Check Point sessions expire after ~600s idle; we re-auth proactively
    _SESSION_TTL = 500  # seconds

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        domain: str = "",
        port: int = 443,
        verify_ssl: bool = False,
    ) -> None:
        api_endpoint = f"https://{hostname}:{port}" if hostname else ""
        super().__init__(
            vendor=FirewallVendor.CHECKPOINT,
            api_endpoint=api_endpoint,
            api_key="",
            extra_config={
                "hostname": hostname,
                "username": username,
                "domain": domain,
                "port": port,
            },
        )
        self._hostname = hostname
        self._username = username
        self._password = password
        self._domain = domain
        self._port = port
        self._verify_ssl = verify_ssl
        self._sid: Optional[str] = None
        self._sid_ts: float = 0

    # ── Authentication ─────────────────────────────────────────────────

    async def _login(self) -> None:
        """Obtain a Check Point Management API session ID (sid).

        POST /web_api/login with {user, password} and optional domain.
        """
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError(
                "httpx is required for Check Point API calls. "
                "Install it with: pip install httpx"
            )
        payload: dict = {
            "user": self._username,
            "password": self._password,
        }
        if self._domain:
            payload["domain"] = self._domain

        async with httpx.AsyncClient(
            timeout=30, verify=self._verify_ssl
        ) as client:
            resp = await client.post(
                f"{self.api_endpoint}/web_api/login",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._sid = data.get("sid", "")
            self._sid_ts = time.time()

    async def _ensure_session(self) -> None:
        """Re-login if session is expired or missing."""
        if (
            not self._sid
            or (time.time() - self._sid_ts) > self._SESSION_TTL
        ):
            await self._login()

    def _api_headers(self) -> dict[str, str]:
        """Return headers for authenticated API calls."""
        return {
            "Content-Type": "application/json",
            "X-chkp-sid": self._sid or "",
        }

    async def _api_call(self, command: str, payload: dict | None = None) -> dict:
        """Execute a Check Point Management API command.

        POST /web_api/{command} with session headers.
        """
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError(
                "httpx is required for Check Point API calls"
            )
        await self._ensure_session()

        async with httpx.AsyncClient(
            timeout=30, verify=self._verify_ssl
        ) as client:
            resp = await client.post(
                f"{self.api_endpoint}/web_api/{command}",
                json=payload or {},
                headers=self._api_headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # ── Core troubleshooting ───────────────────────────────────────────

    async def simulate_flow(
        self,
        src_ip: str,
        dst_ip: str,
        port: int,
        protocol: str = "tcp",
    ) -> PolicyVerdict:
        """Simulate a flow against cached Check Point access rules.

        Rules are evaluated in order (ascending). The first matching rule
        determines the verdict. If no rule matches, the implicit
        Check Point cleanup-rule (deny all) is applied.
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
                        f"Matched Check Point rule '{rule.rule_name}' "
                        f"(order {rule.order})"
                    ),
                )

        # Check Point implicit cleanup-rule: deny all
        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="cleanup-rule",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.75,
            details="No matching Check Point rule; implicit cleanup-rule deny applied",
        )

    # ── Policy snapshot fetchers ───────────────────────────────────────

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch access rules from Check Point Management API.

        Uses show-access-rulebase to retrieve the full access policy.
        Parses sections (layers) and inline rules.
        """
        data = await self._api_call(
            "show-access-rulebase",
            {
                "name": "Network",
                "details-level": "full",
                "use-object-dictionary": True,
                "limit": 500,
                "offset": 0,
            },
        )

        rules: list[FirewallRule] = []
        rulebase = data.get("rulebase", [])
        order = 0

        for section in rulebase:
            # Sections can contain sub-rules in a "rulebase" key
            section_rules = section.get("rulebase", [section])
            for raw_rule in section_rules:
                if raw_rule.get("type") in ("access-rule", "access-section"):
                    if raw_rule.get("type") == "access-section":
                        continue
                    rule = self._normalize_access_rule(raw_rule, order)
                    rules.append(rule)
                    order += 1

        return rules

    async def _fetch_nat_rules(self) -> list[NATRule]:
        """Fetch NAT rules from Check Point Management API.

        Uses show-nat-rulebase to retrieve the NAT policy.
        """
        data = await self._api_call(
            "show-nat-rulebase",
            {
                "package": "standard",
                "details-level": "full",
                "limit": 500,
                "offset": 0,
            },
        )

        nat_rules: list[NATRule] = []
        rulebase = data.get("rulebase", [])

        for idx, raw in enumerate(rulebase):
            sub_rules = raw.get("rulebase", [raw])
            for raw_rule in sub_rules:
                if raw_rule.get("type") != "nat-rule":
                    continue
                rule_id = self._stable_id(
                    f"cp-nat-{raw_rule.get('uid', idx)}"
                )
                original_src = self._extract_ip(
                    raw_rule.get("original-source", {})
                )
                original_dst = self._extract_ip(
                    raw_rule.get("original-destination", {})
                )
                translated_src = self._extract_ip(
                    raw_rule.get("translated-source", {})
                )
                translated_dst = self._extract_ip(
                    raw_rule.get("translated-destination", {})
                )

                nat_rules.append(
                    NATRule(
                        id=rule_id,
                        device_id=f"checkpoint-{self._hostname}",
                        original_src=original_src,
                        original_dst=original_dst,
                        translated_src=translated_src,
                        translated_dst=translated_dst,
                    )
                )

        return nat_rules

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        """Fetch interfaces from Check Point gateways.

        Uses show-gateways-and-servers to enumerate managed gateways,
        then extracts interface information from each gateway object.
        """
        data = await self._api_call(
            "show-gateways-and-servers",
            {"details-level": "full", "limit": 50},
        )

        interfaces: list[DeviceInterface] = []
        for gw in data.get("objects", []):
            gw_name = gw.get("name", "")
            for iface in gw.get("interfaces", []):
                interfaces.append(
                    DeviceInterface(
                        name=iface.get("name", ""),
                        ip=iface.get("ipv4-address", ""),
                        zone=iface.get("topology", ""),
                        status="up",
                    )
                )

        return interfaces

    async def _fetch_routes(self) -> list[Route]:
        """Check Point Management API does not expose Gaia routing table.

        Gaia routes are managed via Gaia Portal or clish, not the
        Management API. Returns an empty list.
        """
        return []

    async def _fetch_zones(self) -> list[Zone]:
        """Extract topology zones from Check Point gateway interfaces.

        Uses show-gateways-and-servers to collect topology zone names
        from interface definitions on managed gateways.
        """
        data = await self._api_call(
            "show-gateways-and-servers",
            {"details-level": "full", "limit": 50},
        )

        seen: set[str] = set()
        zones: list[Zone] = []

        for gw in data.get("objects", []):
            for iface in gw.get("interfaces", []):
                zone_name = iface.get("topology", "")
                if zone_name and zone_name not in seen:
                    seen.add(zone_name)
                    zones.append(
                        Zone(
                            id=self._stable_id(f"cp-zone-{zone_name}"),
                            name=zone_name,
                            firewall_id=f"checkpoint-{self._hostname}",
                        )
                    )

        return zones

    # ── Health check ───────────────────────────────────────────────────

    async def health_check(self) -> AdapterHealth:
        """Check Check Point Management API reachability and session validity.

        Returns NOT_CONFIGURED if hostname is empty.
        """
        if not self._hostname:
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.NOT_CONFIGURED,
                message="No Check Point hostname configured",
            )

        if not _HTTPX_AVAILABLE:
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.UNREACHABLE,
                message="httpx library is not installed",
            )

        try:
            await self._login()
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.CONNECTED,
                snapshot_age_seconds=self.snapshot_age_seconds(),
                last_refresh=self._format_snapshot_time(),
                message="Check Point Management API session authenticated",
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

    def _normalize_access_rule(self, raw: dict, order: int) -> FirewallRule:
        """Convert a raw Check Point access rule to a FirewallRule.

        Check Point access rule structure (simplified):
        {
            "uid": "...",
            "name": "Allow Web",
            "action": {"name": "Accept"},
            "source": [{"type": "host", "ipv4-address": "10.0.0.1"}],
            "destination": [{"type": "network", "subnet4": "10.0.0.0", "mask-length4": 24}],
            "service": [{"type": "service-tcp", "port": "443"}],
            "track": {"type": {"name": "Log"}},
            "enabled": true
        }
        """
        # Action mapping
        action_obj = raw.get("action", {})
        action_name = action_obj.get("name", "Drop") if isinstance(action_obj, dict) else str(action_obj)
        if action_name == "Accept":
            action = PolicyAction.ALLOW
        elif action_name == "Drop":
            action = PolicyAction.DROP
        else:
            action = PolicyAction.DENY

        # Source IPs
        src_ips: list[str] = []
        for obj in raw.get("source", []):
            ip = self._extract_ip(obj)
            src_ips.append(ip)
        if not src_ips:
            src_ips = ["any"]

        # Destination IPs
        dst_ips: list[str] = []
        for obj in raw.get("destination", []):
            ip = self._extract_ip(obj)
            dst_ips.append(ip)
        if not dst_ips:
            dst_ips = ["any"]

        # Service / ports
        ports: list[int] = []
        for svc in raw.get("service", []):
            port_val = svc.get("port", "")
            if isinstance(port_val, int):
                ports.append(port_val)
            elif isinstance(port_val, str) and port_val.isdigit():
                ports.append(int(port_val))

        # Track / logging
        track = raw.get("track", {})
        track_type = track.get("type", {}) if isinstance(track, dict) else {}
        track_name = track_type.get("name", "None") if isinstance(track_type, dict) else str(track_type)
        logged = track_name == "Log"

        # Deterministic rule ID
        rule_uid = raw.get("uid", f"rule-{order}")
        rule_id = self._stable_id(f"cp-rule-{rule_uid}")

        return FirewallRule(
            id=rule_id,
            device_id=f"checkpoint-{self._hostname}",
            rule_name=raw.get("name", f"rule-{order}"),
            src_ips=src_ips,
            dst_ips=dst_ips,
            ports=ports,
            action=action,
            order=order,
            logged=logged,
            protocol="any",
        )

    @staticmethod
    def _extract_ip(obj: dict) -> str:
        """Extract an IP/CIDR string from a Check Point network object.

        Handles:
        - host: {"type": "host", "ipv4-address": "10.0.0.1"} -> "10.0.0.1/32"
        - network: {"type": "network", "subnet4": "10.0.0.0", "mask-length4": 24} -> "10.0.0.0/24"
        - CpmiAnyObject: {"type": "CpmiAnyObject"} -> "any"
        - Fallback: "any"
        """
        obj_type = obj.get("type", "")
        if obj_type == "host":
            addr = obj.get("ipv4-address", "")
            return f"{addr}/32" if addr else "any"
        elif obj_type == "network":
            subnet = obj.get("subnet4", "")
            mask = obj.get("mask-length4", 0)
            return f"{subnet}/{mask}" if subnet else "any"
        elif obj_type == "CpmiAnyObject":
            return "any"
        return "any"

    @staticmethod
    def _stable_id(seed: str) -> str:
        """Generate a deterministic 12-char hex ID from a seed string."""
        return hashlib.sha256(seed.encode()).hexdigest()[:12]

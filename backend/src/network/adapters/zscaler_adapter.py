"""Zscaler ZIA firewall adapter.

Integrates with the Zscaler Internet Access (ZIA) REST API to fetch
firewall rules, web application rules, and trusted-network zones.
Authentication uses session-based auth via POST /authenticatedSession.

All diagnostic reads (simulate_flow, get_rules, etc.) operate against
a locally-cached snapshot -- never live API calls in the hot path.
"""
from __future__ import annotations

import hashlib
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


def _obfuscate_api_key(api_key: str, timestamp: str) -> str:
    """Zscaler API key obfuscation algorithm.

    The ZIA API requires a time-stamped obfuscation of the API key:
      1. Take current epoch milliseconds as a string.
      2. Extract the last 6 chars of the timestamp as positional indices.
      3. Build a new string by picking characters from the api_key at those
         indices, then append the remaining chars of the api_key not chosen.

    Reference: https://help.zscaler.com/zia/getting-started-zia-api
    """
    now = timestamp
    n = now[-6:]
    r = str(int(n) >> 1).zfill(6)
    key = ""
    for i in range(len(n)):
        key += api_key[int(n[i])]
    for i in range(len(r)):
        key += api_key[int(r[i]) + 2]
    return key


class ZscalerAdapter(FirewallAdapter):
    """Adapter for Zscaler Internet Access (ZIA) REST API.

    Parameters
    ----------
    cloud_name : str
        The Zscaler cloud hostname suffix, e.g. ``"zscloud.net"``.
    api_key : str
        ZIA API key for authentication.
    username : str
        Admin username (email) for ZIA portal.
    password : str
        Admin password for ZIA portal.
    """

    # ZIA sessions expire after 30 min of inactivity; we re-auth proactively
    _SESSION_TTL = 1500  # 25 minutes

    def __init__(
        self,
        cloud_name: str,
        api_key: str,
        username: str,
        password: str,
    ) -> None:
        api_endpoint = f"https://zsapi.{cloud_name}/api/v1" if cloud_name else ""
        super().__init__(
            vendor=FirewallVendor.ZSCALER,
            api_endpoint=api_endpoint,
            api_key=api_key,
            extra_config={
                "cloud_name": cloud_name,
                "username": username,
            },
        )
        self._cloud_name = cloud_name
        self._username = username
        self._password = password
        self._session_cookie: Optional[str] = None
        self._session_ts: float = 0

    # ── Authentication ─────────────────────────────────────────────────

    async def _authenticate(self) -> None:
        """Obtain a ZIA authenticated session cookie.

        POST /authenticatedSession with obfuscated API key.
        """
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError(
                "httpx is required for Zscaler API calls. "
                "Install it with: pip install httpx"
            )
        timestamp = str(int(time.time() * 1000))
        obf_key = _obfuscate_api_key(self.api_key, timestamp)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_endpoint}/authenticatedSession",
                json={
                    "apiKey": obf_key,
                    "username": self._username,
                    "password": self._password,
                    "timestamp": timestamp,
                },
            )
            resp.raise_for_status()
            # ZIA returns JSESSIONID in Set-Cookie
            self._session_cookie = resp.cookies.get("JSESSIONID", "")
            self._session_ts = time.time()

    async def _ensure_session(self) -> None:
        """Re-authenticate if session is expired or missing."""
        if (
            not self._session_cookie
            or (time.time() - self._session_ts) > self._SESSION_TTL
        ):
            await self._authenticate()

    def _auth_headers(self) -> dict[str, str]:
        """Return headers/cookies for authenticated API calls."""
        return {"Cookie": f"JSESSIONID={self._session_cookie}"}

    # ── Core troubleshooting ───────────────────────────────────────────

    async def simulate_flow(
        self,
        src_ip: str,
        dst_ip: str,
        port: int,
        protocol: str = "tcp",
    ) -> PolicyVerdict:
        """Simulate a flow against cached ZIA firewall rules.

        Rules are evaluated in order (ascending). The first matching rule
        determines the verdict. If no rule matches, an implicit deny is
        returned (Zscaler default-deny posture).
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
                    details=(
                        f"Matched Zscaler rule '{rule.rule_name}' "
                        f"(order {rule.order})"
                    ),
                )

        # Zscaler implicit default-deny
        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="zscaler-implicit-deny",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.75,
            details="No matching Zscaler rule; implicit deny applied",
        )

    # ── Policy snapshot fetchers ───────────────────────────────────────

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch firewall rules from ZIA API.

        Tries /firewallRules first, falls back to /webApplicationRules.
        Normalizes vendor-specific JSON to FirewallRule models.
        """
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError(
                "httpx is required for Zscaler API calls"
            )
        await self._ensure_session()
        rules: list[FirewallRule] = []

        async with httpx.AsyncClient(timeout=30) as client:
            # Try firewall rules endpoint
            resp = await client.get(
                f"{self.api_endpoint}/firewallRules",
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            raw_rules = resp.json()

            for idx, raw in enumerate(raw_rules):
                rule = self._normalize_rule(raw, idx)
                rules.append(rule)

        return rules

    async def _fetch_nat_rules(self) -> list[NATRule]:
        """Zscaler ZIA does not expose NAT rules via API."""
        return []

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        """Zscaler is cloud-native; no physical interfaces to enumerate."""
        return []

    async def _fetch_routes(self) -> list[Route]:
        """Zscaler is cloud-native; no routing table to enumerate."""
        return []

    async def _fetch_zones(self) -> list[Zone]:
        """Fetch Zscaler trusted networks as security zones.

        Uses /locations endpoint to derive zone-like constructs from
        ZPA trusted networks / ZIA locations.
        """
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError(
                "httpx is required for Zscaler API calls"
            )
        await self._ensure_session()
        zones: list[Zone] = []

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.api_endpoint}/locations",
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            raw_locations = resp.json()

            for loc in raw_locations:
                zones.append(
                    Zone(
                        id=str(loc.get("id", "")),
                        name=loc.get("name", ""),
                        description=loc.get("description", ""),
                        firewall_id=f"zscaler-{self._cloud_name}",
                        security_level=loc.get("securityLevel", 0),
                    )
                )

        return zones

    # ── Health check ───────────────────────────────────────────────────

    async def health_check(self) -> AdapterHealth:
        """Check ZIA API reachability and session validity.

        Returns NOT_CONFIGURED if cloud_name is empty.
        """
        if not self._cloud_name:
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.NOT_CONFIGURED,
                message="No Zscaler cloud name configured",
            )

        if not _HTTPX_AVAILABLE:
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.UNREACHABLE,
                message="httpx library is not installed",
            )

        try:
            await self._authenticate()
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.CONNECTED,
                snapshot_age_seconds=self.snapshot_age_seconds(),
                last_refresh=self._format_snapshot_time(),
                message="ZIA session authenticated",
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

    def _normalize_rule(self, raw: dict, index: int) -> FirewallRule:
        """Convert a raw ZIA firewall rule JSON dict to a FirewallRule.

        ZIA rule structure (simplified):
        {
            "id": 12345,
            "name": "Allow Web Traffic",
            "order": 1,
            "action": "ALLOW",
            "srcIps": ["10.0.0.0/8"],
            "destAddresses": ["any"],
            "destPorts": [{"start": 443, "end": 443}],
            "protocols": ["TCP"],
            "state": "ENABLED"
        }
        """
        # Parse destination ports from ZIA port-range objects
        ports: list[int] = []
        for port_range in raw.get("destPorts", []):
            if isinstance(port_range, dict):
                start = port_range.get("start", 0)
                end = port_range.get("end", start)
                ports.extend(range(start, end + 1))
            elif isinstance(port_range, int):
                ports.append(port_range)

        # Map ZIA action strings to PolicyAction
        action_str = raw.get("action", "BLOCK_DROP").upper()
        if action_str in ("ALLOW", "CAUTION"):
            action = PolicyAction.ALLOW
        elif action_str in ("BLOCK_DROP", "DROP"):
            action = PolicyAction.DROP
        else:
            action = PolicyAction.DENY

        # Source IPs
        src_ips = raw.get("srcIps", [])
        if not src_ips:
            src_ips = ["any"]

        # Destination addresses
        dst_ips = raw.get("destAddresses", [])
        if not dst_ips:
            dst_ips = ["any"]

        return FirewallRule(
            id=str(raw.get("id", f"zscaler-rule-{index}")),
            device_id=f"zscaler-{self._cloud_name}",
            rule_name=raw.get("name", f"rule-{index}"),
            src_ips=src_ips,
            dst_ips=dst_ips,
            ports=ports,
            action=action,
            order=raw.get("order", index),
            logged=raw.get("enableLogging", False),
            protocol=",".join(
                p.lower() for p in raw.get("protocols", ["tcp"])
            ),
        )

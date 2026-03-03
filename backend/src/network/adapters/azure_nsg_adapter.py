"""Azure Network Security Group adapter.

Maps Azure NSG security rules to the common FirewallRule model.
Priority numbers in Azure: lower number = higher priority (100-4096).
"""
import logging
from typing import Optional

from .base import FirewallAdapter, DeviceInterface
from ..models import (
    PolicyVerdict, FirewallVendor, FirewallRule, NATRule, Zone, Route,
    PolicyAction, VerdictMatchType,
)

# Graceful degradation when azure SDK not installed
try:
    from azure.identity import DefaultAzureCredential  # type: ignore
    from azure.mgmt.network import NetworkManagementClient  # type: ignore
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

logger = logging.getLogger(__name__)


class AzureNSGAdapter(FirewallAdapter):
    """Adapter for Azure Network Security Groups.

    Reads NSG security rules via Azure SDK and normalises them to FirewallRule.
    Priority is mapped directly to ``order`` (lower = evaluated first).
    """

    def __init__(
        self,
        subscription_id: str,
        resource_group: str,
        nsg_name: str,
        credential: Optional[object] = None,
        api_endpoint: str = "",
        api_key: str = "",
    ):
        super().__init__(vendor=FirewallVendor.AZURE_NSG, api_endpoint=api_endpoint, api_key=api_key)
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.nsg_name = nsg_name
        self.credential = credential
        self._client: Optional[object] = None

    # ── helpers ──

    def _get_client(self):
        """Lazily create the Azure network management client."""
        if not AZURE_AVAILABLE:
            raise RuntimeError("azure-mgmt-network / azure-identity not installed")
        if self._client is None:
            cred = self.credential or DefaultAzureCredential()
            self._client = NetworkManagementClient(cred, self.subscription_id)
        return self._client

    # ── Core troubleshooting ──

    async def simulate_flow(
        self, src_ip: str, dst_ip: str, port: int, protocol: str = "tcp"
    ) -> PolicyVerdict:
        """Evaluate cached NSG rules in priority order (lower number first).

        Azure NSGs have an implicit deny-all at priority 65500 for custom rules,
        so if no rule matches we return an implicit deny.
        """
        await self._ensure_snapshot()

        for rule in sorted(self._rules_cache, key=lambda r: r.order):
            src_match = self._match_ip(src_ip, rule.src_ips)
            dst_match = self._match_ip(dst_ip, rule.dst_ips)
            port_match = self._match_port(port, rule.ports)
            proto_match = rule.protocol.lower() in (protocol.lower(), "any", "*")

            if src_match and dst_match and port_match and proto_match:
                return PolicyVerdict(
                    action=rule.action,
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    match_type=VerdictMatchType.EXACT,
                    confidence=0.95,
                    details=f"Matched Azure NSG rule '{rule.rule_name}' (priority {rule.order})",
                )

        # Implicit deny-all (Azure default)
        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="implicit-deny-all",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.85,
            details="No matching NSG rule; implicit deny-all applied",
        )

    # ── Snapshot fetchers ──

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch NSG security rules via Azure SDK."""
        if not AZURE_AVAILABLE:
            return []
        try:
            client = self._get_client()
            nsg = client.network_security_groups.get(self.resource_group, self.nsg_name)
            rules: list[FirewallRule] = []
            for sr in (nsg.security_rules or []):
                action = PolicyAction.ALLOW if sr.access.lower() == "allow" else PolicyAction.DENY
                src_ips = self._normalise_addresses(sr.source_address_prefix, sr.source_address_prefixes)
                dst_ips = self._normalise_addresses(sr.destination_address_prefix, sr.destination_address_prefixes)
                ports = self._normalise_ports(sr.destination_port_range, sr.destination_port_ranges)
                rules.append(FirewallRule(
                    id=sr.name,
                    device_id=self.nsg_name,
                    rule_name=sr.name,
                    src_ips=src_ips,
                    dst_ips=dst_ips,
                    ports=ports,
                    protocol=sr.protocol or "any",
                    action=action,
                    order=sr.priority,
                ))
            return rules
        except Exception:
            logger.exception("Azure NSG: failed to fetch rules for %s", self.nsg_name)
            return []

    async def _fetch_routes(self) -> list[Route]:
        """Fetch route tables associated with NSG subnets."""
        if not AZURE_AVAILABLE:
            return []
        try:
            client = self._get_client()
            routes: list[Route] = []
            for rt in client.route_tables.list(self.resource_group):
                for r in (rt.routes or []):
                    routes.append(Route(
                        id=r.name or "",
                        device_id=rt.name or "",
                        destination_cidr=r.address_prefix or "",
                        next_hop=r.next_hop_ip_address or r.next_hop_type or "",
                        protocol="static",
                    ))
            return routes
        except Exception:
            logger.exception("Azure NSG: failed to fetch routes for resource group %s", self.resource_group)
            return []

    async def _fetch_nat_rules(self) -> list[NATRule]:
        # Azure NSGs do not have NAT rules; NAT is handled by Azure LB / NAT Gateway.
        return []

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        return []

    async def _fetch_zones(self) -> list[Zone]:
        # Azure NSGs don't use traditional security zones.
        return []

    # ── Internal helpers ──

    @staticmethod
    def _normalise_addresses(prefix: Optional[str], prefixes: Optional[list]) -> list[str]:
        """Convert Azure address prefix fields to a list."""
        result: list[str] = []
        if prefix and prefix != "*":
            result.append(prefix)
        elif prefix == "*":
            result.append("any")
        if prefixes:
            for p in prefixes:
                result.append("any" if p == "*" else p)
        return result or ["any"]

    @staticmethod
    def _normalise_ports(port_range: Optional[str], port_ranges: Optional[list]) -> list:
        """Convert Azure port range strings to int / (min,max) tuple list (empty = any)."""
        out: list = []
        for pr in filter(None, [port_range] + (port_ranges or [])):
            if pr == "*":
                return []  # any port
            if "-" in pr:
                parts = pr.split("-", 1)
                lo, hi = int(parts[0]), int(parts[1])
                if lo == hi:
                    out.append(lo)
                else:
                    out.append((lo, hi))
            else:
                out.append(int(pr))
        return out

"""Oracle Cloud Infrastructure Network Security Group adapter.

Maps OCI NSG security rules to the common FirewallRule model.
Rules are evaluated in priority order (lower number = higher priority).
"""
import logging
from typing import Optional

from .base import FirewallAdapter, DeviceInterface
from ..models import (
    PolicyVerdict, FirewallVendor, FirewallRule, NATRule, Zone, Route,
    PolicyAction, VerdictMatchType,
)

# Graceful degradation when OCI SDK not installed
try:
    import oci  # type: ignore
    OCI_AVAILABLE = True
except ImportError:
    OCI_AVAILABLE = False

logger = logging.getLogger(__name__)


class OracleNSGAdapter(FirewallAdapter):
    """Adapter for Oracle Cloud Infrastructure Network Security Groups.

    Fetches security rules via the OCI Python SDK and normalises them
    to the common FirewallRule model.  Rules are evaluated by priority.
    """

    def __init__(
        self,
        compartment_id: str,
        nsg_id: str,
        config: Optional[dict] = None,
        api_endpoint: str = "",
        api_key: str = "",
    ):
        super().__init__(vendor=FirewallVendor.ORACLE_NSG, api_endpoint=api_endpoint, api_key=api_key)
        self.compartment_id = compartment_id
        self.nsg_id = nsg_id
        self.oci_config = config
        self._vn_client: Optional[object] = None

    # ── helpers ──

    def _get_vn_client(self):
        """Lazily create the OCI VirtualNetworkClient."""
        if not OCI_AVAILABLE:
            raise RuntimeError("oci SDK is not installed")
        if self._vn_client is None:
            cfg = self.oci_config or oci.config.from_file()
            self._vn_client = oci.core.VirtualNetworkClient(cfg)
        return self._vn_client

    # ── Core troubleshooting ──

    async def simulate_flow(
        self, src_ip: str, dst_ip: str, port: int, protocol: str = "tcp"
    ) -> PolicyVerdict:
        """Evaluate cached OCI NSG rules in priority order."""
        await self._ensure_snapshot()

        for rule in sorted(self._rules_cache, key=lambda r: r.order):
            src_match = self._match_ip(src_ip, rule.src_ips)
            dst_match = self._match_ip(dst_ip, rule.dst_ips)
            port_match = self._match_port(port, rule.ports)
            proto_match = rule.protocol.lower() in (protocol.lower(), "all", "any")

            if src_match and dst_match and port_match and proto_match:
                return PolicyVerdict(
                    action=rule.action,
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    match_type=VerdictMatchType.EXACT,
                    confidence=0.95,
                    details=f"Matched OCI NSG rule '{rule.rule_name}' (order {rule.order})",
                )

        # Implicit deny
        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="implicit-deny",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.85,
            details="No matching OCI NSG rule; implicit deny applied",
        )

    # ── Snapshot fetchers ──

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch NSG security rules via OCI SDK."""
        if not OCI_AVAILABLE:
            return []
        try:
            client = self._get_vn_client()
            resp = client.list_network_security_group_security_rules(self.nsg_id)
            rules: list[FirewallRule] = []
            for idx, sr in enumerate(resp.data or []):
                direction = getattr(sr, "direction", "INGRESS")
                is_stateless = getattr(sr, "is_stateless", False)
                # OCI NSGs are allow-only; DENY rules only exist in OCI Security Lists.
                action = PolicyAction.ALLOW

                src_ips = self._extract_source(sr, direction)
                dst_ips = self._extract_destination(sr, direction)
                ports = self._extract_ports(sr)
                proto = self._protocol_number_to_name(getattr(sr, "protocol", "all"))

                rules.append(FirewallRule(
                    id=getattr(sr, "id", f"oci-rule-{idx}"),
                    device_id=self.nsg_id,
                    rule_name=getattr(sr, "description", f"rule-{idx}") or f"rule-{idx}",
                    src_ips=src_ips,
                    dst_ips=dst_ips,
                    ports=ports,
                    protocol=proto,
                    action=action,
                    order=idx,
                ))
            return rules
        except Exception:
            logger.exception("Oracle NSG: failed to fetch rules for %s", self.nsg_id)
            return []

    async def _fetch_routes(self) -> list[Route]:
        # Routes are in VCN route tables, not NSGs.
        return []

    async def _fetch_nat_rules(self) -> list[NATRule]:
        return []

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        return []

    async def _fetch_zones(self) -> list[Zone]:
        return []

    # ── Internal helpers ──

    @staticmethod
    def _extract_source(rule: object, direction: str) -> list[str]:
        """Extract source addresses respecting OCI rule direction.

        INGRESS rules carry an explicit ``source`` field.
        EGRESS rules originate from the local network so source is "any".
        """
        if direction == "INGRESS":
            src = getattr(rule, "source", None)
            if src:
                return [src]
        return ["any"]

    @staticmethod
    def _extract_destination(rule: object, direction: str) -> list[str]:
        """Extract destination addresses respecting OCI rule direction.

        EGRESS rules carry an explicit ``destination`` field.
        INGRESS rules target the local network so destination is "any".
        """
        if direction == "EGRESS":
            dst = getattr(rule, "destination", None)
            if dst:
                return [dst]
        return ["any"]

    @staticmethod
    def _extract_ports(rule: object) -> list:
        """Extract port range from TCP/UDP options."""
        ports: list = []
        for attr in ("tcp_options", "udp_options"):
            opts = getattr(rule, attr, None)
            if opts:
                dst_range = getattr(opts, "destination_port_range", None)
                if dst_range:
                    mn = getattr(dst_range, "min", 0)
                    mx = getattr(dst_range, "max", 0)
                    if mn and mx:
                        if mn == mx:
                            ports.append(mn)
                        else:
                            ports.append((mn, mx))
                        return ports
        return ports

    @staticmethod
    def _protocol_number_to_name(proto: str) -> str:
        """Map IANA protocol number to name."""
        mapping = {"6": "tcp", "17": "udp", "1": "icmp", "all": "any"}
        return mapping.get(str(proto).lower(), str(proto))

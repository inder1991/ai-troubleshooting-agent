"""Mock firewall adapter for testing and demo purposes."""
from .base import FirewallAdapter, DeviceInterface, VRF, VirtualRouter
from ..models import (
    PolicyVerdict, FirewallVendor, FirewallRule, NATRule, Zone, Route,
    PolicyAction, VerdictMatchType,
)


class MockFirewallAdapter(FirewallAdapter):
    """Returns configurable mock responses. Used in tests and demos."""

    def __init__(self, vendor: FirewallVendor = FirewallVendor.PALO_ALTO,
                 rules: list[FirewallRule] = None,
                 nat_rules: list[NATRule] = None,
                 zones: list[Zone] = None,
                 default_action: PolicyAction = PolicyAction.DENY,
                 api_endpoint: str = "",
                 api_key: str = "",
                 extra_config: dict = None):
        super().__init__(vendor=vendor, api_endpoint=api_endpoint, api_key=api_key)
        self._mock_rules = rules or []
        self._mock_nat_rules = nat_rules or []
        self._mock_zones = zones or []
        self._default_action = default_action
        self._api_endpoint = api_endpoint
        self._api_key = api_key
        self.extra_config = extra_config or {}

    async def simulate_flow(self, src_ip: str, dst_ip: str, port: int,
                           protocol: str = "tcp") -> PolicyVerdict:
        await self._ensure_snapshot()
        # Evaluate rules in priority order
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
                    details=f"Matched rule {rule.rule_name} (order {rule.order})",
                    matched_source=",".join(rule.src_ips) if rule.src_ips else "",
                    matched_destination=",".join(rule.dst_ips) if rule.dst_ips else "",
                    matched_ports=",".join(str(p) for p in rule.ports) if rule.ports else "",
                )
        # No explicit match -> implicit deny
        return PolicyVerdict(
            action=self._default_action,
            rule_name="implicit-deny",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.75,
            details="No matching rule found, implicit deny",
        )

    async def _fetch_rules(self) -> list[FirewallRule]:
        return list(self._mock_rules)

    async def _fetch_nat_rules(self) -> list[NATRule]:
        return list(self._mock_nat_rules)

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        return []

    async def _fetch_routes(self) -> list[Route]:
        return []

    async def _fetch_zones(self) -> list[Zone]:
        return list(self._mock_zones)

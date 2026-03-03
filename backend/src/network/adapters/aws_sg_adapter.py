"""AWS Security Group adapter.

Maps EC2 Security Group ingress/egress rules to the common FirewallRule model.
AWS SGs are stateful: if an inbound rule allows traffic, the return traffic is
automatically allowed regardless of outbound rules.
"""
import logging
from typing import Optional

from .base import FirewallAdapter, DeviceInterface
from ..models import (
    PolicyVerdict, FirewallVendor, FirewallRule, NATRule, Zone, Route,
    PolicyAction, VerdictMatchType,
)

# Graceful degradation when boto3 not installed
try:
    import boto3  # type: ignore
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

logger = logging.getLogger(__name__)


class AWSSGAdapter(FirewallAdapter):
    """Adapter for AWS EC2 Security Groups.

    Security Groups are *allow-only* and stateful.  There is no explicit deny;
    traffic not matched by any allow rule is implicitly denied.
    """

    def __init__(
        self,
        region: str,
        security_group_id: str,
        aws_access_key: Optional[str] = None,
        aws_secret_key: Optional[str] = None,
        api_endpoint: str = "",
        api_key: str = "",
    ):
        super().__init__(vendor=FirewallVendor.AWS_SG, api_endpoint=api_endpoint, api_key=api_key)
        self.region = region
        self.security_group_id = security_group_id
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self._ec2_client: Optional[object] = None

    # ── helpers ──

    def _get_ec2_client(self):
        """Lazily create the boto3 EC2 client."""
        if not BOTO3_AVAILABLE:
            raise RuntimeError("boto3 is not installed")
        if self._ec2_client is None:
            kwargs: dict = {"region_name": self.region}
            if self.aws_access_key and self.aws_secret_key:
                kwargs["aws_access_key_id"] = self.aws_access_key
                kwargs["aws_secret_access_key"] = self.aws_secret_key
            self._ec2_client = boto3.client("ec2", **kwargs)
        return self._ec2_client

    # ── Core troubleshooting ──

    async def simulate_flow(
        self, src_ip: str, dst_ip: str, port: int, protocol: str = "tcp"
    ) -> PolicyVerdict:
        """Evaluate cached SG rules.

        AWS Security Groups are allow-only and stateful:
        - If an inbound rule allows the traffic, the flow is allowed and
          return traffic is automatically permitted.
        - If no rule matches, traffic is implicitly denied.
        """
        await self._ensure_snapshot()

        for rule in sorted(self._rules_cache, key=lambda r: r.order):
            src_match = self._match_ip(src_ip, rule.src_ips)
            dst_match = self._match_ip(dst_ip, rule.dst_ips)
            port_match = self._match_port(port, rule.ports)
            proto_match = rule.protocol.lower() in (protocol.lower(), "-1", "all", "any")

            if src_match and dst_match and port_match and proto_match:
                return PolicyVerdict(
                    action=PolicyAction.ALLOW,
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    match_type=VerdictMatchType.EXACT,
                    confidence=0.95,
                    details=(
                        f"Matched AWS SG rule '{rule.rule_name}' "
                        f"(stateful – return traffic automatically allowed)"
                    ),
                )

        # SG implicit deny (no matching allow rule)
        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="implicit-deny",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.85,
            details="No matching Security Group allow rule; implicit deny",
        )

    # ── Snapshot fetchers ──

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch SG ingress + egress rules via boto3 ``describe_security_groups``."""
        if not BOTO3_AVAILABLE:
            return []
        try:
            client = self._get_ec2_client()
            resp = client.describe_security_groups(GroupIds=[self.security_group_id])
            rules: list[FirewallRule] = []
            for sg in resp.get("SecurityGroups", []):
                rules.extend(self._parse_permissions(sg, "IpPermissions", direction="ingress"))
                rules.extend(self._parse_permissions(sg, "IpPermissionsEgress", direction="egress"))
            return rules
        except Exception:
            logger.exception("AWS SG: failed to fetch rules for %s", self.security_group_id)
            return []

    async def _fetch_routes(self) -> list[Route]:
        # Routes are managed at VPC route-table level, not SG level.
        return []

    async def _fetch_nat_rules(self) -> list[NATRule]:
        # NAT is handled by NAT Gateways, not Security Groups.
        return []

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        return []

    async def _fetch_zones(self) -> list[Zone]:
        return []

    # ── Internal helpers ──

    def _parse_permissions(
        self, sg: dict, key: str, direction: str
    ) -> list[FirewallRule]:
        """Convert AWS IpPermissions to FirewallRule list."""
        rules: list[FirewallRule] = []
        sg_id = sg.get("GroupId", self.security_group_id)
        for idx, perm in enumerate(sg.get(key, [])):
            proto = perm.get("IpProtocol", "-1")
            from_port = perm.get("FromPort", 0)
            to_port = perm.get("ToPort", 0)
            ports: list = []
            if proto != "-1" and from_port and to_port:
                if from_port == to_port:
                    ports = [from_port]
                else:
                    ports = [(from_port, to_port)]

            cidrs = [r["CidrIp"] for r in perm.get("IpRanges", [])]
            cidrs += [r["CidrIpv6"] for r in perm.get("Ipv6Ranges", [])]
            if not cidrs:
                cidrs = ["any"]

            src_ips = cidrs if direction == "ingress" else ["any"]
            dst_ips = ["any"] if direction == "ingress" else cidrs

            rules.append(FirewallRule(
                id=f"{sg_id}-{direction}-{idx}",
                device_id=sg_id,
                rule_name=f"{direction}-{idx}",
                src_ips=src_ips,
                dst_ips=dst_ips,
                ports=ports,
                protocol="any" if proto == "-1" else proto,
                action=PolicyAction.ALLOW,  # SGs are allow-only
                order=idx,
            ))
        return rules

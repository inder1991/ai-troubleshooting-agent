"""Topology data-integrity validator.

Detects duplicate IPs, orphan interfaces, subnet overlaps, and other
structural issues in the network topology graph.
"""

from __future__ import annotations

import ipaddress
from collections import defaultdict
from typing import Any

from .domain import Device, Interface, IPAddress, Route, Subnet


class TopologyValidator:
    """Stateless validator that checks topology entities for data-integrity issues."""

    # ── Individual checks ──────────────────────────────────────────────

    def check_duplicate_ips(self, ip_addresses: list[IPAddress]) -> list[dict[str, Any]]:
        """Return issues for any IP string assigned to more than one interface."""
        by_ip: dict[str, list[str]] = defaultdict(list)
        for addr in ip_addresses:
            by_ip[addr.ip].append(addr.assigned_to)

        issues: list[dict[str, Any]] = []
        for ip, assigned_to in by_ip.items():
            if len(assigned_to) >= 2:
                issues.append(
                    {
                        "type": "duplicate_ip",
                        "severity": "critical",
                        "ip": ip,
                        "assigned_to": assigned_to,
                        "message": f"IP {ip} is assigned to {len(assigned_to)} interfaces: {', '.join(assigned_to)}",
                    }
                )
        return issues

    def check_orphan_interfaces(
        self, devices: list[Device], interfaces: list[Interface]
    ) -> list[dict[str, Any]]:
        """Return issues for interfaces whose device_id has no matching Device."""
        device_ids = {d.id for d in devices}
        issues: list[dict[str, Any]] = []
        for iface in interfaces:
            if iface.device_id not in device_ids:
                issues.append(
                    {
                        "type": "orphan_interface",
                        "severity": "high",
                        "interface_id": iface.id,
                        "device_id": iface.device_id,
                        "message": f"Interface {iface.id} references non-existent device {iface.device_id}",
                    }
                )
        return issues

    def check_subnet_overlaps(self, subnets: list[Subnet]) -> list[dict[str, Any]]:
        """Return issues for each pair of subnets that overlap but are not equal."""
        networks = [
            (s, ipaddress.ip_network(s.cidr, strict=False)) for s in subnets
        ]
        issues: list[dict[str, Any]] = []
        for i in range(len(networks)):
            for j in range(i + 1, len(networks)):
                subnet_a, net_a = networks[i]
                subnet_b, net_b = networks[j]
                if net_a.overlaps(net_b) and net_a != net_b:
                    issues.append(
                        {
                            "type": "subnet_overlap",
                            "severity": "high",
                            "subnet_a": subnet_a.id,
                            "subnet_b": subnet_b.id,
                            "cidr_a": subnet_a.cidr,
                            "cidr_b": subnet_b.cidr,
                            "message": (
                                f"Subnet {subnet_a.cidr} ({subnet_a.id}) overlaps with "
                                f"{subnet_b.cidr} ({subnet_b.id})"
                            ),
                        }
                    )
        return issues

    # ── Aggregate ──────────────────────────────────────────────────────

    def validate(
        self,
        devices: list[Device],
        interfaces: list[Interface],
        ip_addresses: list[IPAddress],
        subnets: list[Subnet],
        routes: list[Route],
    ) -> dict[str, Any]:
        """Run every check and return a summary dict."""
        issues: list[dict[str, Any]] = []
        issues.extend(self.check_duplicate_ips(ip_addresses))
        issues.extend(self.check_orphan_interfaces(devices, interfaces))
        issues.extend(self.check_subnet_overlaps(subnets))

        severity_counts = {"critical": 0, "high": 0, "medium": 0}
        for issue in issues:
            sev = issue.get("severity", "medium")
            if sev in severity_counts:
                severity_counts[sev] += 1

        return {
            "issues": issues,
            "issue_count": len(issues),
            **severity_counts,
        }

"""IPAM Report Generators — subnet inventory, IP allocation, conflicts, and capacity forecast."""
import csv
import io
from datetime import datetime, timezone
from .topology_store import TopologyStore


def generate_subnet_report(store: TopologyStore) -> list[dict]:
    """Subnet inventory report with utilization."""
    subnets = store.list_subnets()
    result = []
    for s in subnets:
        util = store.get_subnet_utilization(s.id)
        result.append({
            "subnet_id": s.id,
            "cidr": s.cidr,
            "description": s.description,
            "region": s.region,
            "environment": s.environment,
            "zone_id": s.zone_id,
            "vlan_id": s.vlan_id,
            "gateway_ip": s.gateway_ip,
            "ip_version": s.ip_version,
            "parent_subnet_id": s.parent_subnet_id,
            "total_ips": util.get("total", 0),
            "assigned": util.get("assigned", 0),
            "available": util.get("available", 0),
            "reserved": util.get("reserved", 0),
            "utilization_pct": util.get("utilization_pct", 0),
        })
    return result


def generate_ip_allocation_report(store: TopologyStore, subnet_id: str = "",
                                   status: str = "") -> list[dict]:
    """IP allocation report by device/status/subnet."""
    result = store.list_ip_addresses(subnet_id=subnet_id or None,
                                      status=status or None)
    ips = result["ips"] if isinstance(result, dict) else result
    report = []
    for ip in ips:
        d = ip.model_dump() if hasattr(ip, 'model_dump') else ip
        report.append(d)
    return report


def generate_conflict_report(store: TopologyStore) -> dict:
    """Combined conflict report: duplicate IPs + DNS mismatches."""
    conflicts = store.detect_ip_conflicts()
    dns_mismatches = store.detect_dns_mismatches()
    return {
        "duplicate_ips": conflicts,
        "dns_mismatches": dns_mismatches,
        "total_issues": len(conflicts) + len(dns_mismatches),
    }


def generate_capacity_report(store: TopologyStore) -> list[dict]:
    """Capacity forecast report."""
    return store.get_capacity_forecast()


def report_to_csv(data: list[dict]) -> str:
    """Convert a list of dicts to CSV string."""
    if not data:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    for row in data:
        writer.writerow(row)
    return output.getvalue()

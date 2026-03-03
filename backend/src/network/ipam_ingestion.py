"""IPAM data ingestion — CSV/Excel upload and parsing."""
import csv
import io
import ipaddress
import uuid
from typing import Optional
from .models import Device, Subnet, Interface, DeviceType
from .topology_store import TopologyStore


def _infer_device_type(name: str, row: dict) -> DeviceType:
    """Infer device type from name patterns or explicit column."""
    explicit = row.get("device_type", "").strip().upper()
    if explicit and hasattr(DeviceType, explicit):
        return DeviceType[explicit]
    name_lower = name.lower()
    if any(k in name_lower for k in ("fw", "firewall", "palo", "asa")):
        return DeviceType.FIREWALL
    if any(k in name_lower for k in ("router", "rtr", "gw", "gateway")):
        return DeviceType.ROUTER
    if any(k in name_lower for k in ("switch", "sw")):
        return DeviceType.SWITCH
    if any(k in name_lower for k in ("lb", "loadbalancer", "load-balancer", "nlb", "alb")):
        return DeviceType.LOAD_BALANCER
    return DeviceType.HOST


def parse_ipam_csv(content: str, store: TopologyStore) -> dict:
    """Parse CSV with columns: ip, subnet, device, zone, vlan, description,
    vendor, location (or site), device_type (optional).
    Creates/updates devices, subnets, and interfaces in the store.
    Returns summary: {devices_added, subnets_added, interfaces_added, errors}.
    """
    reader = csv.DictReader(io.StringIO(content))
    stats = {"devices_added": 0, "subnets_added": 0, "interfaces_added": 0, "errors": []}
    seen_devices = set()
    seen_subnets = set()
    seen_ips = set()

    for row_num, row in enumerate(reader, start=2):
        try:
            ip = row.get("ip", "").strip()
            subnet_cidr = row.get("subnet", "").strip()
            device_name = row.get("device", "").strip()
            zone = row.get("zone", "").strip()
            vlan = row.get("vlan", "0").strip()
            description = row.get("description", "").strip()

            if not ip and not subnet_cidr:
                continue

            # Validate IP address
            if ip:
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    stats["errors"].append(f"Row {row_num}: Invalid IP address '{ip}'")
                    continue

            # Validate subnet CIDR
            if subnet_cidr:
                try:
                    ipaddress.ip_network(subnet_cidr, strict=False)
                except ValueError:
                    stats["errors"].append(f"Row {row_num}: Invalid CIDR '{subnet_cidr}'")
                    continue

            # Duplicate IP detection
            if ip:
                if ip in seen_ips:
                    stats["errors"].append(f"Row {row_num}: Duplicate IP '{ip}'")
                    continue
                seen_ips.add(ip)

            # Create/update subnet
            if subnet_cidr and subnet_cidr not in seen_subnets:
                subnet_id = f"subnet-{subnet_cidr.replace('/', '-')}"
                store.add_subnet(Subnet(
                    id=subnet_id, cidr=subnet_cidr, vlan_id=int(vlan or 0),
                    zone_id=zone, description=description,
                ))
                seen_subnets.add(subnet_cidr)
                stats["subnets_added"] += 1

            # Create/update device
            if device_name and device_name not in seen_devices:
                device_id = f"device-{device_name.lower().replace(' ', '-')}"
                vendor = row.get("vendor", "").strip()
                location = row.get("location", "").strip() or row.get("site", "").strip()
                store.add_device(Device(
                    id=device_id, name=device_name,
                    device_type=_infer_device_type(device_name, row),
                    management_ip=ip,
                    vendor=vendor,
                    location=location,
                    zone_id=zone,
                    vlan_id=int(vlan or 0),
                    description=description,
                ))
                seen_devices.add(device_name)
                stats["devices_added"] += 1

            # Create interface
            if ip and device_name:
                device_id = f"device-{device_name.lower().replace(' ', '-')}"
                iface_id = f"iface-{device_id}-{ip.replace('.', '-')}"
                store.add_interface(Interface(
                    id=iface_id, device_id=device_id, name=f"eth-{ip}",
                    ip=ip, zone_id=zone,
                ))
                stats["interfaces_added"] += 1

        except Exception as e:
            stats["errors"].append(f"Row {row_num}: {str(e)}")

    return stats


def parse_ipam_excel(file_bytes: bytes, store: TopologyStore) -> dict:
    """Parse Excel (.xlsx) file with same columns as CSV.
    Requires openpyxl. Returns same stats dict.
    """
    try:
        import openpyxl
    except ImportError:
        return {"devices_added": 0, "subnets_added": 0, "interfaces_added": 0,
                "errors": ["openpyxl not installed"]}

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"devices_added": 0, "subnets_added": 0, "interfaces_added": 0, "errors": []}

    headers = [str(h).strip().lower() if h else "" for h in rows[0]]
    csv_lines = []
    csv_lines.append(",".join(headers))
    for row in rows[1:]:
        csv_lines.append(",".join(str(v).strip() if v else "" for v in row))

    return parse_ipam_csv("\n".join(csv_lines), store)

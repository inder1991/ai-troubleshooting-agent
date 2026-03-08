"""IPAM data ingestion — CSV/Excel upload and parsing."""
import csv
import io
import ipaddress
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from .models import Device, Subnet, Interface, DeviceType, IPAddress
from .topology_store import TopologyStore


def _infer_device_type(name: str, row: dict) -> DeviceType:
    """Infer device type from name patterns or explicit column."""
    explicit = row.get("device_type", "").strip().upper()
    if explicit:
        # Try exact match first, then common aliases
        if hasattr(DeviceType, explicit):
            return DeviceType[explicit]
        aliases = {"FW": "FIREWALL", "RTR": "ROUTER", "SW": "SWITCH", "LB": "LOAD_BALANCER"}
        if explicit in aliases and hasattr(DeviceType, aliases[explicit]):
            return DeviceType[aliases[explicit]]
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


def _sanitize_id(raw: str) -> str:
    """Sanitize a string for use as an ID (handles IPv6 colons, dots, slashes)."""
    return re.sub(r'[^a-zA-Z0-9\-]', '-', raw)


def parse_ipam_csv(content: str, store: TopologyStore) -> dict:
    """Parse CSV with columns: ip, subnet, device, zone, vlan, description,
    vendor, location (or site), device_type (optional).
    Creates/updates devices, subnets, and interfaces in the store.
    Returns summary: {devices_added, subnets_added, interfaces_added, errors}.
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or not {'ip', 'subnet'}.issubset(set(reader.fieldnames)):
        return {"devices_added": 0, "subnets_added": 0, "interfaces_added": 0,
                "errors": ["CSV must contain at least 'ip' and 'subnet' columns"]}
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

            # Validate IP is within declared subnet
            if ip and subnet_cidr:
                try:
                    net = ipaddress.ip_network(subnet_cidr, strict=False)
                    if ipaddress.ip_address(ip) not in net:
                        stats["errors"].append(
                            f"Row {row_num}: IP '{ip}' is not within subnet '{subnet_cidr}'"
                        )
                        continue
                except ValueError:
                    pass  # Already caught above

            # Validate VLAN range
            try:
                vlan_int = int(vlan or 0)
            except (ValueError, TypeError):
                stats["errors"].append(f"Row {row_num}: Invalid VLAN value '{vlan}'")
                vlan_int = 0
            if vlan_int != 0 and (vlan_int < 1 or vlan_int > 4094):
                stats["errors"].append(f"Row {row_num}: VLAN {vlan_int} out of range (1-4094)")
                vlan_int = 0  # Reset to unset but don't skip row

            # Create/update subnet
            if subnet_cidr and subnet_cidr not in seen_subnets:
                subnet_id = f"subnet-{_sanitize_id(subnet_cidr)}"
                region = row.get("region", "").strip()
                environment = row.get("environment", "").strip()
                net_obj = ipaddress.ip_network(subnet_cidr, strict=False)
                ip_ver = 6 if net_obj.version == 6 else 4
                store.add_subnet(Subnet(
                    id=subnet_id, cidr=subnet_cidr, vlan_id=vlan_int,
                    zone_id=zone, description=description,
                    region=region, environment=environment,
                    ip_version=ip_ver,
                ))
                seen_subnets.add(subnet_cidr)
                stats["subnets_added"] += 1

            # Validate gateway IP if provided
            gateway = row.get("gateway", "").strip()
            if gateway and subnet_cidr:
                try:
                    net = ipaddress.ip_network(subnet_cidr, strict=False)
                    if ipaddress.ip_address(gateway) not in net:
                        stats["errors"].append(
                            f"Row {row_num}: Gateway '{gateway}' is not within subnet '{subnet_cidr}'"
                        )
                except ValueError:
                    pass

            # Create/update device
            if device_name and device_name not in seen_devices:
                device_id = f"device-{_sanitize_id(device_name.lower())}"
                vendor = row.get("vendor", "").strip()
                location = row.get("location", "").strip() or row.get("site", "").strip()

                # Check if device already exists — merge instead of overwrite
                existing = store.get_device(device_id)
                if existing:
                    # Only update fields that are provided and non-empty in CSV
                    if vendor:
                        existing.vendor = vendor
                    if location:
                        existing.location = location
                    if ip:
                        existing.management_ip = ip
                    if zone:
                        existing.zone_id = zone
                    if vlan_int:
                        existing.vlan_id = vlan_int
                    if description:
                        existing.description = description
                    store.add_device(existing)
                    stats["devices_updated"] = stats.get("devices_updated", 0) + 1
                else:
                    store.add_device(Device(
                        id=device_id, name=device_name,
                        device_type=_infer_device_type(device_name, row),
                        management_ip=ip,
                        vendor=vendor,
                        location=location,
                        zone_id=zone,
                        vlan_id=vlan_int,
                        description=description,
                    ))
                    stats["devices_added"] += 1
                seen_devices.add(device_name)

            # Create interface
            if ip and device_name:
                device_id = f"device-{_sanitize_id(device_name.lower())}"
                iface_name = row.get("interface_name", "").strip() or f"eth-{ip}"
                iface_role = row.get("interface_role", "").strip()
                iface_id = f"iface-{device_id}-{_sanitize_id(ip)}"

                # Resolve subnet_id from IP
                iface_subnet_id = ""
                if subnet_cidr:
                    iface_subnet_id = f"subnet-{_sanitize_id(subnet_cidr)}"

                store.add_interface(Interface(
                    id=iface_id, device_id=device_id, name=iface_name,
                    ip=ip, zone_id=zone, role=iface_role,
                    subnet_id=iface_subnet_id,
                ))
                stats["interfaces_added"] += 1

        except Exception as e:
            stats["errors"].append(f"Row {row_num}: {str(e)}")

    # Detect overlapping subnets and set parent-child relationships
    subnet_list = list(seen_subnets)
    for i in range(len(subnet_list)):
        for j in range(i + 1, len(subnet_list)):
            try:
                a = ipaddress.ip_network(subnet_list[i], strict=False)
                b = ipaddress.ip_network(subnet_list[j], strict=False)
                if a.overlaps(b):
                    # If one is a strict subset of the other, set parent
                    if a.supernet_of(b) and a != b:
                        child_id = f"subnet-{_sanitize_id(subnet_list[j])}"
                        parent_id = f"subnet-{_sanitize_id(subnet_list[i])}"
                        store.update_subnet(child_id, parent_subnet_id=parent_id)
                    elif b.supernet_of(a) and a != b:
                        child_id = f"subnet-{_sanitize_id(subnet_list[i])}"
                        parent_id = f"subnet-{_sanitize_id(subnet_list[j])}"
                        store.update_subnet(child_id, parent_subnet_id=parent_id)
                    else:
                        stats["errors"].append(
                            f"Overlapping subnets detected: '{subnet_list[i]}' and '{subnet_list[j]}'"
                        )
            except ValueError:
                pass

    # Auto-populate IP addresses for each imported subnet
    ips_populated = 0
    for cidr in seen_subnets:
        subnet_id = f"subnet-{_sanitize_id(cidr)}"
        subnet = store.get_subnet(subnet_id)
        if subnet:
            ips_populated += populate_subnet_ips(store, subnet)
    stats["ips_populated"] = ips_populated

    # Mark IPs that match existing interfaces as assigned
    for cidr in seen_subnets:
        subnet_id = f"subnet-{_sanitize_id(cidr)}"
        interfaces = store.list_interfaces()
        for iface in interfaces:
            if iface.ip and iface.subnet_id == subnet_id:
                ip_rec = store.get_ip_by_address(iface.ip)
                if ip_rec and ip_rec.status == "available":
                    store.update_ip_status(
                        ip_rec.id, "assigned",
                        device_id=iface.device_id,
                        interface_id=iface.id,
                    )

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

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
    except Exception as e:
        return {"devices_added": 0, "subnets_added": 0, "interfaces_added": 0,
                "errors": [f"Failed to read Excel file: {e}"]}
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


def populate_subnet_ips(store: TopologyStore, subnet: "Subnet") -> int:
    """Lazy allocation: only create gateway IP row (if set) and initialize free ranges.
    No longer creates a row per host IP. Returns count of IPs created (0 or 1).
    """
    try:
        net = ipaddress.ip_network(subnet.cidr, strict=False)
    except ValueError:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    created = 0
    gateway = subnet.gateway_ip

    # Only create gateway IP record
    if gateway:
        ip_id = f"ip-{_sanitize_id(subnet.id)}-{_sanitize_id(gateway)}"
        store.bulk_create_ip_addresses([IPAddress(
            id=ip_id,
            address=gateway,
            subnet_id=subnet.id,
            status="assigned",
            ip_type="gateway",
            created_at=now,
        )])
        created = 1

    # Initialize free ranges for O(1) allocation
    store.init_free_ranges(subnet.id, subnet.cidr, gateway)
    return created


def reconcile_discovered_ips(store: TopologyStore, candidates: list[dict]) -> dict:
    """Reconcile discovered IPs with IPAM records.
    Updates last_seen, mac, hostname, discovery_source, confidence on known IPs.
    Returns stats: {updated, rogue_ips}.
    """
    stats = {"updated": 0, "rogue_ips": []}
    now = datetime.now(timezone.utc).isoformat()
    for c in candidates:
        ip_addr = c.get("ip", "")
        if not ip_addr:
            continue
        ip_rec = store.get_ip_by_address(ip_addr)
        if ip_rec:
            updates = {"last_seen": now}
            if c.get("mac"):
                updates["mac_address"] = c["mac"]
            if c.get("hostname"):
                updates["hostname"] = c["hostname"]
            if c.get("discovered_via"):
                updates["discovery_source"] = c["discovered_via"]
            if c.get("confidence_score"):
                updates["confidence_score"] = c["confidence_score"]
            store.update_ip_address(ip_rec.id, **updates)
            stats["updated"] += 1
        else:
            # IP not in any known subnet — rogue IP
            stats["rogue_ips"].append(ip_addr)
    return stats

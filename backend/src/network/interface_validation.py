"""Multi-interface validation rules for network appliances."""
import ipaddress
from .models import Interface, Subnet, Zone


def validate_device_interfaces(
    device_id: str,
    interfaces: list[Interface],
    subnets: list[Subnet],
    zones: list[Zone],
) -> list[dict]:
    """Validate interfaces for a single device.

    Returns list of dicts: {rule, field, message, severity, interface_id}.
    """
    errors: list[dict] = []
    subnet_map = {s.id: s for s in subnets}
    zone_map = {z.id: z for z in zones}

    # Rule 29: Interface IP must be within its assigned subnet CIDR
    for iface in interfaces:
        if not iface.ip or not iface.subnet_id:
            continue
        subnet = subnet_map.get(iface.subnet_id)
        if not subnet:
            continue
        try:
            net = ipaddress.ip_network(subnet.cidr, strict=False)
            if ipaddress.ip_address(iface.ip) not in net:
                errors.append({
                    "rule": 29,
                    "field": "ip",
                    "message": (
                        f"Interface '{iface.name}' IP {iface.ip} is outside "
                        f"subnet '{subnet.id}' CIDR {subnet.cidr}"
                    ),
                    "severity": "error",
                    "interface_id": iface.id,
                })
        except ValueError:
            pass

    # Rule 30: No two non-sync interfaces may share a zone on the same device
    zone_ifaces: dict[str, list[Interface]] = {}
    for iface in interfaces:
        if not iface.zone_id or iface.role == "sync":
            continue
        zone_ifaces.setdefault(iface.zone_id, []).append(iface)

    for zone_id, iface_list in zone_ifaces.items():
        if len(iface_list) > 1:
            names = ", ".join(f"'{i.name}'" for i in iface_list)
            errors.append({
                "rule": 30,
                "field": "zone_id",
                "message": (
                    f"Interfaces {names} on device '{device_id}' share "
                    f"zone '{zone_id}' — each interface should be in a unique zone"
                ),
                "severity": "error",
                "interface_id": iface_list[0].id,
            })

    # Rule 31: Management interface should not be in a data/dmz zone
    for iface in interfaces:
        if iface.role != "management" or not iface.zone_id:
            continue
        zone = zone_map.get(iface.zone_id)
        if not zone or not zone.zone_type:
            continue
        if zone.zone_type in ("data", "dmz"):
            errors.append({
                "rule": 31,
                "field": "role",
                "message": (
                    f"Management interface '{iface.name}' is in "
                    f"{zone.zone_type} zone '{zone.name}' — "
                    f"management interfaces should be in a management zone"
                ),
                "severity": "warning",
                "interface_id": iface.id,
            })

    return errors

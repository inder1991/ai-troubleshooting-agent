"""HA group validation rules."""
import ipaddress
from .models import HAGroup, HAMode
from .topology_store import TopologyStore


def validate_ha_group(store: TopologyStore, group: HAGroup) -> list[str]:
    """Validate an HA group against stored topology. Returns list of error strings."""
    errors: list[str] = []

    # Load member devices
    members = []
    for mid in group.member_ids:
        device = store.get_device(mid)
        if not device:
            errors.append(f"Member device '{mid}' not found")
            continue
        members.append(device)

    if len(members) < 2:
        return errors  # can't validate further

    # Rule 20: Members must be same device type
    types = set(m.device_type for m in members)
    if len(types) > 1:
        errors.append(f"HA members must be same device type, found: {', '.join(t.value for t in types)}")

    # Rule 21: Members must be in same subnet
    member_ips = [m.management_ip for m in members if m.management_ip]
    if member_ips:
        subnets = store.list_subnets()
        member_subnets: dict[str, str] = {}
        for mip in member_ips:
            for s in subnets:
                try:
                    if ipaddress.ip_address(mip) in ipaddress.ip_network(s.cidr, strict=False):
                        member_subnets[mip] = s.cidr
                        break
                except ValueError:
                    pass
        subnet_set = set(member_subnets.values())
        if len(subnet_set) > 1:
            errors.append(f"HA members must be in same subnet, found: {', '.join(subnet_set)}")
        elif not subnet_set and len(member_ips) >= 2:
            # No known subnets matched; fall back to /24 comparison
            networks_24 = set()
            for mip in member_ips:
                try:
                    networks_24.add(ipaddress.ip_network(f"{mip}/24", strict=False))
                except ValueError:
                    pass
            if len(networks_24) > 1:
                errors.append(
                    f"HA members must be in same subnet, found IPs in different /24 networks: "
                    f"{', '.join(str(n) for n in networks_24)}"
                )

    # Rule 22: VIPs must be in member subnet
    if group.virtual_ips and member_ips:
        subnets = store.list_subnets()
        for vip in group.virtual_ips:
            vip_in_subnet = False
            for s in subnets:
                try:
                    if ipaddress.ip_address(vip) in ipaddress.ip_network(s.cidr, strict=False):
                        for mip in member_ips:
                            try:
                                if ipaddress.ip_address(mip) in ipaddress.ip_network(s.cidr, strict=False):
                                    vip_in_subnet = True
                                    break
                            except ValueError:
                                pass
                        if vip_in_subnet:
                            break
                except ValueError:
                    pass
            if not vip_in_subnet:
                errors.append(f"VIP '{vip}' is not within any subnet containing HA members")

    # Rule 24: Active-passive needs exactly 1 active
    if group.ha_mode == HAMode.ACTIVE_PASSIVE:
        if not group.active_member_id:
            errors.append("Active-passive HA group requires an active member to be designated")
        elif group.active_member_id not in group.member_ids:
            errors.append(f"Active member '{group.active_member_id}' is not in member list")

    return errors

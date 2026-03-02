"""NAT resolver node — tracks address translation chain through firewalls."""
from src.network.adapters.base import FirewallAdapter
from src.network.models import NATDirection


async def nat_resolver(state: dict, *, adapters: dict[str, FirewallAdapter]) -> dict:
    """Resolve NAT translations along the path.

    Builds an identity chain: tracks how source/destination IPs and ports
    change through each firewall performing NAT.
    """
    firewalls = state.get("firewalls_in_path", [])
    src_ip = state.get("src_ip", "")
    dst_ip = state.get("dst_ip", "")
    port = state.get("port", 0)

    if not firewalls:
        return {
            "nat_translations": [],
            "identity_chain": [{"stage": "original", "ip": src_ip, "port": port}],
        }

    identity_chain = [{"stage": "original", "ip": src_ip, "port": port}]
    translations = []
    current_src = src_ip
    current_dst = dst_ip
    current_port = port

    for fw in firewalls:
        device_id = fw.get("device_id", "")
        adapter = adapters.get(device_id)
        if not adapter:
            continue

        try:
            nat_rules = await adapter.get_nat_rules()
        except Exception:
            continue

        for rule in nat_rules:
            # Check SNAT: original source matches
            if rule.direction == NATDirection.SNAT:
                if _ip_in_range(current_src, rule.original_src):
                    translation = {
                        "device_id": device_id,
                        "direction": "snat",
                        "original_src": current_src,
                        "translated_src": rule.translated_src,
                        "rule_id": rule.rule_id or rule.id,
                    }
                    translations.append(translation)
                    current_src = rule.translated_src
                    identity_chain.append({
                        "stage": f"post-snat-{device_id}",
                        "ip": current_src,
                        "port": current_port,
                        "device_id": device_id,
                    })

            # Check DNAT: original destination matches
            elif rule.direction == NATDirection.DNAT:
                if _ip_in_range(current_dst, rule.original_dst):
                    translation = {
                        "device_id": device_id,
                        "direction": "dnat",
                        "original_dst": current_dst,
                        "translated_dst": rule.translated_dst,
                        "original_port": current_port,
                        "translated_port": rule.translated_port or current_port,
                        "rule_id": rule.rule_id or rule.id,
                    }
                    translations.append(translation)
                    current_dst = rule.translated_dst
                    if rule.translated_port:
                        current_port = rule.translated_port
                    identity_chain.append({
                        "stage": f"post-dnat-{device_id}",
                        "ip": current_dst,
                        "port": current_port,
                        "device_id": device_id,
                    })

    return {
        "nat_translations": translations,
        "identity_chain": identity_chain,
        "evidence": [{
            "type": "nat",
            "detail": f"NAT chain: {len(translations)} translations, {len(identity_chain)} stages",
        }],
    }


def _ip_in_range(ip: str, pattern: str) -> bool:
    """Check if IP matches pattern (exact or CIDR)."""
    if not pattern:
        return False
    if pattern == ip:
        return True
    import ipaddress
    try:
        if "/" in pattern:
            return ipaddress.ip_address(ip) in ipaddress.ip_network(pattern, strict=False)
        return ip == pattern
    except ValueError:
        return False

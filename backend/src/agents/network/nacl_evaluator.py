"""NACL evaluator node — stateless rule evaluation for NACLs in path."""
import ipaddress
from src.network.topology_store import TopologyStore
from src.network.models import NACLDirection, PolicyAction


def nacl_evaluator(state: dict, *, store: TopologyStore) -> dict:
    """Evaluate flow against NACLs in path.

    NACLs are stateless: rules are evaluated in order (lowest rule_number first).
    Both INBOUND and OUTBOUND must be checked. First match wins.
    No match = implicit deny.
    """
    nacls = state.get("nacls_in_path", [])
    src_ip = state.get("src_ip", "")
    dst_ip = state.get("dst_ip", "")
    port = state.get("port", 0)
    protocol = state.get("protocol", "tcp")

    if not nacls:
        return {"nacl_verdicts": [], "evidence": [{"type": "nacl", "detail": "No NACLs in path"}]}

    verdicts = []
    for nacl_info in nacls:
        nacl_id = nacl_info.get("device_id", "")
        rules = store.list_nacl_rules(nacl_id)

        inbound_result = _evaluate_rules(
            [r for r in rules if r.direction == NACLDirection.INBOUND],
            src_ip, dst_ip, port, protocol,
        )
        outbound_result = _evaluate_rules(
            [r for r in rules if r.direction == NACLDirection.OUTBOUND],
            dst_ip, src_ip, port, protocol,  # Outbound: reverse src/dst perspective
        )

        overall = "allow" if inbound_result["action"] == "allow" and outbound_result["action"] == "allow" else "deny"

        verdicts.append({
            "nacl_id": nacl_id,
            "nacl_name": nacl_info.get("device_name", ""),
            "action": overall,
            "inbound": inbound_result,
            "outbound": outbound_result,
        })

    any_deny = any(v["action"] == "deny" for v in verdicts)
    return {
        "nacl_verdicts": verdicts,
        "evidence": [{"type": "nacl",
                       "detail": f"NACL evaluation: {'BLOCKED' if any_deny else 'ALLOWED'} — {len(verdicts)} NACLs checked"}],
    }


def _evaluate_rules(rules: list, src_ip: str, dst_ip: str, port: int, protocol: str) -> dict:
    """Evaluate ordered NACL rules. First match wins."""
    for rule in sorted(rules, key=lambda r: r.rule_number):
        if rule.protocol != "-1" and rule.protocol != protocol:
            continue
        if not _ip_matches(src_ip, rule.cidr) and not _ip_matches(dst_ip, rule.cidr):
            continue
        if rule.protocol != "-1" and not (rule.port_range_from <= port <= rule.port_range_to):
            continue
        return {
            "action": rule.action.value,
            "rule_number": rule.rule_number,
            "matched_rule_id": rule.id,
        }
    # Implicit deny
    return {"action": "deny", "rule_number": -1, "matched_rule_id": "implicit_deny"}


def _ip_matches(ip: str, cidr: str) -> bool:
    if cidr == "0.0.0.0/0":
        return True
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False

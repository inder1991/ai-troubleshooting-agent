"""Input resolution node — resolves IPs to devices and subnets."""
from src.network.knowledge_graph import NetworkKnowledgeGraph


def input_resolver(state: dict, *, kg: NetworkKnowledgeGraph) -> dict:
    """Resolve source and destination IPs to devices and subnets.

    Returns resolution_status:
    - "resolved": both IPs mapped to known devices/subnets
    - "ambiguous": one or both IPs have multiple device candidates
    - "failed": IPs not in any known subnet
    """
    src_ip = state.get("src_ip", "")
    dst_ip = state.get("dst_ip", "")

    src_info = kg.resolve_ip(src_ip)
    dst_info = kg.resolve_ip(dst_ip)

    updates: dict = {
        "src_device": src_info.get("device"),
        "dst_device": dst_info.get("device"),
        "src_subnet": src_info.get("subnet"),
        "dst_subnet": dst_info.get("subnet"),
    }

    # Check for ambiguity
    ambiguous = []
    if src_info["subnet"] and not src_info["device_id"]:
        candidates = kg.find_candidate_devices(src_ip)
        if len(candidates) > 1:
            ambiguous.extend(candidates)

    if dst_info["subnet"] and not dst_info["device_id"]:
        candidates = kg.find_candidate_devices(dst_ip)
        if len(candidates) > 1:
            ambiguous.extend(candidates)

    if ambiguous:
        updates["resolution_status"] = "ambiguous"
        updates["ambiguous_candidates"] = ambiguous
    elif not src_info["subnet"] and not dst_info["subnet"]:
        updates["resolution_status"] = "failed"
    else:
        updates["resolution_status"] = "resolved"

    return updates

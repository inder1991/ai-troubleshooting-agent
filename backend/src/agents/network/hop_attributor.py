"""Hop attribution node — maps traced hops to known devices."""
from src.network.knowledge_graph import NetworkKnowledgeGraph


def hop_attributor(state: dict, *, kg: NetworkKnowledgeGraph) -> dict:
    """Attribute each traced hop IP to a known device in the knowledge graph.

    Uses probabilistic matching:
    - Direct match (interface/management IP) -> confidence 1.0
    - Candidate devices in same subnet -> confidence 0.5-0.8
    - No match -> confidence 0.0
    """
    trace_hops = state.get("trace_hops", [])
    if not trace_hops:
        return {"trace_hops": trace_hops}

    attributed_hops = []
    for hop in trace_hops:
        hop_ip = hop.get("ip", "")
        if not hop_ip:
            attributed_hops.append(hop)
            continue

        # Try direct device match
        device_id = kg.find_device_by_ip(hop_ip)
        if device_id:
            device = kg.store.get_device(device_id)
            hop["device_id"] = device_id
            hop["device_name"] = device.name if device else ""
            hop["attribution_confidence"] = 1.0
            attributed_hops.append(hop)
            continue

        # Try candidate devices in same subnet
        candidates = kg.find_candidate_devices(hop_ip)
        if candidates:
            # Pick highest confidence candidate or just note them
            hop["candidate_devices"] = candidates
            hop["attribution_confidence"] = 0.5 if len(candidates) > 1 else 0.7
            attributed_hops.append(hop)
            continue

        # No match
        hop["attribution_confidence"] = 0.0
        attributed_hops.append(hop)

    # Build evidence
    attributed_count = sum(1 for h in attributed_hops if h.get("device_id"))
    total_hops = len([h for h in attributed_hops if h.get("ip")])

    return {
        "trace_hops": attributed_hops,
        "evidence": [{
            "type": "hop_attribution",
            "detail": f"Attributed {attributed_count}/{total_hops} hops to known devices",
        }],
    }

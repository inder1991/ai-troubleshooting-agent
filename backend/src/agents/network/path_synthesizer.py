"""Path synthesizer node — merges all evidence into a final path with confidence."""

# Weighted segment scoring
_SEGMENT_WEIGHTS = {
    "traced": 3.0,
    "api": 2.0,
    "graph": 1.0,
    "inferred": 0.5,
}


def path_synthesizer(state: dict) -> dict:
    """Synthesize final path from candidate paths, traced path, and firewall verdicts.

    Features:
    - Weighted confidence: traced > api > graph > inferred
    - Contradiction detection between trace and graph paths
    - Overall diagnosis confidence calculation
    """
    candidate_paths = state.get("candidate_paths", [])
    traced_path = state.get("traced_path")
    firewall_verdicts = state.get("firewall_verdicts", [])
    trace_hops = state.get("trace_hops", [])
    nat_translations = state.get("nat_translations", [])
    routing_loop = state.get("routing_loop_detected", False)

    # Determine final path source and confidence
    path_source = "graph"
    path_confidence = 0.0
    final_hops = []
    contradictions = []

    if traced_path and traced_path.get("hops"):
        # Traced path is highest confidence
        final_hops = traced_path["hops"]
        path_source = "traced"
        path_confidence = _SEGMENT_WEIGHTS["traced"]
    elif candidate_paths:
        # Use best graph path
        best = candidate_paths[0]
        final_hops = best.get("hops", [])
        path_source = "graph"
        path_confidence = _SEGMENT_WEIGHTS["graph"]

    # Check for contradictions between trace and graph
    if traced_path and candidate_paths:
        traced_hops_set = set(traced_path.get("hops", []))
        for cp in candidate_paths:
            graph_hops_set = set(cp.get("hops", []))
            if traced_hops_set and graph_hops_set and not traced_hops_set & graph_hops_set:
                contradictions.append({
                    "type": "path_mismatch",
                    "detail": "Traced path and graph path share no common nodes",
                    "traced_hops": list(traced_hops_set),
                    "graph_hops": list(graph_hops_set),
                })

    # Factor in firewall verdicts
    nacl_verdicts = state.get("nacl_verdicts", [])
    nacl_deny = any(v.get("action") == "deny" for v in nacl_verdicts)

    fw_confidence = 0.0
    any_deny = False
    for v in firewall_verdicts:
        fw_confidence += v.get("confidence", 0)
        if v.get("action") in ("deny", "drop"):
            any_deny = True
    any_deny = any_deny or nacl_deny
    if firewall_verdicts:
        fw_confidence /= len(firewall_verdicts)

    # Overall confidence: weighted combination
    if path_confidence > 0:
        overall = min(1.0, (path_confidence / 3.0) * 0.6 + fw_confidence * 0.3 + (0.1 if not contradictions else 0.0))
    else:
        overall = 0.0

    # Reduce confidence for issues
    if routing_loop:
        overall *= 0.3
        contradictions.append({"type": "routing_loop", "detail": "Routing loop detected in traceroute"})

    if any_deny:
        overall = min(overall, 0.5)  # Can't be highly confident if blocked

    # Determine diagnosis status
    if not final_hops and not candidate_paths:
        diagnosis_status = "no_path_known"
    elif routing_loop:
        diagnosis_status = "error"
    elif any_deny:
        diagnosis_status = "complete"
    else:
        diagnosis_status = "complete"

    final_path = {
        "hops": final_hops,
        "source": path_source,
        "hop_count": len(final_hops),
        "has_nat": len(nat_translations) > 0,
        "blocked": any_deny,
        "vpn_segments": state.get("vpn_segments", []),
        "vpc_crossings": state.get("vpc_boundary_crossings", []),
        "load_balancers": state.get("load_balancers_in_path", []),
    }

    return {
        "final_path": final_path,
        "confidence": round(overall, 3),
        "diagnosis_status": diagnosis_status,
        "contradictions": contradictions,
        "evidence": [{
            "type": "synthesis",
            "detail": f"Path source: {path_source}, confidence: {overall:.2f}, contradictions: {len(contradictions)}",
        }],
    }

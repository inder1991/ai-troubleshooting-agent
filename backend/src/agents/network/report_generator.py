"""Report generator node — produces structured JSON diagnosis report."""


def report_generator(state: dict) -> dict:
    """Generate a structured diagnosis report from synthesized state.

    Produces structured JSON only — no freeform LLM text.
    """
    final_path = state.get("final_path", {})
    firewall_verdicts = state.get("firewall_verdicts", [])
    nat_translations = state.get("nat_translations", [])
    identity_chain = state.get("identity_chain", [])
    trace_hops = state.get("trace_hops", [])
    contradictions = state.get("contradictions", [])
    confidence = state.get("confidence", 0.0)
    diagnosis_status = state.get("diagnosis_status", "running")
    evidence = state.get("evidence", [])
    nacl_verdicts = state.get("nacl_verdicts", [])
    vpn_segments = state.get("vpn_segments", [])
    vpc_crossings = state.get("vpc_boundary_crossings", [])
    lbs_in_path = state.get("load_balancers_in_path", [])

    # Build next steps
    next_steps = []
    if diagnosis_status == "no_path_known":
        next_steps.append("Add network topology data (devices, subnets, routes) to enable path analysis")
        next_steps.append("Check if source and destination IPs are correct")
    elif final_path.get("blocked"):
        deny_fws = [v["device_name"] for v in firewall_verdicts if v.get("action") in ("deny", "drop")]
        for fw in deny_fws:
            next_steps.append(f"Review firewall rules on {fw}")
        next_steps.append("Check if a firewall rule change request is needed")
    elif contradictions:
        next_steps.append("Investigate path contradictions between traceroute and topology data")
        next_steps.append("Verify topology data accuracy and update if needed")
    elif confidence < 0.5:
        next_steps.append("Run additional diagnostics to improve confidence")
        next_steps.append("Add more topology data for better path resolution")
    nacl_deny = [v["nacl_name"] for v in nacl_verdicts if v.get("action") == "deny"]
    for nacl_name in nacl_deny:
        next_steps.append(f"Review NACL rules on {nacl_name}")

    # Build executive summary
    if diagnosis_status == "no_path_known":
        summary = "Unable to determine network path. Topology data may be incomplete."
    elif final_path.get("blocked"):
        blockers = ", ".join(v["device_name"] for v in firewall_verdicts if v.get("action") in ("deny", "drop"))
        summary = f"Traffic is BLOCKED by firewall(s): {blockers}"
    elif state.get("routing_loop_detected"):
        summary = "Routing loop detected. Traffic is not reaching destination."
    elif confidence >= 0.7:
        summary = f"Path identified with high confidence ({confidence:.0%}). Traffic is ALLOWED."
    elif confidence >= 0.4:
        summary = f"Path identified with moderate confidence ({confidence:.0%}). Traffic appears ALLOWED."
    else:
        summary = f"Path analysis inconclusive (confidence: {confidence:.0%}). More data needed."

    if vpn_segments:
        vpn_names = ", ".join(s.get("name", "unknown") for s in vpn_segments)
        summary += f" Path traverses VPN tunnel(s): {vpn_names}."
    if vpc_crossings:
        summary += f" Path crosses {len(vpc_crossings)} VPC boundary(ies)."
    if lbs_in_path:
        lb_names = ", ".join(lb.get("device_name", "unknown") for lb in lbs_in_path)
        summary += f" Load balancer(s) in path: {lb_names}."

    return {
        "executive_summary": summary,
        "next_steps": next_steps,
        "evidence": [{
            "type": "report",
            "detail": f"Report generated: {diagnosis_status}, {len(next_steps)} next steps",
        }],
    }

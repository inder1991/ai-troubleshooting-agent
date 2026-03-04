"""Report generator node — produces structured JSON diagnosis report."""
import ipaddress


def _compute_security_grade(verdict: dict) -> str | None:
    """Compute a security risk grade for an ALLOW verdict.

    Returns None for deny/drop verdicts (no security concern on blocking).
    """
    action = verdict.get("action", "").lower()
    if action != "allow":
        return None

    src = verdict.get("matched_source", "")
    dst = verdict.get("matched_destination", "")
    ports = verdict.get("matched_ports", "")

    src_is_any = src in ("0.0.0.0/0", "any", "*", "")
    dst_is_any = dst in ("0.0.0.0/0", "any", "*", "")
    port_is_any = ports in ("any", "*", "", "0-65535")

    # Broad source CIDR detection
    src_is_broad = src_is_any
    if not src_is_any and src:
        try:
            for cidr in src.split(","):
                net = ipaddress.ip_network(cidr.strip(), strict=False)
                if net.prefixlen <= 16:
                    src_is_broad = True
                    break
        except ValueError:
            pass

    if src_is_any and port_is_any:
        return "CRITICAL"
    if src_is_any and not port_is_any:
        return "HIGH"
    if src_is_broad and port_is_any:
        return "MEDIUM"
    return "LOW"


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
        deny_fws = [v.get("device_name", "unknown") for v in firewall_verdicts if v.get("action") in ("deny", "drop")]
        for fw in deny_fws:
            next_steps.append(f"Review firewall rules on {fw}")
        next_steps.append("Check if a firewall rule change request is needed")
    elif contradictions:
        next_steps.append("Investigate path contradictions between traceroute and topology data")
        next_steps.append("Verify topology data accuracy and update if needed")
    elif confidence < 0.5:
        next_steps.append("Run additional diagnostics to improve confidence")
        next_steps.append("Add more topology data for better path resolution")
    nacl_deny = [v.get("nacl_name", "unknown") for v in nacl_verdicts if v.get("action") == "deny"]
    for nacl_name in nacl_deny:
        next_steps.append(f"Review NACL rules on {nacl_name}")

    # Build executive summary
    if diagnosis_status == "no_path_known":
        summary = "Unable to determine network path. Topology data may be incomplete."
    elif final_path.get("blocked"):
        blockers = ", ".join(v.get("device_name", "unknown") for v in firewall_verdicts if v.get("action") in ("deny", "drop"))
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

    # Security grading
    security_warnings = []
    for v in firewall_verdicts:
        grade = _compute_security_grade(v)
        if grade and grade in ("CRITICAL", "HIGH"):
            security_warnings.append(
                f"SEC-WARN ({grade}): {v.get('device_name', 'unknown')} allows traffic via "
                f"overly permissive rule '{v.get('rule_name', 'unknown')}'"
            )
    if security_warnings:
        summary += " " + " | ".join(security_warnings)
        next_steps.extend([
            "Review overly permissive firewall rules flagged with SEC-WARN",
            "Consider tightening source/destination CIDR scope",
        ])

    # Drift event warnings
    drift_events = state.get("active_drift_events", [])
    if drift_events:
        critical_drifts = [d for d in drift_events if d.get("severity") == "critical"]
        if critical_drifts:
            drift_summary = ", ".join(
                f"{d['entity_type']} '{d['entity_id']}' {d['drift_type']} ({d['field']})"
                for d in critical_drifts[:3]
            )
            summary += f" DRIFT WARNING: {drift_summary}."
            next_steps.append("Review active drift events on devices in the path")

    return {
        "executive_summary": summary,
        "next_steps": next_steps,
        "evidence": [{
            "type": "report",
            "detail": f"Report generated: {diagnosis_status}, {len(next_steps)} next steps",
        }],
    }

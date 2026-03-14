"""Solution validator: validate remediation safety before showing to operator."""

from __future__ import annotations

from src.agents.cluster.command_validator import (
    validate_kubectl_command,
    check_forbidden,
    simulate_command,
    check_replica_safety,
    check_drain_capacity,
    check_fixes_root_cause,
    compute_remediation_confidence,
    add_dry_run,
)
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)


def validate_solution_step(
    step: dict,
    topology: dict,
    domain_reports: list,
    hypothesis_selection: dict,
) -> dict:
    """Validate a single remediation step for safety."""
    command = step.get("command", "")
    if not command:
        return step

    # Check forbidden
    blocked, block_reason = check_forbidden(command)
    if blocked:
        step["validation"] = {
            "risk_level": "forbidden",
            "warnings": [block_reason],
            "requires_confirmation": False,
            "blocked": True,
            "block_reason": block_reason,
            "simulation": None,
            "remediation_confidence": 0.0,
            "confidence_label": "Blocked",
        }
        return step

    # Simulate impact
    simulation = simulate_command(command, topology, domain_reports)

    # Safety checks
    checks = [
        check_replica_safety(command, domain_reports),
        check_drain_capacity(command, topology),
    ]

    cmd_validation = validate_kubectl_command(command)
    if cmd_validation.is_destructive:
        checks.append("dangerous")

    root_check = check_fixes_root_cause(step, hypothesis_selection)
    checks.append(root_check)

    risk = "safe"
    warnings: list[str] = []
    for check_result in checks:
        if check_result == "dangerous":
            risk = "dangerous"
            warnings.append("Destructive operation — requires confirmation")
        elif check_result == "caution" and risk != "dangerous":
            risk = "caution"

    # Get top hypothesis for confidence calc
    top_hypothesis: dict = {}
    root_causes = hypothesis_selection.get("root_causes", [])
    if root_causes:
        top_hypothesis = root_causes[0] if isinstance(root_causes[0], dict) else {}

    confidence = compute_remediation_confidence(step, top_hypothesis, simulation, risk)

    confidence_label = (
        "High confidence fix" if confidence >= 0.8
        else "Likely fix" if confidence >= 0.5
        else "Speculative" if confidence >= 0.3
        else "Low confidence"
    )

    step["validation"] = {
        "risk_level": risk,
        "warnings": warnings,
        "requires_confirmation": risk == "dangerous",
        "blocked": False,
        "block_reason": "",
        "simulation": simulation,
        "remediation_confidence": round(confidence, 2),
        "confidence_label": confidence_label,
    }

    return step


@traced_node(timeout_seconds=8)
async def solution_validator(state: dict, config: dict) -> dict:
    """Validate remediation steps for safety and effectiveness. Deterministic."""
    health_report = state.get("health_report", {})
    if not health_report:
        return {}

    remediation = health_report.get("remediation", {})
    topology = state.get("scoped_topology_graph") or state.get("topology_graph", {})
    domain_reports = state.get("domain_reports", [])
    hypothesis_selection = state.get("hypothesis_selection", {})

    # Validate immediate steps
    validated_immediate = []
    speculative = []
    for step in remediation.get("immediate", []):
        validated = validate_solution_step(step, topology, domain_reports, hypothesis_selection)
        conf = validated.get("validation", {}).get("remediation_confidence", 0)
        if conf >= 0.3 or not validated.get("validation"):
            validated_immediate.append(validated)
        else:
            speculative.append(validated)

    remediation["immediate"] = validated_immediate
    if speculative:
        remediation["speculative"] = speculative
    health_report["remediation"] = remediation

    return {"health_report": health_report}

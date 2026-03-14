"""Critic agent: validates domain agent findings before synthesis."""

from __future__ import annotations

from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _validate_finding_has_evidence(anomaly: dict) -> bool:
    """Check that finding has non-empty evidence reference."""
    return bool(anomaly.get("evidence_ref", "").strip())


def _validate_severity_proportional(anomaly: dict) -> bool:
    """Basic check that severity matches description intensity."""
    desc = anomaly.get("description", "").lower()
    severity = anomaly.get("severity", "medium")
    # High severity should mention critical impact words
    critical_words = ["crash", "down", "failure", "unavailable", "oom", "unresponsive", "data loss"]
    if severity == "high" and not any(w in desc for w in critical_words):
        return False  # Possibly over-rated
    return True


def _check_contradictions(reports: list[dict]) -> list[str]:
    """Find contradictions between domain findings."""
    contradictions = []
    # Check if one domain says healthy and another says the same resource is unhealthy
    all_anomalies = []
    all_ruled_out = set()
    for r in reports:
        for a in r.get("anomalies", []):
            all_anomalies.append(a)
        for ro in r.get("ruled_out", []):
            all_ruled_out.add(ro.lower().strip())

    for a in all_anomalies:
        desc = a.get("description", "").lower()
        for ro in all_ruled_out:
            # If a ruled_out item closely matches an anomaly description
            if len(ro) > 10 and ro in desc:
                contradictions.append(
                    f"Contradiction: '{a.get('anomaly_id')}' reports issue but another domain ruled out '{ro}'"
                )
    return contradictions


@traced_node(timeout_seconds=15)
async def critic_validator(state: dict, config: dict) -> dict:
    """Validate domain agent findings before synthesis."""
    reports_data = state.get("domain_reports", [])

    validated_anomaly_ids = []
    dropped_anomaly_ids = []
    downgraded_anomaly_ids = []
    warnings = []

    for report_data in reports_data:
        if report_data.get("status") in ("SKIPPED", "FAILED"):
            continue

        for anomaly in report_data.get("anomalies", []):
            anomaly_id = anomaly.get("anomaly_id", "")

            # Check 1: Has evidence
            if not _validate_finding_has_evidence(anomaly):
                dropped_anomaly_ids.append(anomaly_id)
                warnings.append(f"Dropped {anomaly_id}: no evidence reference")
                continue

            # Check 2: Severity proportional
            if not _validate_severity_proportional(anomaly):
                downgraded_anomaly_ids.append(anomaly_id)
                warnings.append(f"Downgraded {anomaly_id}: severity not proportional to description")

            validated_anomaly_ids.append(anomaly_id)

    # Check for contradictions
    contradictions = _check_contradictions(reports_data)
    if contradictions:
        warnings.extend(contradictions)

    if warnings:
        logger.info("Critic found %d issues", len(warnings), extra={"action": "critic_validation"})

    return {
        "critic_result": {
            "validated_anomaly_ids": validated_anomaly_ids,
            "dropped_anomaly_ids": dropped_anomaly_ids,
            "downgraded_anomaly_ids": downgraded_anomaly_ids,
            "warnings": warnings,
        },
    }

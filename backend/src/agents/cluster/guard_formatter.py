"""Guard Mode Formatter — structures diagnostic output into 3-layer health scan."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.agents.cluster.state import (
    GuardScanResult, CurrentRisk, PredictiveRisk, ScanDelta, DomainReport, DomainStatus,
)
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _extract_current_risks(state: dict) -> list[CurrentRisk]:
    """Layer 1: What is broken right now."""
    risks: list[CurrentRisk] = []
    reports = [DomainReport(**r) for r in state.get("domain_reports", [])]

    for report in reports:
        for anomaly in report.anomalies:
            risks.append(CurrentRisk(
                category=report.domain,
                severity=anomaly.severity,
                resource=anomaly.evidence_ref,
                description=anomaly.description,
                affected_count=1,
            ))

    # Add risks from issue clusters
    for cluster in state.get("issue_clusters", []):
        cluster_id = cluster.get("cluster_id", "")
        for alert in cluster.get("alerts", []):
            # Avoid duplicating anomalies already captured from domain reports
            desc = f"{alert.get('alert_type', '')} on {alert.get('resource_key', '')}"
            if not any(r.description == desc for r in risks):
                risks.append(CurrentRisk(
                    category=alert.get("resource_key", "").split("/")[0],
                    severity=alert.get("severity", "warning"),
                    resource=alert.get("resource_key", ""),
                    description=desc,
                    affected_count=1,
                    issue_cluster_id=cluster_id,
                ))

    return risks


def _extract_predictive_risks(state: dict) -> list[PredictiveRisk]:
    """Layer 2: What will break soon. Based on domain report analysis."""
    risks: list[PredictiveRisk] = []
    health_report = state.get("health_report", {})
    if not health_report:
        return risks

    # Extract from remediation long_term items (these hint at future risks)
    remediation = health_report.get("remediation", {})
    for item in remediation.get("long_term", []):
        risks.append(PredictiveRisk(
            category="capacity",
            severity="warning",
            description=item.get("description", ""),
            predicted_impact=item.get("description", ""),
            time_horizon=item.get("effort_estimate", "unknown"),
        ))

    return risks


def _compute_delta(current: GuardScanResult, previous: dict | None) -> ScanDelta:
    """Layer 3: What changed since last scan."""
    if not previous:
        return ScanDelta()

    prev_descriptions = {r.get("description", "") for r in previous.get("current_risks", [])}
    curr_descriptions = {r.description for r in current.current_risks}

    return ScanDelta(
        new_risks=sorted(curr_descriptions - prev_descriptions),
        resolved_risks=sorted(prev_descriptions - curr_descriptions),
        worsened=[],  # TODO: compare severity levels
        improved=[],
        previous_scan_id=previous.get("scan_id"),
        previous_scanned_at=previous.get("scanned_at"),
    )


def _compute_overall_health(risks: list[CurrentRisk]) -> str:
    """Determine overall health from current risks."""
    if any(r.severity == "critical" for r in risks):
        return "CRITICAL"
    if any(r.severity == "warning" for r in risks):
        return "DEGRADED"
    return "HEALTHY"


def _compute_risk_score(current: list[CurrentRisk], predictive: list[PredictiveRisk]) -> float:
    """Simple risk score: 0.0 (healthy) to 1.0 (critical)."""
    score = 0.0
    for r in current:
        score += {"critical": 0.3, "warning": 0.15, "info": 0.05}.get(r.severity, 0.05)
    for r in predictive:
        score += {"critical": 0.2, "warning": 0.1, "info": 0.03}.get(r.severity, 0.03)
    return min(1.0, round(score, 2))


@traced_node(timeout_seconds=15)
async def guard_formatter(state: dict, config: dict) -> dict:
    """LangGraph node: format output for Guard Mode (skip in diagnostic mode)."""
    scan_mode = state.get("scan_mode", "diagnostic")

    if scan_mode != "guard":
        return {}  # No-op for diagnostic mode

    now = datetime.now(timezone.utc).isoformat()
    current_risks = _extract_current_risks(state)
    predictive_risks = _extract_predictive_risks(state)

    scan = GuardScanResult(
        scan_id=f"gs-{uuid.uuid4().hex[:8]}",
        scanned_at=now,
        platform=state.get("platform", ""),
        platform_version=state.get("platform_version", ""),
        current_risks=current_risks,
        predictive_risks=predictive_risks,
        overall_health=_compute_overall_health(current_risks),
        risk_score=_compute_risk_score(current_risks, predictive_risks),
    )

    # Compute delta against previous scan
    previous = state.get("previous_scan")
    scan.delta = _compute_delta(scan, previous)

    logger.info("Guard scan formatted", extra={
        "action": "guard_format",
        "current_risks": len(current_risks),
        "predictive_risks": len(predictive_risks),
        "overall_health": scan.overall_health,
    })

    return {"guard_scan_result": scan.model_dump(mode="json")}

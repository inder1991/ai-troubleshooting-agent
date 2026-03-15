"""Recommendation engine: score, prioritize, categorize all findings."""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from src.agents.cluster.state import (
    ProactiveFinding, CostRecommendation, WorkloadRecommendation,
    ScoredRecommendation, ClusterRecommendationSnapshot, ClusterCostSummary,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

SEVERITY_WEIGHT = {"critical": 100, "high": 75, "medium": 50, "low": 25}

def _days_factor(days: int) -> float:
    if days < 0: return 1.0  # Already impacting
    if days <= 7: return 1.0
    if days <= 14: return 0.7
    if days <= 30: return 0.4
    return 0.1

def _savings_factor(savings: float) -> float:
    return min(1.0, savings / 500)

def score_recommendation(finding: dict) -> float:
    """Score a recommendation for sorting. Higher = more urgent."""
    severity = finding.get("severity", "medium")
    days = finding.get("days_until_impact", -1)
    savings = finding.get("estimated_savings_usd", 0)
    confidence = finding.get("confidence", 0.5)
    blast = len(finding.get("affected_workloads", []))

    return (
        SEVERITY_WEIGHT.get(severity, 50) * 0.25
        + _days_factor(days) * 15
        + _savings_factor(savings) * 10
        + confidence * 10
        + min(blast, 10) * 0.5
    )

def categorize(finding: dict) -> str:
    """Assign category based on source and severity."""
    source = finding.get("source", "")
    severity = finding.get("severity", "medium")
    check_type = finding.get("check_type", "")

    if source == "proactive" and severity in ("critical", "high"):
        return "critical_risk"
    if source in ("cost", "workload"):
        return "optimization"
    if check_type in ("security_posture", "image_stale"):
        return "security"
    if source == "proactive":
        return "security" if check_type in ("security_posture", "image_stale") else "critical_risk" if severity == "high" else "known_issue"
    return "known_issue"

def build_scored_recommendations(
    proactive_findings: list[ProactiveFinding],
    cost_recommendation: CostRecommendation | None,
    workload_recommendations: list[WorkloadRecommendation],
) -> list[ScoredRecommendation]:
    """Combine all sources into scored, categorized recommendations."""
    scored: list[ScoredRecommendation] = []

    # Proactive findings
    for f in proactive_findings:
        d = f.model_dump()
        scored.append(ScoredRecommendation(
            recommendation_id=f.finding_id or str(uuid.uuid4())[:8],
            category=categorize(d),
            score=score_recommendation(d),
            title=f.title,
            description=f.description,
            severity=f.severity,
            source=f.source,
            affected_resources=f.affected_resources,
            affected_workloads=f.affected_workloads,
            commands=f.commands,
            dry_run_command=f.dry_run_command,
            rollback_command=f.rollback_command,
            days_until_impact=f.days_until_impact,
            estimated_savings_usd=f.estimated_savings_usd,
            risk_level="safe",
            confidence=f.confidence,
        ))

    # Cost recommendation
    if cost_recommendation and cost_recommendation.projected_savings_usd > 0:
        scored.append(ScoredRecommendation(
            recommendation_id=cost_recommendation.recommendation_id or str(uuid.uuid4())[:8],
            category="optimization",
            score=score_recommendation({
                "severity": "medium",
                "days_until_impact": 30,
                "estimated_savings_usd": cost_recommendation.projected_savings_usd,
                "confidence": 0.7,
                "affected_workloads": cost_recommendation.affected_workloads,
            }),
            title=f"Optimize instance mix — save ${cost_recommendation.projected_savings_usd:.0f}/mo ({cost_recommendation.projected_savings_pct:.0f}%)",
            description=f"Current: ${cost_recommendation.current_monthly_cost:.0f}/mo. Projected: ${cost_recommendation.projected_monthly_cost:.0f}/mo. {cost_recommendation.idle_capacity_pct:.0f}% idle capacity.",
            severity="medium",
            source="cost",
            affected_workloads=cost_recommendation.affected_workloads,
            estimated_savings_usd=cost_recommendation.projected_savings_usd,
            risk_level=cost_recommendation.risk_level,
            confidence=0.7,
        ))

    # Workload recommendations
    for w in workload_recommendations:
        savings = 0.0  # Would need cost data to estimate
        scored.append(ScoredRecommendation(
            recommendation_id=w.recommendation_id or str(uuid.uuid4())[:8],
            category="optimization",
            score=score_recommendation({
                "severity": "low" if w.risk_level == "safe" else "medium",
                "days_until_impact": 90,
                "estimated_savings_usd": savings,
                "confidence": 0.8,
                "affected_workloads": [w.workload],
            }),
            title=f"Right-size {w.workload.split('/')[-1]}: {w.current_memory_request} → {w.recommended_memory_request}",
            description=f"CPU: {w.current_cpu_request} → {w.recommended_cpu_request} ({w.cpu_reduction_pct:.0f}% reduction). Memory: {w.current_memory_request} → {w.recommended_memory_request} ({w.memory_reduction_pct:.0f}% reduction). p95 usage: CPU {w.p95_cpu_usage}, Memory {w.p95_memory_usage}.",
            severity="low" if w.risk_level == "safe" else "medium",
            source="workload",
            affected_workloads=[w.workload],
            risk_level=w.risk_level,
            confidence=0.8,
        ))

    # Sort by score descending
    scored.sort(key=lambda r: r.score, reverse=True)

    logger.info("Built %d scored recommendations (%d proactive, %d cost, %d workload)",
                len(scored), len(proactive_findings),
                1 if cost_recommendation else 0, len(workload_recommendations))

    return scored

def build_recommendation_snapshot(
    cluster_id: str,
    cluster_name: str,
    provider: str,
    proactive_findings: list[ProactiveFinding],
    cost_summary: ClusterCostSummary | None,
    cost_recommendation: CostRecommendation | None,
    workload_recommendations: list[WorkloadRecommendation],
) -> ClusterRecommendationSnapshot:
    """Build a full snapshot for persistence and the cluster registry."""
    scored = build_scored_recommendations(proactive_findings, cost_recommendation, workload_recommendations)

    total_savings = (cost_recommendation.projected_savings_usd if cost_recommendation else 0)
    critical_count = sum(1 for r in scored if r.category == "critical_risk")
    optimization_count = sum(1 for r in scored if r.category == "optimization")
    security_count = sum(1 for r in scored if r.category == "security")

    return ClusterRecommendationSnapshot(
        cluster_id=cluster_id,
        cluster_name=cluster_name,
        provider=provider,
        scanned_at=datetime.now(timezone.utc).isoformat(),
        proactive_findings=proactive_findings,
        cost_summary=cost_summary,
        workload_recommendations=workload_recommendations,
        scored_recommendations=scored,
        total_savings_usd=round(total_savings, 2),
        critical_count=critical_count,
        optimization_count=optimization_count,
        security_count=security_count,
    )

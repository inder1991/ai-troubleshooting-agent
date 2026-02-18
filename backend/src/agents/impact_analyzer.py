from src.models.schemas import BlastRadius, SeverityRecommendation, ServiceTier
from src.utils.logger import get_logger

logger = get_logger(__name__)

SEVERITY_MATRIX = {
    ("critical", "cluster_wide"): "P1",
    ("critical", "namespace"): "P1",
    ("critical", "service_group"): "P2",
    ("critical", "single_service"): "P2",
    ("standard", "cluster_wide"): "P2",
    ("standard", "namespace"): "P3",
    ("standard", "service_group"): "P3",
    ("standard", "single_service"): "P4",
    ("internal", "cluster_wide"): "P3",
    ("internal", "namespace"): "P4",
    ("internal", "service_group"): "P4",
    ("internal", "single_service"): "P4",
}


class ImpactAnalyzer:
    def __init__(self, service_tiers: dict[str, ServiceTier] | None = None):
        self._tiers = service_tiers or {}

    def get_service_tier(self, service_name: str) -> str:
        if service_name in self._tiers:
            return self._tiers[service_name].tier
        return "standard"  # default

    def recommend_severity(
        self, service_name: str, blast_radius: BlastRadius
    ) -> SeverityRecommendation:
        tier = self.get_service_tier(service_name)
        key = (tier, blast_radius.scope)
        severity = SEVERITY_MATRIX.get(key, "P3")
        logger.info("Severity recommended", extra={"agent_name": "impact_analyzer", "action": "severity", "extra": {"severity": severity, "reasoning": f"tier={tier}, scope={blast_radius.scope}"}})
        return SeverityRecommendation(
            recommended_severity=severity,
            reasoning=f"Service tier '{tier}' with blast radius scope '{blast_radius.scope}'",
            factors={"service_tier": tier, "blast_radius_scope": blast_radius.scope},
        )

    def estimate_blast_radius(
        self,
        primary_service: str,
        upstream: list[str] | None = None,
        downstream: list[str] | None = None,
        shared: list[str] | None = None,
    ) -> BlastRadius:
        upstream = upstream or []
        downstream = downstream or []
        shared = shared or []
        total_affected = len(upstream) + len(downstream)
        if total_affected > 10:
            scope = "cluster_wide"
        elif total_affected > 5:
            scope = "namespace"
        elif total_affected > 1:
            scope = "service_group"
        else:
            scope = "single_service"
        logger.info("Blast radius computed", extra={"agent_name": "impact_analyzer", "action": "blast_radius", "extra": {"primary_service": primary_service, "upstream": len(upstream), "downstream": len(downstream), "scope": scope}})
        return BlastRadius(
            primary_service=primary_service,
            upstream_affected=upstream,
            downstream_affected=downstream,
            shared_resources=shared,
            estimated_user_impact=f"~{total_affected * 1000} users potentially affected"
            if total_affected
            else "Minimal",
            scope=scope,
        )

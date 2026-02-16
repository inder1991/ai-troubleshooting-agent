import pytest
from src.models.schemas import BlastRadius, SeverityRecommendation, ServiceTier
from src.agents.impact_analyzer import ImpactAnalyzer, SEVERITY_MATRIX


class TestSeverityMatrix:
    def test_critical_cluster_wide_is_p1(self):
        assert SEVERITY_MATRIX[("critical", "cluster_wide")] == "P1"

    def test_internal_single_service_is_p4(self):
        assert SEVERITY_MATRIX[("internal", "single_service")] == "P4"

    def test_all_combinations_present(self):
        tiers = ["critical", "standard", "internal"]
        scopes = ["cluster_wide", "namespace", "service_group", "single_service"]
        for t in tiers:
            for s in scopes:
                assert (t, s) in SEVERITY_MATRIX


class TestImpactAnalyzer:
    def test_default_tier(self):
        analyzer = ImpactAnalyzer()
        assert analyzer.get_service_tier("unknown") == "standard"

    def test_configured_tier(self):
        tiers = {"order-svc": ServiceTier(service_name="order-svc", tier="critical")}
        analyzer = ImpactAnalyzer(service_tiers=tiers)
        assert analyzer.get_service_tier("order-svc") == "critical"

    def test_recommend_severity_p1(self):
        tiers = {"api-gw": ServiceTier(service_name="api-gw", tier="critical")}
        analyzer = ImpactAnalyzer(service_tiers=tiers)
        br = BlastRadius(primary_service="api-gw", scope="cluster_wide")
        rec = analyzer.recommend_severity("api-gw", br)
        assert rec.recommended_severity == "P1"

    def test_recommend_severity_p4(self):
        analyzer = ImpactAnalyzer()
        br = BlastRadius(primary_service="internal-tool", scope="single_service")
        rec = analyzer.recommend_severity("internal-tool", br)
        assert rec.recommended_severity == "P4"

    def test_estimate_blast_radius_single(self):
        analyzer = ImpactAnalyzer()
        br = analyzer.estimate_blast_radius("order-svc")
        assert br.scope == "single_service"

    def test_estimate_blast_radius_namespace(self):
        analyzer = ImpactAnalyzer()
        br = analyzer.estimate_blast_radius(
            "order-svc",
            upstream=["a", "b", "c"],
            downstream=["d", "e", "f"],
        )
        assert br.scope == "namespace"

    def test_estimate_blast_radius_cluster_wide(self):
        analyzer = ImpactAnalyzer()
        br = analyzer.estimate_blast_radius(
            "order-svc",
            upstream=["a", "b", "c", "d", "e", "f"],
            downstream=["g", "h", "i", "j", "k"],
        )
        assert br.scope == "cluster_wide"

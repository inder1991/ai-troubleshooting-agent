"""Tests for the intelligent cluster diagnostic state models.

Covers topology, correlation, causal firewall, and guard-mode models
added in state.py alongside the existing ClusterDiagnosticState.
"""

import pytest

from src.agents.cluster.state import (
    BlockedLink,
    CausalAnnotation,
    CausalChain,
    CausalSearchSpace,
    ClusterAlert,
    ClusterHealthReport,
    CurrentRisk,
    DomainAnomaly,
    DomainReport,
    GuardScanResult,
    IssueCluster,
    PredictiveRisk,
    RootCandidate,
    ScanDelta,
    TopologyEdge,
    TopologyNode,
    TopologySnapshot,
)


class TestTopologyModels:
    """Tests for TopologyNode, TopologyEdge, and TopologySnapshot."""

    def test_topology_snapshot_defaults(self):
        """Empty snapshot has sane defaults."""
        snap = TopologySnapshot()
        assert snap.nodes == {}
        assert snap.edges == []
        assert snap.built_at == ""
        assert snap.stale is False
        assert snap.resource_version == ""

    def test_topology_snapshot_with_data(self):
        """Snapshot populated with nodes and edges round-trips correctly."""
        node_a = TopologyNode(kind="Pod", name="web-abc", namespace="default", status="Running")
        node_b = TopologyNode(kind="Service", name="web-svc", namespace="default")
        edge = TopologyEdge(from_key="Service/default/web-svc", to_key="Pod/default/web-abc", relation="selects")

        snap = TopologySnapshot(
            nodes={
                "Pod/default/web-abc": node_a,
                "Service/default/web-svc": node_b,
            },
            edges=[edge],
            built_at="2026-03-01T00:00:00Z",
            resource_version="12345",
        )

        assert len(snap.nodes) == 2
        assert snap.nodes["Pod/default/web-abc"].kind == "Pod"
        assert snap.nodes["Pod/default/web-abc"].status == "Running"
        assert snap.nodes["Service/default/web-svc"].node_name is None
        assert len(snap.edges) == 1
        assert snap.edges[0].relation == "selects"
        assert snap.built_at == "2026-03-01T00:00:00Z"
        assert snap.stale is False

    def test_topology_node_labels(self):
        """TopologyNode labels default to empty dict and can be populated."""
        bare = TopologyNode(kind="Node", name="node-1")
        assert bare.labels == {}

        labelled = TopologyNode(kind="Node", name="node-1", labels={"zone": "us-east-1a"})
        assert labelled.labels["zone"] == "us-east-1a"


class TestCorrelationModels:
    """Tests for ClusterAlert, RootCandidate, and IssueCluster."""

    def test_issue_cluster_with_root_candidates(self):
        """IssueCluster with hypothesis seeds validates correctly."""
        alert = ClusterAlert(
            resource_key="Pod/default/web-abc",
            alert_type="CrashLoopBackOff",
            severity="high",
            timestamp="2026-03-01T00:05:00Z",
        )
        candidate = RootCandidate(
            resource_key="Deployment/default/web",
            hypothesis="OOMKilled due to memory-limit misconfiguration",
            supporting_signals=["container_oom_events_total > 5", "memory_usage_ratio > 0.95"],
            confidence=0.85,
        )
        cluster = IssueCluster(
            cluster_id="ic-001",
            alerts=[alert],
            root_candidates=[candidate],
            confidence=0.8,
            correlation_basis=["namespace", "owner-ref"],
            affected_resources=["Pod/default/web-abc", "Pod/default/web-def"],
        )

        assert cluster.cluster_id == "ic-001"
        assert len(cluster.alerts) == 1
        assert cluster.alerts[0].alert_type == "CrashLoopBackOff"
        assert len(cluster.root_candidates) == 1
        assert cluster.root_candidates[0].confidence == 0.85
        assert len(cluster.root_candidates[0].supporting_signals) == 2
        assert cluster.confidence == 0.8
        assert "namespace" in cluster.correlation_basis
        assert len(cluster.affected_resources) == 2

    def test_cluster_alert_defaults(self):
        """ClusterAlert has sensible defaults for optional fields."""
        alert = ClusterAlert(resource_key="Node/node-1", alert_type="NotReady")
        assert alert.severity == "medium"
        assert alert.timestamp == ""
        assert alert.raw_event == {}

    def test_root_candidate_defaults(self):
        """RootCandidate defaults to 0.5 confidence and empty signals."""
        rc = RootCandidate(resource_key="Pod/default/x", hypothesis="disk pressure")
        assert rc.confidence == 0.5
        assert rc.supporting_signals == []


class TestCausalFirewallModels:
    """Tests for BlockedLink, CausalAnnotation, and CausalSearchSpace."""

    def test_blocked_link_justification(self):
        """BlockedLink carries all invariant justification fields."""
        bl = BlockedLink(
            from_resource="Pod/default/web-abc",
            to_resource="Node/node-3",
            reason_code="NO_SCHEDULE_AFFINITY",
            invariant_id="INV-007",
            invariant_description="Pod cannot cause node-level failure without schedule affinity",
            timestamp="2026-03-01T00:10:00Z",
        )

        assert bl.from_resource == "Pod/default/web-abc"
        assert bl.to_resource == "Node/node-3"
        assert bl.reason_code == "NO_SCHEDULE_AFFINITY"
        assert bl.invariant_id == "INV-007"
        assert bl.invariant_description == "Pod cannot cause node-level failure without schedule affinity"
        assert bl.timestamp == "2026-03-01T00:10:00Z"

    def test_causal_annotation_defaults(self):
        """CausalAnnotation defaults to 0.5 confidence and empty reason."""
        ann = CausalAnnotation(
            from_resource="Service/default/api",
            to_resource="Pod/default/api-abc",
            rule_id="RULE-001",
        )
        assert ann.confidence_hint == 0.5
        assert ann.reason == ""
        assert ann.supporting_evidence == []

    def test_causal_search_space_counts(self):
        """CausalSearchSpace counts are correct when populated."""
        blocked = BlockedLink(
            from_resource="A",
            to_resource="B",
            reason_code="CROSS_NS",
            invariant_id="INV-001",
            invariant_description="Cross-namespace causal link not allowed",
        )
        space = CausalSearchSpace(
            valid_links=[{"from": "C", "to": "D"}],
            annotated_links=[{"from": "C", "to": "D", "confidence": 0.9}],
            blocked_links=[blocked],
            total_evaluated=10,
            total_blocked=1,
            total_annotated=1,
        )

        assert len(space.valid_links) == 1
        assert len(space.annotated_links) == 1
        assert len(space.blocked_links) == 1
        assert space.total_evaluated == 10
        assert space.total_blocked == 1
        assert space.total_annotated == 1

    def test_causal_search_space_defaults(self):
        """Empty CausalSearchSpace has zero counts and empty lists."""
        space = CausalSearchSpace()
        assert space.valid_links == []
        assert space.annotated_links == []
        assert space.blocked_links == []
        assert space.total_evaluated == 0
        assert space.total_blocked == 0
        assert space.total_annotated == 0


class TestGuardModeModels:
    """Tests for CurrentRisk, PredictiveRisk, ScanDelta, and GuardScanResult."""

    def test_guard_scan_result_defaults(self):
        """Empty GuardScanResult has UNKNOWN health and zero risk score."""
        result = GuardScanResult()
        assert result.scan_id == ""
        assert result.scanned_at == ""
        assert result.platform == ""
        assert result.platform_version == ""
        assert result.current_risks == []
        assert result.predictive_risks == []
        assert result.overall_health == "UNKNOWN"
        assert result.risk_score == 0.0
        # Delta should also be default
        assert result.delta.new_risks == []
        assert result.delta.resolved_risks == []
        assert result.delta.previous_scan_id is None

    def test_guard_scan_result_three_layers(self):
        """GuardScanResult with current risks, predictive risks, and delta."""
        current = CurrentRisk(
            category="resource_exhaustion",
            severity="critical",
            resource="Node/node-2",
            description="Node memory above 95%",
            affected_count=12,
            issue_cluster_id="ic-003",
        )
        predictive = PredictiveRisk(
            category="disk_pressure",
            severity="warning",
            resource="PVC/default/data-vol",
            description="PVC projected to fill within 48h",
            predicted_impact="Pod evictions on node-2",
            time_horizon="48h",
            trend_data=[{"ts": "2026-03-01T00:00:00Z", "value": 88.5}],
        )
        delta = ScanDelta(
            new_risks=["resource_exhaustion:Node/node-2"],
            resolved_risks=["network_partition:Node/node-1"],
            worsened=["disk_pressure:PVC/default/data-vol"],
            improved=[],
            previous_scan_id="scan-099",
            previous_scanned_at="2026-02-28T23:00:00Z",
        )
        result = GuardScanResult(
            scan_id="scan-100",
            scanned_at="2026-03-01T00:00:00Z",
            platform="EKS",
            platform_version="1.29",
            current_risks=[current],
            predictive_risks=[predictive],
            delta=delta,
            overall_health="DEGRADED",
            risk_score=72.5,
        )

        assert result.scan_id == "scan-100"
        assert result.overall_health == "DEGRADED"
        assert result.risk_score == 72.5

        # Current risks
        assert len(result.current_risks) == 1
        assert result.current_risks[0].category == "resource_exhaustion"
        assert result.current_risks[0].severity == "critical"
        assert result.current_risks[0].affected_count == 12
        assert result.current_risks[0].issue_cluster_id == "ic-003"

        # Predictive risks
        assert len(result.predictive_risks) == 1
        assert result.predictive_risks[0].time_horizon == "48h"
        assert len(result.predictive_risks[0].trend_data) == 1

        # Delta
        assert len(result.delta.new_risks) == 1
        assert len(result.delta.resolved_risks) == 1
        assert result.delta.previous_scan_id == "scan-099"

    def test_scan_delta_defaults(self):
        """ScanDelta defaults to empty lists and None scan references."""
        delta = ScanDelta()
        assert delta.new_risks == []
        assert delta.resolved_risks == []
        assert delta.worsened == []
        assert delta.improved == []
        assert delta.previous_scan_id is None
        assert delta.previous_scanned_at is None


class TestExistingModelsUnaffected:
    """Ensure pre-existing models still work after adding new ones."""

    def test_existing_models_unaffected(self):
        """DomainReport, CausalChain, and ClusterHealthReport still instantiate correctly."""
        # DomainReport
        report = DomainReport(domain="networking")
        assert report.domain == "networking"
        assert report.status.value == "PENDING"
        assert report.anomalies == []
        assert report.confidence == 0

        # CausalChain
        anomaly = DomainAnomaly(
            domain="compute",
            anomaly_id="a-1",
            description="OOMKilled",
            evidence_ref="ev-1",
        )
        chain = CausalChain(chain_id="cc-1", confidence=0.9, root_cause=anomaly)
        assert chain.chain_id == "cc-1"
        assert chain.confidence == 0.9
        assert chain.root_cause.domain == "compute"
        assert chain.cascading_effects == []

        # ClusterHealthReport
        health = ClusterHealthReport(diagnostic_id="diag-001")
        assert health.diagnostic_id == "diag-001"
        assert health.platform_health == "UNKNOWN"
        assert health.data_completeness == 0.0
        assert health.causal_chains == []
        assert health.domain_reports == []

import pytest
from src.agents.cluster.state import (
    FailureReason, DomainStatus, DomainAnomaly, TruncationFlags,
    DomainReport, CausalLink, CausalChain, BlastRadius,
    RemediationStep, ClusterHealthReport, ClusterDiagnosticState,
)


def test_domain_report_defaults():
    report = DomainReport(domain="ctrl_plane")
    assert report.status == DomainStatus.PENDING
    assert report.confidence == 0
    assert report.anomalies == []
    assert report.ruled_out == []
    assert report.evidence_refs == []
    assert report.truncation_flags == TruncationFlags()


def test_domain_report_failed():
    report = DomainReport(
        domain="node",
        status=DomainStatus.FAILED,
        failure_reason=FailureReason.TIMEOUT,
        confidence=0,
        data_gathered_before_failure=["3 nodes checked before timeout"],
    )
    assert report.failure_reason == FailureReason.TIMEOUT
    assert len(report.data_gathered_before_failure) == 1


def test_causal_chain_weakest_link():
    chain = CausalChain(
        chain_id="cc-001",
        confidence=0.88,
        root_cause=DomainAnomaly(
            domain="node", anomaly_id="node-003",
            description="disk full", evidence_ref="ev-001",
        ),
        cascading_effects=[
            CausalLink(
                order=1, domain="ctrl_plane", anomaly_id="cp-002",
                description="pods evicted",
                link_type="resource_exhaustion -> pod_eviction",
                evidence_ref="ev-002",
            ),
        ],
    )
    assert chain.chain_id == "cc-001"
    assert chain.cascading_effects[0].link_type == "resource_exhaustion -> pod_eviction"


def test_cluster_diagnostic_state_defaults():
    state = ClusterDiagnosticState(diagnostic_id="DIAG-001")
    assert state.platform == ""
    assert len(state.domain_reports) == 0
    assert len(state.causal_chains) == 0
    assert state.re_dispatch_count == 0
    assert state.phase == "pre_flight"


def test_cluster_health_report_serialization():
    report = ClusterHealthReport(
        diagnostic_id="DIAG-001",
        platform="openshift",
        platform_version="4.14.2",
        platform_health="DEGRADED",
        data_completeness=0.75,
        blast_radius=BlastRadius(
            summary="14% of nodes under pressure",
            affected_namespaces=3, affected_pods=47, affected_nodes=2,
        ),
        causal_chains=[],
        uncorrelated_findings=[],
        domain_reports=[],
        remediation={"immediate": [], "long_term": []},
        execution_metadata={
            "total_duration_ms": 18340, "token_usage_total": 12500,
            "re_dispatch_count": 0, "agents_succeeded": 4, "agents_failed": 0,
        },
    )
    data = report.model_dump(mode="json")
    assert data["platform_health"] == "DEGRADED"
    assert data["blast_radius"]["affected_pods"] == 47

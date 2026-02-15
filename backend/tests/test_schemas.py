import pytest
from datetime import datetime
from src.models.schemas import (
    Breadcrumb, NegativeFinding, Finding, CriticVerdict,
    TokenUsage, TaskEvent, ErrorPattern, LogEvidence,
    MetricAnomaly, DataPoint, TimeRange, PodHealthStatus,
    K8sEvent, SpanInfo, ImpactedFile, LineRange, FixArea,
    DiagnosticPhase, DiagnosticState, TimeWindow,
    LogAnalysisResult, MetricsAnalysisResult, K8sAnalysisResult,
    TraceAnalysisResult, CodeAnalysisResult, SessionTokenSummary
)


def test_breadcrumb_creation():
    b = Breadcrumb(
        agent_name="log_agent",
        action="queried_elasticsearch",
        source_type="log",
        source_reference="app-logs-2025.12.26, ID: R3znW5",
        raw_evidence="ConnectionTimeout after 30000ms",
        timestamp=datetime.now()
    )
    assert b.agent_name == "log_agent"
    assert b.source_type == "log"


def test_finding_with_confidence_score():
    f = Finding(
        finding_id="f1",
        agent_name="log_agent",
        category="database_timeout",
        summary="DB connection timed out",
        confidence_score=85,
        severity="critical",
        breadcrumbs=[],
        negative_findings=[]
    )
    assert f.confidence_score == 85
    assert f.severity == "critical"
    assert f.critic_verdict is None


def test_diagnostic_state_phases():
    assert DiagnosticPhase.INITIAL == "initial"
    assert DiagnosticPhase.DIAGNOSIS_COMPLETE == "diagnosis_complete"
    assert DiagnosticPhase.COMPLETE == "complete"


def test_error_pattern_priority():
    p = ErrorPattern(
        pattern_id="p1",
        exception_type="ConnectionTimeout",
        error_message="DB timeout after 30s",
        frequency=47,
        severity="critical",
        affected_components=["order-service"],
        sample_logs=[],
        confidence_score=87,
        priority_rank=1,
        priority_reasoning="Highest frequency and severity"
    )
    assert p.priority_rank == 1
    assert p.frequency == 47


def test_token_usage():
    t = TokenUsage(
        agent_name="log_agent",
        input_tokens=1500,
        output_tokens=800,
        total_tokens=2300
    )
    assert t.total_tokens == 2300
    assert t.agent_name == "log_agent"


def test_negative_finding():
    nf = NegativeFinding(
        agent_name="log_agent",
        what_was_checked="Database logs for trace_id abc-123",
        result="Zero errors found",
        implication="Issue is NOT in DB layer",
        source_reference="db-logs-2025.12.26"
    )
    assert "NOT" in nf.implication


def test_diagnostic_state_defaults():
    state = DiagnosticState(
        session_id="test-123",
        phase=DiagnosticPhase.INITIAL,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now")
    )
    assert state.phase == DiagnosticPhase.INITIAL
    assert state.log_analysis is None
    assert state.all_findings == []
    assert state.overall_confidence == 0


def test_critic_verdict():
    cv = CriticVerdict(
        finding_id="f1",
        agent_source="log_agent",
        verdict="challenged",
        reasoning="Metrics show DB is healthy",
        confidence_in_verdict=85
    )
    assert cv.verdict == "challenged"


def test_metric_anomaly():
    ma = MetricAnomaly(
        metric_name="container_memory_usage",
        promql_query="container_memory_working_set_bytes{pod=~'order.*'}",
        baseline_value=200.0,
        peak_value=510.0,
        spike_start=datetime(2025, 12, 26, 14, 2),
        spike_end=datetime(2025, 12, 26, 14, 15),
        severity="critical",
        correlation_to_incident="Memory spike preceded first error by 13 minutes",
        confidence_score=90
    )
    assert ma.peak_value == 510.0


def test_span_info():
    s = SpanInfo(
        span_id="s1",
        service_name="order-service",
        operation_name="processOrder",
        duration_ms=31000.0,
        status="timeout",
        error_message="Connection timed out",
        tags={"db.type": "postgresql"}
    )
    assert s.status == "timeout"


def test_pod_health_status():
    p = PodHealthStatus(
        pod_name="order-svc-7f8b9-x4k2p",
        status="CrashLoopBackOff",
        restart_count=6,
        last_termination_reason="OOMKilled",
        resource_requests={"memory": "256Mi", "cpu": "250m"},
        resource_limits={"memory": "512Mi", "cpu": "500m"}
    )
    assert p.restart_count == 6
    assert p.last_termination_reason == "OOMKilled"


def test_session_token_summary():
    s = SessionTokenSummary(
        by_agent=[
            TokenUsage(agent_name="log_agent", input_tokens=1000, output_tokens=500, total_tokens=1500),
            TokenUsage(agent_name="metrics_agent", input_tokens=800, output_tokens=400, total_tokens=1200),
        ],
        grand_total_input=1800,
        grand_total_output=900,
        grand_total=2700
    )
    assert s.grand_total == 2700
    assert len(s.by_agent) == 2

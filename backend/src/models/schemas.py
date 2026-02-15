from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class DiagnosticPhase(str, Enum):
    INITIAL = "initial"
    COLLECTING_CONTEXT = "collecting_context"
    LOGS_ANALYZED = "logs_analyzed"
    METRICS_ANALYZED = "metrics_analyzed"
    K8S_ANALYZED = "k8s_analyzed"
    TRACING_ANALYZED = "tracing_analyzed"
    CODE_ANALYZED = "code_analyzed"
    VALIDATING = "validating"
    RE_INVESTIGATING = "re_investigating"
    DIAGNOSIS_COMPLETE = "diagnosis_complete"
    FIX_IN_PROGRESS = "fix_in_progress"
    COMPLETE = "complete"


class Breadcrumb(BaseModel):
    agent_name: str
    action: str
    source_type: Literal["log", "metric", "k8s_event", "trace_span", "code", "config"]
    source_reference: str
    raw_evidence: str
    timestamp: datetime


class NegativeFinding(BaseModel):
    agent_name: str
    what_was_checked: str
    result: str
    implication: str
    source_reference: str


class CriticVerdict(BaseModel):
    finding_id: str
    agent_source: str
    verdict: Literal["validated", "challenged", "insufficient_data"]
    reasoning: str
    contradicting_evidence: Optional[list[Breadcrumb]] = None
    recommendation: Optional[str] = None
    confidence_in_verdict: int = Field(ge=0, le=100)


class Finding(BaseModel):
    finding_id: str
    agent_name: str
    category: str
    summary: str
    confidence_score: int = Field(ge=0, le=100)
    severity: Literal["critical", "high", "medium", "low"]
    breadcrumbs: list[Breadcrumb]
    negative_findings: list[NegativeFinding]
    critic_verdict: Optional[CriticVerdict] = None


class TokenUsage(BaseModel):
    agent_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int

    @model_validator(mode="after")
    def check_total(self):
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        return self


class TaskEvent(BaseModel):
    timestamp: datetime
    agent_name: str
    event_type: Literal["started", "progress", "success", "warning", "error"]
    message: str
    details: Optional[dict] = None


class LogEvidence(BaseModel):
    log_id: str
    index: str
    timestamp: datetime
    level: str
    message: str
    service: Optional[str] = None
    raw_line: str


class ErrorPattern(BaseModel):
    pattern_id: str
    exception_type: str
    error_message: str
    frequency: int
    severity: Literal["critical", "high", "medium", "low"]
    affected_components: list[str]
    sample_logs: list[LogEvidence]
    confidence_score: int = Field(ge=0, le=100)
    priority_rank: int
    priority_reasoning: str


class LogAnalysisResult(BaseModel):
    primary_pattern: ErrorPattern
    secondary_patterns: list[ErrorPattern]
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int = Field(ge=0, le=100)
    tokens_used: TokenUsage


class DataPoint(BaseModel):
    timestamp: datetime
    value: float


class TimeRange(BaseModel):
    start: datetime
    end: datetime


class MetricAnomaly(BaseModel):
    metric_name: str
    promql_query: str
    baseline_value: float
    peak_value: float
    spike_start: datetime
    spike_end: datetime
    severity: Literal["critical", "high", "medium", "low"]
    correlation_to_incident: str
    confidence_score: int = Field(ge=0, le=100)


class MetricsAnalysisResult(BaseModel):
    anomalies: list[MetricAnomaly]
    time_series_data: dict[str, list[DataPoint]]
    chart_highlights: list[TimeRange]
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int = Field(ge=0, le=100)
    tokens_used: TokenUsage


class PodHealthStatus(BaseModel):
    pod_name: str
    status: str
    restart_count: int
    last_termination_reason: Optional[str] = None
    last_restart_time: Optional[datetime] = None
    resource_requests: dict[str, str]
    resource_limits: dict[str, str]


class K8sEvent(BaseModel):
    timestamp: datetime
    type: Literal["Normal", "Warning"]
    reason: str
    message: str
    source_component: str


class K8sAnalysisResult(BaseModel):
    cluster_name: str
    namespace: str
    service_name: str
    pod_statuses: list[PodHealthStatus]
    events: list[K8sEvent]
    is_crashloop: bool
    total_restarts_last_hour: int
    resource_mismatch: Optional[str] = None
    findings: list[Finding]
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int = Field(ge=0, le=100)
    tokens_used: TokenUsage


class SpanInfo(BaseModel):
    span_id: str
    service_name: str
    operation_name: str
    duration_ms: float
    status: Literal["ok", "error", "timeout"]
    error_message: Optional[str] = None
    parent_span_id: Optional[str] = None
    tags: dict[str, str]


class TraceAnalysisResult(BaseModel):
    trace_id: str
    total_duration_ms: float
    total_services: int
    total_spans: int
    call_chain: list[SpanInfo]
    failure_point: Optional[SpanInfo] = None
    cascade_path: list[str]
    latency_bottlenecks: list[SpanInfo]
    retry_detected: bool
    service_dependency_graph: dict[str, list[str]]
    trace_source: Literal["jaeger", "tempo", "elasticsearch", "combined"]
    elk_reconstruction_confidence: Optional[int] = Field(default=None, ge=0, le=100)
    findings: list[Finding]
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int = Field(ge=0, le=100)
    tokens_used: TokenUsage


class LineRange(BaseModel):
    start: int
    end: int


class ImpactedFile(BaseModel):
    file_path: str
    impact_type: Literal["direct_error", "caller", "callee", "shared_resource", "config", "test"]
    relevant_lines: list[LineRange]
    code_snippet: str
    relationship: str
    fix_relevance: Literal["must_fix", "should_review", "informational"]


class FixArea(BaseModel):
    file_path: str
    description: str
    suggested_change: str


class CodeAnalysisResult(BaseModel):
    root_cause_location: ImpactedFile
    impacted_files: list[ImpactedFile]
    call_chain: list[str]
    dependency_graph: dict[str, list[str]]
    shared_resource_conflicts: list[str]
    suggested_fix_areas: list[FixArea]
    mermaid_diagram: str
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int = Field(ge=0, le=100)
    tokens_used: TokenUsage


class SessionTokenSummary(BaseModel):
    by_agent: list[TokenUsage]
    grand_total_input: int
    grand_total_output: int
    grand_total: int


class TimeWindow(BaseModel):
    start: str
    end: str


class DiagnosticState(BaseModel):
    session_id: str
    phase: DiagnosticPhase

    # User input
    service_name: str
    trace_id: Optional[str] = None
    time_window: TimeWindow
    cluster_url: Optional[str] = None
    namespace: Optional[str] = None
    repo_url: Optional[str] = None

    # Agent results
    log_analysis: Optional[LogAnalysisResult] = None
    metrics_analysis: Optional[MetricsAnalysisResult] = None
    k8s_analysis: Optional[K8sAnalysisResult] = None
    trace_analysis: Optional[TraceAnalysisResult] = None
    code_analysis: Optional[CodeAnalysisResult] = None

    # Cross-cutting
    all_findings: list[Finding] = []
    all_negative_findings: list[NegativeFinding] = []
    all_breadcrumbs: list[Breadcrumb] = []
    critic_verdicts: list[CriticVerdict] = []

    # Tracking
    token_usage: list[TokenUsage] = []
    task_events: list[TaskEvent] = []

    # Supervisor decisions
    supervisor_reasoning: list[str] = []
    agents_completed: list[str] = []
    agents_pending: list[str] = []
    overall_confidence: int = Field(default=0, ge=0, le=100)

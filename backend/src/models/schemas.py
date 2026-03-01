from pydantic import BaseModel, Field, computed_field, model_validator
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
    ERROR = "error"


class FixStatus(str, Enum):
    NOT_STARTED = "not_started"
    GENERATING = "generating"
    AWAITING_REVIEW = "awaiting_review"
    HUMAN_FEEDBACK = "human_feedback"
    VERIFICATION_IN_PROGRESS = "verification_in_progress"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    APPROVED = "approved"
    REJECTED = "rejected"
    PR_CREATING = "pr_creating"
    PR_CREATED = "pr_created"
    FAILED = "failed"


class Breadcrumb(BaseModel):
    agent_name: str
    action: str
    source_type: Literal["log", "metric", "k8s_event", "trace_span", "code", "config"]
    source_reference: str
    raw_evidence: str
    timestamp: datetime

    @computed_field
    @property
    def detail(self) -> str:
        return f"[{self.source_type}] {self.raw_evidence}" if self.raw_evidence else self.source_reference


class NegativeFinding(BaseModel):
    agent_name: str
    what_was_checked: str
    result: str
    implication: str
    source_reference: str

    @computed_field
    @property
    def agent(self) -> str:
        return self.agent_name

    @computed_field
    @property
    def category(self) -> str:
        return self.what_was_checked

    @computed_field
    @property
    def description(self) -> str:
        return f"{self.result} — {self.implication}"


class CriticVerdict(BaseModel):
    finding_id: str
    agent_source: str
    verdict: Literal["validated", "challenged", "insufficient_data"]
    reasoning: str
    contradicting_evidence: Optional[list[Breadcrumb]] = None
    recommendation: Optional[str] = None
    confidence_in_verdict: int = Field(ge=0, le=100)

    @computed_field
    @property
    def finding_index(self) -> int:
        # Extract numeric suffix from finding_id for frontend compatibility
        import re
        nums = re.findall(r'\d+', self.finding_id)
        return int(nums[-1]) if nums else 0

    @computed_field
    @property
    def finding_title(self) -> str:
        return self.agent_source

    @computed_field
    @property
    def confidence(self) -> int:
        return self.confidence_in_verdict


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
    resource_refs: list["ResourceRef"] = Field(default_factory=list)

    @computed_field
    @property
    def title(self) -> str:
        return self.summary

    @computed_field
    @property
    def description(self) -> str:
        return self.summary

    @computed_field
    @property
    def confidence(self) -> int:
        return self.confidence_score

    @computed_field
    @property
    def evidence(self) -> list[str]:
        return [f"[{b.source_type}] {b.action}: {b.raw_evidence}" for b in self.breadcrumbs]

    @computed_field
    @property
    def suggested_fix(self) -> Optional[str]:
        if self.critic_verdict and self.critic_verdict.recommendation:
            return self.critic_verdict.recommendation
        return None


class TokenUsage(BaseModel):
    agent_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int

    @model_validator(mode="after")
    def check_total(self):
        # total_tokens may include cache tokens, so only validate it's >= sum
        expected = self.input_tokens + self.output_tokens
        if self.total_tokens < expected:
            self.total_tokens = expected
        return self


class TaskEvent(BaseModel):
    timestamp: datetime
    agent_name: str
    event_type: Literal["started", "progress", "success", "warning", "error", "tool_call", "phase_change", "finding", "summary", "attestation_required", "fix_proposal", "fix_approved", "waiting_for_input"]
    message: str
    details: Optional[dict] = None
    session_id: Optional[str] = None


class LogEvidence(BaseModel):
    log_id: str
    index: str
    timestamp: datetime
    level: str
    message: str
    service: Optional[str] = None
    raw_line: str


class ServiceFlowStep(BaseModel):
    """A single step in the temporal flow reconstruction from logs."""
    service: str
    timestamp: str
    operation: str
    status: Literal["ok", "error", "timeout"]
    status_detail: str = ""
    message: str = ""
    is_new_service: bool = True


# ---------------------------------------------------------------------------
# Typed models for fields previously stored as untyped dicts
# ---------------------------------------------------------------------------


class PatientZeroInfo(BaseModel):
    """Patient zero identification from log agent."""
    service: str = ""
    evidence: str = ""
    first_error_time: str = ""


class InferredDependencyInfo(BaseModel):
    """Inferred service dependency from log agent."""
    source: str = ""
    target: Optional[str] = None
    evidence: Optional[str] = None
    targets: Optional[list[str]] = None


class ReasoningChainStepInfo(BaseModel):
    """A single step in the reasoning chain from log agent."""
    step: int = 0
    observation: str = ""
    inference: str = ""


class SuggestedPromQLInfo(BaseModel):
    """A suggested PromQL query from log/metrics agent."""
    metric: str = ""
    query: str = ""
    rationale: str = ""


class PastIncidentMatchInfo(BaseModel):
    """A matching past incident from memory/similarity search."""
    fingerprint_id: str = ""
    session_id: str = ""
    similarity_score: float = 0.0
    root_cause: str = ""
    resolution_steps: list[str] = Field(default_factory=list)
    error_patterns: list[str] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    time_to_resolve: int = 0


class CrossRepoFindingInfo(BaseModel):
    """Cross-repo finding from code agent."""
    repo: str = ""
    role: str = ""
    evidence: str = ""


class FixVerificationResult(BaseModel):
    """Verification result for a generated fix."""
    verdict: Literal["approve", "reject", "needs_changes"] = "needs_changes"
    confidence: int = 0
    issues_found: list[str] = Field(default_factory=list)
    regression_risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    reasoning: str = ""


class PRData(BaseModel):
    """PR creation data from fix pipeline."""
    branch_name: str = ""
    commit_sha: str = ""
    pr_title: str = ""
    pr_body: str = ""
    diff: str = ""
    validation: dict = Field(default_factory=dict)
    impact: dict = Field(default_factory=dict)
    fixed_code: str = ""
    status: str = ""
    token_usage: dict = Field(default_factory=dict)
    # Allow extra fields from agent3 which returns a different shape
    model_config = {"extra": "allow"}


class HighPriorityFileInfo(BaseModel):
    """A high-priority file from change analysis."""
    file_path: str = ""
    risk_score: float = 0.0
    sha: str = ""
    description: str = ""


class ChangeCorrelationInfo(BaseModel):
    """A change correlation from change agent."""
    change_id: str = ""
    change_type: str = "code_deploy"
    risk_score: float = 0.0
    temporal_correlation: float = 0.0
    scope_overlap: Optional[float] = None
    author: str = ""
    description: str = ""
    files_changed: list[str] = Field(default_factory=list)
    timestamp: Optional[str] = None
    service_name: Optional[str] = None
    reasoning: Optional[str] = None


class ChangeAnalysisResult(BaseModel):
    """Structured change analysis result from change agent."""
    change_correlations: list[ChangeCorrelationInfo] = Field(default_factory=list)
    high_priority_files: list[HighPriorityFileInfo] = Field(default_factory=list)
    summary: Optional[str] = None
    breadcrumbs: list = Field(default_factory=list)
    negative_findings: list = Field(default_factory=list)
    tokens_used: Optional[dict] = None
    # Allow extra fields from agent
    model_config = {"extra": "allow"}


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
    # Enrichment fields (backward compatible)
    stack_traces: list[str] = Field(default_factory=list)
    correlation_ids: list[str] = Field(default_factory=list)
    sample_log_ids: list[str] = Field(default_factory=list)
    causal_role: Optional[Literal["root_cause", "cascading_failure", "correlated_anomaly"]] = None

    @computed_field
    @property
    def pattern(self) -> str:
        return self.exception_type

    @computed_field
    @property
    def count(self) -> int:
        return self.frequency

    @computed_field
    @property
    def sample_message(self) -> str:
        return self.error_message

    @computed_field
    @property
    def confidence(self) -> int:
        return self.confidence_score

    @computed_field
    @property
    def first_seen(self) -> Optional[str]:
        if self.sample_logs:
            return self.sample_logs[0].timestamp.isoformat()
        return None

    @computed_field
    @property
    def last_seen(self) -> Optional[str]:
        if self.sample_logs:
            return self.sample_logs[-1].timestamp.isoformat()
        return None


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

    @computed_field
    @property
    def current_value(self) -> float:
        return self.peak_value

    @computed_field
    @property
    def deviation_percent(self) -> float:
        if self.baseline_value == 0:
            return 0.0 if self.peak_value == 0 else round(self.peak_value * 100, 1)
        return round(((self.peak_value - self.baseline_value) / self.baseline_value) * 100, 1)

    @computed_field
    @property
    def direction(self) -> str:
        return "above" if self.peak_value >= self.baseline_value else "below"

    @computed_field
    @property
    def timestamp(self) -> datetime:
        return self.spike_start


class CorrelatedSignalGroup(BaseModel):
    group_name: str
    signal_type: Literal["RED", "USE"]
    metrics: list[str]
    narrative: str


class EventMarker(BaseModel):
    timestamp: datetime
    label: str
    source: str
    severity: Literal["critical", "high", "medium", "low", "info"] = "info"


class MetricsAnalysisResult(BaseModel):
    anomalies: list[MetricAnomaly]
    correlated_signals: list[CorrelatedSignalGroup] = []
    event_markers: list[EventMarker] = []
    time_series_data: dict[str, list[DataPoint]]
    chart_highlights: list[TimeRange]
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int = Field(ge=0, le=100)
    tokens_used: TokenUsage


class PodHealthStatus(BaseModel):
    pod_name: str
    namespace: str = ""
    status: str
    restart_count: int
    last_termination_reason: Optional[str] = None
    last_restart_time: Optional[datetime] = None
    resource_requests: dict[str, str] = Field(default_factory=dict)
    resource_limits: dict[str, str] = Field(default_factory=dict)
    init_container_failures: list[str] = Field(default_factory=list)
    image_pull_errors: list[str] = Field(default_factory=list)
    container_count: int = 0
    ready_containers: int = 0

    @computed_field
    @property
    def ready(self) -> bool:
        return self.status.lower() in ("running", "ready")

    @computed_field
    @property
    def conditions(self) -> list[str]:
        conds = []
        if self.status:
            conds.append(self.status)
        if self.last_termination_reason:
            conds.append(self.last_termination_reason)
        return conds

    @computed_field
    @property
    def oom_killed(self) -> bool:
        return self.last_termination_reason == "OOMKilled" if self.last_termination_reason else False

    @computed_field
    @property
    def crash_loop(self) -> bool:
        return self.restart_count >= 3 and self.status.lower() in ("crashloopbackoff", "error", "waiting")


class K8sEvent(BaseModel):
    timestamp: datetime
    type: Literal["Normal", "Warning"]
    reason: str
    message: str
    source_component: str
    count: int = 1
    involved_object: str = ""

    @computed_field
    @property
    def first_timestamp(self) -> str:
        return self.timestamp.isoformat()

    @computed_field
    @property
    def last_timestamp(self) -> str:
        return self.timestamp.isoformat()


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
    tags: dict[str, str] = Field(default_factory=dict)

    @computed_field
    @property
    def service(self) -> str:
        return self.service_name

    @computed_field
    @property
    def operation(self) -> str:
        return self.operation_name

    @computed_field
    @property
    def error(self) -> bool:
        return self.status == "error" or self.error_message is not None


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


class FixedFile(BaseModel):
    """A single file's fix data within a multi-file fix."""
    file_path: str
    original_code: str = ""
    fixed_code: str = ""
    diff: str = ""


class FixResult(BaseModel):
    fix_status: FixStatus = FixStatus.NOT_STARTED
    target_file: str = ""               # Primary file (backward compat)
    original_code: str = ""             # Primary file's original (backward compat)
    generated_fix: str = ""             # Primary file's fix (backward compat)
    diff: str = ""                      # Primary file's diff (backward compat)
    fixed_files: list[FixedFile] = Field(default_factory=list)  # All files
    fix_explanation: str = ""
    pr_data: Optional[PRData | dict] = None
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    verification_result: Optional[FixVerificationResult | dict] = None
    human_feedback: list[str] = Field(default_factory=list)
    attempt_count: int = 0
    max_attempts: int = 2


class DiffAnalysisItem(BaseModel):
    file: str
    commit_sha: str = ""
    verdict: Literal["likely_cause", "unrelated", "contributing"] = "unrelated"
    reasoning: str = ""


class CodeAnalysisResult(BaseModel):
    root_cause_location: ImpactedFile
    impacted_files: list[ImpactedFile]
    call_chain: list[str]
    dependency_graph: dict[str, list[str]]
    shared_resource_conflicts: list[str]
    suggested_fix_areas: list[FixArea]
    diff_analysis: list[DiffAnalysisItem] = Field(default_factory=list)
    cross_repo_findings: list[CrossRepoFindingInfo | dict] = Field(default_factory=list)
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


# ---------------------------------------------------------------------------
# v5 Governance Models
# ---------------------------------------------------------------------------


class EvidencePin(BaseModel):
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    claim: str = Field(..., min_length=1)
    supporting_evidence: list[str] = []
    source_agent: Optional[str] = None
    source_tool: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    timestamp: datetime
    evidence_type: Literal["log", "metric", "trace", "k8s_event", "k8s_resource", "code", "change"]

    # Live investigation steering fields
    source: Literal["auto", "manual"] = "auto"
    triggered_by: Literal["automated_pipeline", "user_chat", "quick_action"] = "automated_pipeline"
    raw_output: Optional[str] = None
    severity: Optional[Literal["critical", "high", "medium", "low", "info"]] = None
    causal_role: Optional[Literal["root_cause", "cascading_symptom", "correlated", "informational"]] = None
    domain: Literal["compute", "network", "storage", "control_plane", "security", "unknown"] = "unknown"
    validation_status: Literal["pending_critic", "validated", "rejected"] = "pending_critic"
    namespace: Optional[str] = None
    service: Optional[str] = None
    resource_name: Optional[str] = None
    time_window: Optional[TimeWindow] = None
    resource_refs: list["ResourceRef"] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# War Room v2 Models
# ---------------------------------------------------------------------------


class ResourceRef(BaseModel):
    """A reference to a Kubernetes/OpenShift resource for click-anywhere drill-down."""
    type: str  # pod, deployment, service, configmap, pvc, node, ingress,
               # replicaset, deploymentconfig, route, buildconfig, imagestream
    name: str
    namespace: Optional[str] = None
    status: Optional[str] = None    # Running, CrashLoopBackOff — for hover tooltip
    age: Optional[str] = None       # "2d", "15m" — for hover tooltip


class CommandStep(BaseModel):
    """A single command in an operational recommendation."""
    order: int
    description: str
    command: str
    command_type: Literal["kubectl", "oc", "helm", "shell"]
    is_dry_run: bool = False
    dry_run_command: Optional[str] = None
    validation_command: Optional[str] = None


class OperationalRecommendation(BaseModel):
    """A copy-paste ready operational command recommendation."""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    title: str
    urgency: Literal["immediate", "short_term", "preventive"]
    category: Literal["scale", "rollback", "restart", "config_patch", "network", "storage"]
    commands: list[CommandStep]
    rollback_commands: list[CommandStep] = Field(default_factory=list)
    risk_level: Literal["safe", "caution", "destructive"]
    prerequisites: list[str] = Field(default_factory=list)
    expected_outcome: str = ""
    resource_refs: list[ResourceRef] = Field(default_factory=list)


class CausalTree(BaseModel):
    """An independent root cause with its cascading symptoms and recommendations."""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    root_cause: Finding
    severity: Literal["critical", "warning", "info"]
    blast_radius: Optional[dict] = None
    cascading_symptoms: list[Finding] = Field(default_factory=list)
    correlated_signals: list[CorrelatedSignalGroup] = Field(default_factory=list)
    operational_recommendations: list[OperationalRecommendation] = Field(default_factory=list)
    triage_status: Literal["untriaged", "acknowledged", "mitigated", "resolved"] = "untriaged"
    resource_refs: list[ResourceRef] = Field(default_factory=list)


# Rebuild models that use forward references to ResourceRef
Finding.model_rebuild()
EvidencePin.model_rebuild()


class ConfidenceLedger(BaseModel):
    log_confidence: float = 0.0
    metrics_confidence: float = 0.0
    tracing_confidence: float = 0.0
    k8s_confidence: float = 0.0
    code_confidence: float = 0.0
    change_confidence: float = 0.0
    critic_adjustment: float = Field(default=0.0, ge=-0.3, le=0.1)
    weighted_final: float = 0.0
    weights: dict[str, float] = Field(default_factory=lambda: {
        "log": 0.25, "metrics": 0.30, "tracing": 0.20,
        "k8s": 0.15, "code": 0.05, "change": 0.05,
    })

    def compute_weighted_final(self) -> None:
        sources = {
            "log": self.log_confidence, "metrics": self.metrics_confidence,
            "tracing": self.tracing_confidence, "k8s": self.k8s_confidence,
            "code": self.code_confidence, "change": self.change_confidence,
        }
        raw = sum(sources[k] * self.weights[k] for k in sources)
        self.weighted_final = max(0.0, min(1.0, raw + self.critic_adjustment))


class AttestationGate(BaseModel):
    gate_type: Literal["discovery_complete", "pre_remediation", "post_remediation"]
    requires_human: bool = True
    evidence_summary: list[EvidencePin] = []
    proposed_action: Optional[str] = None
    human_decision: Optional[Literal["approve", "reject", "modify"]] = None
    human_notes: Optional[str] = None
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None


class ReasoningStep(BaseModel):
    step_number: int = Field(..., gt=0)
    timestamp: datetime
    decision: str
    reasoning: str
    evidence_considered: list[str] = []
    confidence_at_step: float = Field(default=0.0, ge=0.0, le=1.0)
    alternatives_rejected: list[str] = []


class ReasoningManifest(BaseModel):
    session_id: str
    steps: list[ReasoningStep] = []


class ReActBudget(BaseModel):
    max_llm_calls: int = 10
    max_tool_calls: int = 30
    max_tokens: int = 50000
    timeout_seconds: int = 120
    current_llm_calls: int = 0
    current_tool_calls: int = 0
    current_tokens: int = 0

    def is_exhausted(self) -> bool:
        return (self.current_llm_calls >= self.max_llm_calls or
                self.current_tool_calls >= self.max_tool_calls or
                self.current_tokens >= self.max_tokens)

    def record_llm_call(self, tokens: int = 0) -> None:
        self.current_llm_calls += 1
        self.current_tokens += tokens

    def record_tool_call(self) -> None:
        self.current_tool_calls += 1


class EvidenceNode(BaseModel):
    id: str
    pin: EvidencePin
    node_type: Literal["symptom", "cause", "contributing_factor", "context"]
    temporal_position: datetime


class CausalEdge(BaseModel):
    source_id: str
    target_id: str
    relationship: Literal["causes", "correlates", "precedes", "contributes_to"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str


class EvidenceGraph(BaseModel):
    nodes: list[EvidenceNode] = Field(default_factory=list)
    edges: list[CausalEdge] = Field(default_factory=list)
    root_causes: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    timestamp: datetime
    source: str
    event_type: str
    description: str
    evidence_node_id: str
    severity: Literal["info", "warning", "error", "critical"]


class IncidentTimeline(BaseModel):
    events: list[TimelineEvent] = Field(default_factory=list)


class Hypothesis(BaseModel):
    hypothesis_id: str
    description: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    supporting_node_ids: list[str] = Field(default_factory=list)
    causal_chain: list[str] = Field(default_factory=list)


class ChangeRiskScore(BaseModel):
    change_id: str
    change_type: Literal["code_deploy", "config_change", "infra_change", "dependency_update"]
    risk_score: float = Field(..., ge=0.0, le=1.0)
    temporal_correlation: float = Field(..., ge=0.0, le=1.0)
    scope_overlap: float = Field(..., ge=0.0, le=1.0)
    author: str
    description: str
    files_changed: list[str] = Field(default_factory=list)
    timestamp: Optional[datetime] = None


class ServiceTier(BaseModel):
    service_name: str
    tier: Literal["critical", "standard", "internal"]
    slo_target: float = 99.9
    on_call_team: str = ""
    escalation_channel: str = ""


class BlastRadius(BaseModel):
    primary_service: str
    upstream_affected: list[str] = Field(default_factory=list)
    downstream_affected: list[str] = Field(default_factory=list)
    shared_resources: list[str] = Field(default_factory=list)
    estimated_user_impact: str = ""
    scope: Literal["single_service", "service_group", "namespace", "cluster_wide"]
    business_impact: list[dict[str, str | list[str]]] = Field(default_factory=list)


class SeverityRecommendation(BaseModel):
    recommended_severity: Literal["P1", "P2", "P3", "P4"]
    reasoning: str
    factors: dict[str, str] = Field(default_factory=dict)


class DiagnosticState(BaseModel):
    session_id: str
    incident_id: str = ""
    phase: DiagnosticPhase

    # User input
    service_name: str
    trace_id: Optional[str] = None
    time_window: TimeWindow
    cluster_url: Optional[str] = None
    namespace: Optional[str] = None
    repo_url: Optional[str] = None
    elk_index: Optional[str] = None

    # Multi-repo mapping (service_name -> repo_url)
    repo_map: dict[str, str] = Field(default_factory=dict)

    # Agent results
    log_analysis: Optional[LogAnalysisResult] = None
    metrics_analysis: Optional[MetricsAnalysisResult] = None
    k8s_analysis: Optional[K8sAnalysisResult] = None
    trace_analysis: Optional[TraceAnalysisResult] = None
    code_analysis: Optional[CodeAnalysisResult] = None
    change_analysis: Optional[ChangeAnalysisResult | dict] = None
    fix_result: Optional[FixResult] = None
    campaign: Optional['RemediationCampaign'] = None
    closure_state: Optional["IncidentClosureState"] = None

    # Flow reconstruction
    service_flow: list[ServiceFlowStep | dict] = Field(default_factory=list)
    flow_source: Optional[str] = None
    flow_confidence: int = 0

    # Log agent enrichment
    patient_zero: Optional[PatientZeroInfo | dict] = None
    inferred_dependencies: list[InferredDependencyInfo | dict] = Field(default_factory=list)
    reasoning_chain: list[ReasoningChainStepInfo | dict] = Field(default_factory=list)
    suggested_promql_queries: list[SuggestedPromQLInfo | dict] = Field(default_factory=list)

    # Impact & memory
    blast_radius_result: Optional[BlastRadius] = None
    severity_result: Optional[SeverityRecommendation] = None
    past_incidents: list[PastIncidentMatchInfo | dict] = Field(default_factory=list)

    # Causal forest (War Room v2)
    causal_forest: list[CausalTree] = Field(default_factory=list)

    # Cross-cutting
    all_findings: list[Finding] = Field(default_factory=list)
    all_negative_findings: list[NegativeFinding] = Field(default_factory=list)
    all_breadcrumbs: list[Breadcrumb] = Field(default_factory=list)
    critic_verdicts: list[CriticVerdict] = Field(default_factory=list)

    # Tracking
    token_usage: list[TokenUsage] = Field(default_factory=list)
    task_events: list[TaskEvent] = Field(default_factory=list)

    # Supervisor decisions
    supervisor_reasoning: list[str] = Field(default_factory=list)
    agents_completed: list[str] = Field(default_factory=list)
    agents_pending: list[str] = Field(default_factory=list)
    overall_confidence: int = Field(default=0, ge=0, le=100)


class DiagnosticStateV5(DiagnosticState):
    evidence_pins: list[EvidencePin] = Field(default_factory=list)
    confidence_ledger: ConfidenceLedger = Field(default_factory=ConfidenceLedger)
    attestation_gates: list[AttestationGate] = Field(default_factory=list)
    reasoning_manifest: Optional[ReasoningManifest] = None
    integration_id: Optional[str] = None
    evidence_graph: EvidenceGraph = Field(default_factory=EvidenceGraph)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    incident_timeline: IncidentTimeline = Field(default_factory=IncidentTimeline)
    change_correlations: list[ChangeRiskScore] = Field(default_factory=list)
    blast_radius: Optional[BlastRadius] = None
    severity_recommendation: Optional[SeverityRecommendation] = None

    @model_validator(mode="after")
    def _auto_init_reasoning_manifest(self):
        if self.reasoning_manifest is None:
            self.reasoning_manifest = ReasoningManifest(session_id=self.session_id)
        return self


# Resolve forward references
from src.models.closure_models import IncidentClosureState  # noqa: E402
from src.models.campaign import RemediationCampaign  # noqa: E402
DiagnosticState.model_rebuild()

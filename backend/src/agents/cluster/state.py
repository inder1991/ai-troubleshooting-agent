"""Pydantic models for the Cluster Diagnostic LangGraph state."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class FailureReason(str, Enum):
    TIMEOUT = "TIMEOUT"
    RBAC_DENIED = "RBAC_DENIED"
    API_UNREACHABLE = "API_UNREACHABLE"
    LLM_PARSE_ERROR = "LLM_PARSE_ERROR"
    EXCEPTION = "EXCEPTION"


class DomainStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class TruncationFlags(BaseModel):
    events: bool = False
    events_dropped: int = 0
    pods: bool = False
    pods_dropped: int = 0
    log_lines: bool = False
    log_lines_dropped: int = 0
    metric_points: bool = False
    metric_points_dropped: int = 0
    nodes: bool = False
    nodes_dropped: int = 0
    pvcs: bool = False
    pvcs_dropped: int = 0


class EvidenceSource(BaseModel):
    api_call: str = ""       # "list_pods(namespace='production')"
    resource: str = ""       # "pod/order-service-abc123"
    data_snippet: str = ""   # "status.phase=CrashLoopBackOff, restartCount=45"
    tool_call_id: str = ""   # Links to specific LLM tool call


class DomainAnomaly(BaseModel):
    domain: str
    anomaly_id: str
    description: str
    evidence_ref: str
    severity: str = "medium"
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)


class DomainReport(BaseModel):
    domain: str
    status: DomainStatus = DomainStatus.PENDING
    failure_reason: Optional[FailureReason] = None
    confidence: int = 0
    anomalies: list[DomainAnomaly] = Field(default_factory=list)
    ruled_out: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    truncation_flags: TruncationFlags = Field(default_factory=TruncationFlags)
    data_gathered_before_failure: list[str] = Field(default_factory=list)
    token_usage: int = 0
    duration_ms: int = 0


class CausalLink(BaseModel):
    order: int
    domain: str
    anomaly_id: str
    description: str
    link_type: str
    evidence_ref: str


class CausalChain(BaseModel):
    chain_id: str
    confidence: float
    root_cause: DomainAnomaly
    cascading_effects: list[CausalLink] = Field(default_factory=list)


class BlastRadius(BaseModel):
    summary: str = ""
    affected_namespaces: list[str] = Field(default_factory=list)
    affected_pods: list[str] = Field(default_factory=list)
    affected_nodes: list[str] = Field(default_factory=list)


class RemediationStep(BaseModel):
    command: str = ""
    description: str = ""
    risk_level: str = "medium"
    effort_estimate: str = ""
    rollback: str = ""
    pre_check: str = ""
    verify: str = ""
    expected_output: str = ""
    dry_run: str = ""
    validation_errors: list[str] = Field(default_factory=list)


class ClusterHealthReport(BaseModel):
    diagnostic_id: str
    platform: str = ""
    platform_version: str = ""
    platform_health: str = "UNKNOWN"
    data_completeness: float = 0.0
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    causal_chains: list[CausalChain] = Field(default_factory=list)
    uncorrelated_findings: list[DomainAnomaly] = Field(default_factory=list)
    domain_reports: list[DomainReport] = Field(default_factory=list)
    remediation: dict[str, list] = Field(default_factory=dict)
    execution_metadata: dict[str, Any] = Field(default_factory=dict)
    # Diagnostic intelligence output
    critical_incidents: list[dict] = Field(default_factory=list)
    other_findings: list[dict] = Field(default_factory=list)
    symptom_map: dict[str, str] = Field(default_factory=dict)
    ranked_hypotheses: list[dict] = Field(default_factory=list)
    hypothesis_selection: Optional[dict] = None
    pattern_matches_count: int = 0
    signals_count: int = 0
    diagnostic_graph_node_count: int = 0
    diagnostic_graph_edge_count: int = 0
    issue_lifecycle_summary: dict[str, int] = Field(default_factory=dict)


class DiagnosticScope(BaseModel):
    """Immutable scope that governs what a diagnostic run examines."""
    model_config = {"frozen": True}

    level: Literal["cluster", "namespace", "workload", "component"] = "cluster"
    namespaces: list[str] = Field(default_factory=list)
    workload_key: Optional[str] = None          # "Deployment/my-app"
    domains: list[str] = Field(default_factory=lambda: ["ctrl_plane", "node", "network", "storage", "rbac"])
    include_control_plane: bool = True           # Default ON, user must explicitly uncheck


class ClusterDiagnosticState(BaseModel):
    """LangGraph shared state. Only compact summaries — no raw data, no credentials."""
    diagnostic_id: str
    platform: str = ""
    platform_version: str = ""
    namespaces: list[str] = Field(default_factory=list)
    exclude_namespaces: list[str] = Field(default_factory=list)
    domain_reports: list[DomainReport] = Field(default_factory=list)
    causal_chains: list[CausalChain] = Field(default_factory=list)
    uncorrelated_findings: list[DomainAnomaly] = Field(default_factory=list)
    health_report: Optional[ClusterHealthReport] = None
    phase: str = "pre_flight"
    re_dispatch_count: int = 0
    re_dispatch_domains: list[str] = Field(default_factory=list)
    data_completeness: float = 0.0
    error: Optional[str] = None
    diagnostic_scope: Optional[dict] = None           # DiagnosticScope.model_dump()
    scoped_topology_graph: Optional[dict] = None       # Pruned topology for downstream
    dispatch_domains: list[str] = Field(default_factory=lambda: ["ctrl_plane", "node", "network", "storage", "rbac"])
    scope_coverage: float = 1.0                        # dispatched / total domains


# ---------------------------------------------------------------------------
# Topology-aware correlation, causal firewall & guard-mode models
# ---------------------------------------------------------------------------


class TopologyNode(BaseModel):
    """A single Kubernetes resource node in the dependency topology."""
    kind: str
    name: str
    namespace: Optional[str] = None
    status: Optional[str] = None
    node_name: Optional[str] = None
    labels: dict[str, str] = Field(default_factory=dict)


class TopologyEdge(BaseModel):
    """Directed edge between two topology nodes."""
    from_key: str
    to_key: str
    relation: str


class TopologySnapshot(BaseModel):
    """Point-in-time snapshot of the cluster resource topology."""
    nodes: dict[str, TopologyNode] = Field(default_factory=dict)
    edges: list[TopologyEdge] = Field(default_factory=list)
    built_at: str = ""
    stale: bool = False
    resource_version: str = ""


class ClusterAlert(BaseModel):
    """An alert raised against a specific cluster resource."""
    resource_key: str
    alert_type: str
    severity: str = "medium"
    timestamp: str = ""
    raw_event: dict[str, Any] = Field(default_factory=dict)


class RootCandidate(BaseModel):
    """A hypothesis for the root cause of an issue cluster."""
    resource_key: str
    hypothesis: str
    supporting_signals: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class IssueCluster(BaseModel):
    """A correlated group of alerts with root-cause candidates."""
    cluster_id: str
    alerts: list[ClusterAlert] = Field(default_factory=list)
    root_candidates: list[RootCandidate] = Field(default_factory=list)
    confidence: float = 0.5
    correlation_basis: list[str] = Field(default_factory=list)
    affected_resources: list[str] = Field(default_factory=list)


class BlockedLink(BaseModel):
    """A causal link rejected by the causal firewall."""
    from_resource: str
    to_resource: str
    reason_code: str
    invariant_id: str
    invariant_description: str
    timestamp: str = ""


class CausalAnnotation(BaseModel):
    """Annotation enriching a causal link with confidence and evidence."""
    from_resource: str
    to_resource: str
    rule_id: str
    confidence_hint: float = 0.5
    reason: str = ""
    supporting_evidence: list[str] = Field(default_factory=list)


class CausalSearchSpace(BaseModel):
    """Aggregate view of the causal search space after firewall filtering."""
    valid_links: list[dict[str, Any]] = Field(default_factory=list)
    annotated_links: list[dict[str, Any]] = Field(default_factory=list)
    blocked_links: list[BlockedLink] = Field(default_factory=list)
    total_evaluated: int = 0
    total_blocked: int = 0
    total_annotated: int = 0


class CurrentRisk(BaseModel):
    """A risk observed in the current guard-mode scan."""
    category: str
    severity: str = "warning"
    resource: str = ""
    description: str = ""
    affected_count: int = 0
    issue_cluster_id: Optional[str] = None


class PredictiveRisk(BaseModel):
    """A predicted future risk based on trend analysis."""
    category: str
    severity: str = "warning"
    resource: str = ""
    description: str = ""
    predicted_impact: str = ""
    time_horizon: str = ""
    trend_data: list[dict[str, Any]] = Field(default_factory=list)


class ScanDelta(BaseModel):
    """Diff between the current and previous guard-mode scans."""
    new_risks: list[str] = Field(default_factory=list)
    resolved_risks: list[str] = Field(default_factory=list)
    worsened: list[str] = Field(default_factory=list)
    improved: list[str] = Field(default_factory=list)
    previous_scan_id: Optional[str] = None
    previous_scanned_at: Optional[str] = None


class GuardScanResult(BaseModel):
    """Full result of a guard-mode health scan."""
    scan_id: str = ""
    scanned_at: str = ""
    platform: str = ""
    platform_version: str = ""
    current_risks: list[CurrentRisk] = Field(default_factory=list)
    predictive_risks: list[PredictiveRisk] = Field(default_factory=list)
    delta: ScanDelta = Field(default_factory=ScanDelta)
    overall_health: str = "UNKNOWN"
    risk_score: float = 0.0


# ---------------------------------------------------------------------------
# Diagnostic Intelligence Engine models
# ---------------------------------------------------------------------------


class NormalizedSignal(BaseModel):
    """Canonical signal extracted from domain report data."""
    signal_id: str = ""
    signal_type: str = ""             # "CRASHLOOP", "NODE_DISK_PRESSURE", etc.
    resource_key: str = ""            # "pod/production/payments-api-abc123"
    source_domain: str = ""           # "node", "network", etc.
    raw_value: Any = None
    reliability: float = 0.5          # Signal weight (1.0=node_condition, 0.4=log)
    timestamp: str = ""
    namespace: str = ""


class FailurePattern(BaseModel):
    """Known failure pattern for deterministic matching."""
    pattern_id: str
    name: str = ""
    version: str = "1.0"
    scope: str = "resource"           # "resource" | "namespace" | "cluster"
    priority: int = 5                 # Higher wins on conflict
    conditions: list[dict] = Field(default_factory=list)
    probable_causes: list[str] = Field(default_factory=list)
    known_fixes: list[str] = Field(default_factory=list)
    severity: str = "medium"
    confidence_boost: float = 0.2


class PatternMatch(BaseModel):
    """Result of matching a failure pattern against signals."""
    pattern_id: str
    name: str = ""
    matched_conditions: list[str] = Field(default_factory=list)
    affected_resources: list[str] = Field(default_factory=list)
    confidence_boost: float = 0.0
    severity: str = "medium"
    scope: str = "resource"
    probable_causes: list[str] = Field(default_factory=list)
    known_fixes: list[str] = Field(default_factory=list)


class DiagnosticNode(BaseModel):
    """A node in the diagnostic evidence graph."""
    node_id: str
    node_type: str = "signal"         # "signal" | "resource" | "pattern"
    resource_key: str = ""
    signal_type: str = ""
    severity: str = "medium"
    reliability: float = 0.5
    first_seen: str = ""
    last_seen: str = ""
    event_age_seconds: int = 0
    restart_velocity: float = 0.0
    resource_age_seconds: int = 0
    event_count_recent: int = 0       # Last 5 min
    event_count_baseline: int = 0     # Last 60 min
    namespace: str = ""


class DiagnosticEdge(BaseModel):
    """A typed edge in the diagnostic evidence graph."""
    from_id: str
    to_id: str
    edge_type: str = ""               # "CAUSES" | "DEPENDS_ON" | "OBSERVED_AFTER" | "AFFECTS" | "SYMPTOM_OF"
    confidence: float = 0.5
    evidence: str = ""


class DiagnosticGraph(BaseModel):
    """Cross-domain evidence graph built from signals and topology."""
    nodes: dict[str, DiagnosticNode] = Field(default_factory=dict)
    edges: list[DiagnosticEdge] = Field(default_factory=list)


class IssueState(str, Enum):
    """Issue lifecycle states ordered by operator relevance."""
    ACTIVE_DISRUPTION = "ACTIVE_DISRUPTION"
    WORSENING = "WORSENING"
    NEW = "NEW"
    EXISTING = "EXISTING"
    LONG_STANDING = "LONG_STANDING"
    INTERMITTENT = "INTERMITTENT"
    SYMPTOM = "SYMPTOM"
    RESOLVED = "RESOLVED"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class LifecycleThresholds(BaseModel):
    """Tunable thresholds for issue lifecycle classification."""
    active_event_age_seconds: int = 120
    active_restart_velocity: float = 1.0
    active_blast_radius_min: int = 2
    worsening_rate_multiplier: float = 3.0
    new_first_seen_seconds: int = 900
    long_standing_age_seconds: int = 86400
    flap_count_threshold: int = 3
    intermittent_window_seconds: int = 600


class DiagnosticIssue(BaseModel):
    """A classified issue with lifecycle state and priority."""
    issue_id: str
    state: IssueState = IssueState.EXISTING
    priority_score: float = 0.0
    first_seen: str = ""
    last_state_change: str = ""
    state_duration_seconds: int = 0
    event_count_recent: int = 0
    event_count_baseline: int = 0
    restart_velocity: float = 0.0
    severity_trend: str = "stable"    # "escalating" | "stable" | "de-escalating"
    is_root_cause: bool = False
    is_symptom: bool = False
    root_cause_id: str = ""
    blast_radius: int = 0
    affected_resources: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    pattern_matches: list[str] = Field(default_factory=list)
    anomaly_ids: list[str] = Field(default_factory=list)
    description: str = ""
    severity: str = "medium"


class WeightedEvidence(BaseModel):
    """Evidence with signal reliability weight."""
    signal_id: str = ""
    signal_type: str = ""
    resource_key: str = ""
    weight: float = 0.5
    reliability: float = 0.5
    relevance: str = ""


class Hypothesis(BaseModel):
    """A root cause hypothesis with weighted evidence."""
    hypothesis_id: str
    cause: str = ""
    cause_type: str = ""
    source: str = "pattern"           # "pattern" | "graph_traversal" | "signal_correlation"
    supporting_evidence: list[WeightedEvidence] = Field(default_factory=list)
    contradicting_evidence: list[WeightedEvidence] = Field(default_factory=list)
    evidence_score: float = 0.0
    contradiction_penalty: float = 0.0
    confidence: float = 0.0
    affected_issues: list[str] = Field(default_factory=list)
    explains_count: int = 0
    blast_radius: int = 0
    issue_state: Optional[str] = None
    root_resource: str = ""
    causal_chain: list[str] = Field(default_factory=list)
    depth: int = 0
    evidence_ids: list[str] = Field(default_factory=list)


class SimulationResult(BaseModel):
    """Result of simulating a remediation command's cluster impact."""
    action: str = ""
    target: str = ""
    impact: str = ""
    side_effects: list[str] = Field(default_factory=list)
    recovery: str = ""


class SolutionValidation(BaseModel):
    """Validation result for a remediation step."""
    risk_level: str = "safe"          # "safe" | "caution" | "dangerous" | "forbidden"
    warnings: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    blocked: bool = False
    block_reason: str = ""
    simulation: Optional[SimulationResult] = None
    remediation_confidence: float = 0.0
    confidence_label: str = ""


# ---------------------------------------------------------------------------
# Cluster Recommendations & Cost Optimization models
# ---------------------------------------------------------------------------


class ProactiveFinding(BaseModel):
    """A finding from proactive analysis (cert expiry, deprecated API, etc.)."""
    finding_id: str = ""
    check_type: str = ""          # "cert_expiry" | "deprecated_api" | "image_stale" | ...
    severity: str = "medium"
    lifecycle_state: str = "NEW"  # Reuses IssueState values

    title: str = ""
    description: str = ""
    affected_resources: list[str] = Field(default_factory=list)
    affected_workloads: list[str] = Field(default_factory=list)

    days_until_impact: int = -1   # -1 = already impacting
    estimated_savings_usd: float = 0.0

    recommendation: str = ""
    commands: list[str] = Field(default_factory=list)
    dry_run_command: str = ""
    rollback_command: str = ""

    confidence: float = 0.0
    source: str = "proactive"     # "proactive" | "cost" | "workload" | "slo"
    cloud_provider: str = ""


class CostRecommendation(BaseModel):
    """Cost optimization recommendation for a cluster."""
    recommendation_id: str = ""
    scope: str = "cluster"        # "cluster" | "namespace" | "workload"

    current_instance_types: list[dict] = Field(default_factory=list)
    current_monthly_cost: float = 0.0

    recommended_instance_types: list[dict] = Field(default_factory=list)
    projected_monthly_cost: float = 0.0
    projected_savings_usd: float = 0.0
    projected_savings_pct: float = 0.0

    idle_capacity_pct: float = 0.0
    affected_workloads: list[str] = Field(default_factory=list)
    constraints_respected: list[str] = Field(default_factory=list)
    risk_level: str = "safe"


class WorkloadRecommendation(BaseModel):
    """Right-sizing recommendation for a single workload."""
    recommendation_id: str = ""
    workload: str = ""            # "deployment/production/api-gateway"
    namespace: str = ""

    current_cpu_request: str = ""
    current_cpu_limit: str = ""
    current_memory_request: str = ""
    current_memory_limit: str = ""

    recommended_cpu_request: str = ""
    recommended_memory_request: str = ""

    p95_cpu_usage: str = ""
    p95_memory_usage: str = ""
    observation_window: str = "7d"

    cpu_reduction_pct: float = 0.0
    memory_reduction_pct: float = 0.0

    recommended_hpa: Optional[dict] = None
    recommended_vpa: Optional[dict] = None

    risk_level: str = "safe"
    throttling_risk: bool = False


class ScoredRecommendation(BaseModel):
    """A scored, prioritized recommendation from any source."""
    recommendation_id: str = ""
    category: str = "known_issue"  # "critical_risk" | "optimization" | "security" | "known_issue"
    score: float = 0.0             # 0-100

    title: str = ""
    description: str = ""
    severity: str = "medium"
    source: str = ""               # "proactive" | "cost" | "workload" | "slo"

    affected_resources: list[str] = Field(default_factory=list)
    affected_workloads: list[str] = Field(default_factory=list)

    commands: list[str] = Field(default_factory=list)
    dry_run_command: str = ""
    rollback_command: str = ""
    yaml_diff: Optional[str] = None

    days_until_impact: int = -1
    estimated_savings_usd: float = 0.0
    risk_level: str = "safe"
    confidence: float = 0.0


class ClusterCostSummary(BaseModel):
    """Cost summary for a cluster."""
    cluster_id: str = ""
    provider: str = ""
    node_count: int = 0
    pod_count: int = 0
    current_monthly_cost: float = 0.0
    projected_monthly_cost: float = 0.0
    projected_savings_usd: float = 0.0
    idle_cpu_pct: float = 0.0
    idle_memory_pct: float = 0.0
    instance_breakdown: list[dict] = Field(default_factory=list)
    namespace_costs: list[dict] = Field(default_factory=list)


class ClusterRecommendationSnapshot(BaseModel):
    """Full recommendation snapshot for a cluster, persisted for the registry."""
    cluster_id: str = ""
    cluster_name: str = ""
    provider: str = ""
    scanned_at: str = ""
    proactive_findings: list[ProactiveFinding] = Field(default_factory=list)
    cost_summary: Optional[ClusterCostSummary] = None
    workload_recommendations: list[WorkloadRecommendation] = Field(default_factory=list)
    scored_recommendations: list[ScoredRecommendation] = Field(default_factory=list)
    total_savings_usd: float = 0.0
    critical_count: int = 0
    optimization_count: int = 0
    security_count: int = 0

"""Pydantic models for the Cluster Diagnostic LangGraph state."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
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


class TruncationFlags(BaseModel):
    events: bool = False
    pods: bool = False
    log_lines: bool = False
    metric_points: bool = False
    nodes: bool = False
    pvcs: bool = False


class DomainAnomaly(BaseModel):
    domain: str
    anomaly_id: str
    description: str
    evidence_ref: str
    severity: str = "medium"


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
    affected_namespaces: int = 0
    affected_pods: int = 0
    affected_nodes: int = 0


class RemediationStep(BaseModel):
    command: str = ""
    description: str = ""
    risk_level: str = "medium"
    effort_estimate: str = ""


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

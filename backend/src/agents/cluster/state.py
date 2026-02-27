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

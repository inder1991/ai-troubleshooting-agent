"""Pydantic models for database diagnostics + SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    """Declarative base for hardening-track ORM models (outbox, audit, priors, eval).

    NOTE: ORM columns below use bare ``mapped_column(...)`` rather than the modern
    ``Mapped[...]`` annotated form because Python 3.14 + SQLAlchemy 2.0.36 +
    ``from __future__ import annotations`` (above) interact badly: typed
    ``Mapped[Optional[datetime]]`` fails inside ``sqlalchemy/util/typing.py``
    with ``TypeError: descriptor '__getitem__' requires a 'typing.Union' object``.
    Workaround until SQLAlchemy ships a fix: stay on ``mapped_column()`` only,
    or drop the ``__future__`` import from THIS module specifically.
    """


class Outbox(Base):
    __tablename__ = "investigation_outbox"
    __table_args__ = (
        sa.UniqueConstraint("run_id", "seq", name="uq_outbox_run_seq"),
        sa.Index(
            "ix_outbox_unrelayed",
            "relayed_at",
            postgresql_where=sa.text("relayed_at IS NULL"),
        ),
    )

    id = mapped_column(sa.BigInteger, primary_key=True)
    run_id = mapped_column(sa.String(64), nullable=False, index=True)
    seq = mapped_column(sa.BigInteger, nullable=False)
    kind = mapped_column(sa.String(64), nullable=False)
    # ``sa.JSON`` is portable across backends. Switch to ``JSONB`` only if/when
    # we need indexed predicates on payload subfields (currently the relay reads
    # rows whole and forwards — no predicate pushdown).
    payload = mapped_column(sa.JSON, nullable=False)
    created_at = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    relayed_at = mapped_column(sa.DateTime(timezone=True), nullable=True)


class DagSnapshot(Base):
    """One-row-per-run snapshot of the VirtualDag, written transactionally
    alongside outbox events by ``OutboxWriter`` (see ``workflows/outbox.py``)."""

    __tablename__ = "investigation_dag_snapshot"

    run_id = mapped_column(sa.String(64), primary_key=True)
    payload = mapped_column(sa.JSON, nullable=False)
    schema_version = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    updated_at = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


# ── Connection Profile ──


class DBProfile(BaseModel):
    id: str
    name: str
    engine: Literal["postgresql", "mongodb", "mysql", "oracle"]
    host: str
    port: int
    database: str
    username: str
    password: str  # stored encrypted at rest via profile_store
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tags: dict[str, str] = {}


# ── Snapshots ──


class PerfSnapshot(BaseModel):
    connections_active: int = 0
    connections_idle: int = 0
    connections_max: int = 0
    cache_hit_ratio: float = 0.0
    transactions_per_sec: float = 0.0
    deadlocks: int = 0
    uptime_seconds: int = 0


class ActiveQuery(BaseModel):
    pid: int
    query: str
    duration_ms: float
    state: str = "active"
    user: str = ""
    database: str = ""
    waiting: bool = False


class ReplicaInfo(BaseModel):
    name: str = ""
    state: str = ""
    lag_bytes: int = 0
    lag_seconds: float = 0.0


class ReplicationSnapshot(BaseModel):
    is_replica: bool = False
    replicas: list[ReplicaInfo] = []
    replication_lag_bytes: int = 0
    replication_lag_seconds: float = 0.0


class SchemaSnapshot(BaseModel):
    tables: list[dict] = []
    indexes: list[dict] = []
    total_size_bytes: int = 0


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    default: Optional[str] = None
    is_pk: bool = False


class IndexInfo(BaseModel):
    name: str
    columns: list[str] = []
    unique: bool = False
    size_bytes: int = 0
    scan_count: int = 0


class TableDetail(BaseModel):
    name: str
    schema_name: str = "public"
    columns: list[ColumnInfo] = []
    indexes: list[IndexInfo] = []
    row_estimate: int = 0
    total_size_bytes: int = 0
    bloat_ratio: float = 0.0


class ConnectionPoolSnapshot(BaseModel):
    active: int = 0
    idle: int = 0
    waiting: int = 0
    max_connections: int = 0


class QueryPlanNode(BaseModel):
    node_type: str
    relation: str = ""
    startup_cost: float = 0.0
    total_cost: float = 0.0
    rows: int = 0
    width: int = 0
    actual_time_ms: float = 0.0
    children: list[QueryPlanNode] = []


class QueryResult(BaseModel):
    query: str
    plan: Optional[QueryPlanNode] = None
    execution_time_ms: float = 0.0
    rows_returned: int = 0
    error: Optional[str] = None


# ── Diagnostic Run & Findings ──


class DBFinding(BaseModel):
    finding_id: str
    category: Literal[
        "query_performance", "replication", "connections",
        "storage", "schema", "locks", "memory",
    ]
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: float = 0.0
    title: str
    detail: str
    evidence: list[str] = []
    recommendation: Optional[str] = None
    remediation_available: bool = False


class DiagnosticRun(BaseModel):
    run_id: str
    profile_id: str
    status: Literal["running", "completed", "failed"] = "running"
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    findings: list[DBFinding] = []
    summary: str = ""


# ── Remediation Models ──


class RemediationPlan(BaseModel):
    plan_id: str
    profile_id: str
    finding_id: Optional[str] = None
    action: str
    params: dict = {}
    sql_preview: str
    impact_assessment: str = ""
    rollback_sql: Optional[str] = None
    requires_downtime: bool = False
    status: str = "pending"
    created_at: str
    approved_at: Optional[str] = None
    executed_at: Optional[str] = None
    completed_at: Optional[str] = None
    result_summary: Optional[str] = None
    before_state: Optional[dict] = None
    after_state: Optional[dict] = None


class AuditLogEntry(BaseModel):
    entry_id: str
    plan_id: str
    profile_id: str
    action: str
    sql_executed: str
    status: str
    before_state: dict = {}
    after_state: dict = {}
    error: Optional[str] = None
    timestamp: str


class ConfigRecommendation(BaseModel):
    param: str
    current_value: str
    recommended_value: str
    reason: str
    requires_restart: bool = False


# --- V2 Models for AI-Powered Database Diagnostics ---

class EvidenceSnippet(BaseModel):
    id: str
    summary: str
    artifact_id: str


class EvidenceSource(BaseModel):
    """Links a finding to the specific tool call that produced the evidence."""
    tool_call_id: str = ""
    tool_name: str = ""
    data_snippet: str = ""
    truncated: bool = False


class DBFindingV2(BaseModel):
    finding_id: str
    agent: str
    category: Literal[
        "slow_query", "lock", "replication", "connections",
        "storage", "schema", "index_candidate", "memory",
        "configuration", "deadlock",
    ]
    title: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence_raw: float
    confidence_calibrated: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    detail: str
    evidence_ids: list[str] = []
    evidence_snippets: list[EvidenceSnippet] = []
    affected_entities: dict = {}
    recommendation: str = ""
    remediation_available: bool = False
    remediation_plan_id: Optional[str] = None
    rule_check: str = ""
    meta: dict = {}
    evidence_sources: list[EvidenceSource] = []    # Provenance: which tool calls support this
    related_findings: list[str] = []               # Cross-agent correlation: finding IDs
    remediation_sql: str = ""                      # Context-aware SQL command
    remediation_warning: str = ""                  # Risk warning for the SQL


class PlanStep(BaseModel):
    step_id: str
    type: str
    description: str
    command: str
    run_target: str
    estimated_time_minutes: Optional[int] = None
    checks: list[dict] = []


class RemediationPlanV2(BaseModel):
    plan_id: str
    profile_id: str
    created_by: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    summary: str
    scope: dict = {}
    steps: list[PlanStep] = []
    prechecks: list[dict] = []
    required_approvals: list[dict] = []
    approval_status: str = "pending"
    approvals: list[dict] = []
    immutable_hash: str = ""
    policy_tags: list[str] = []
    estimated_risk: Literal["low", "medium", "high", "critical"] = "medium"
    status: str = "created"
    finding_id: Optional[str] = None

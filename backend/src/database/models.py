"""Pydantic models for database diagnostics."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


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

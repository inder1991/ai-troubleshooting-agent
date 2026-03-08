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

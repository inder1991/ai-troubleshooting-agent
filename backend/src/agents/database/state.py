"""TypedDict state for DB diagnostic LangGraph graph."""
from __future__ import annotations

from typing import Optional, TypedDict


class DBDiagnosticState(TypedDict, total=False):
    run_id: str
    profile_id: str
    engine: str
    status: str  # "running", "completed", "failed"
    error: Optional[str]
    # Connection validation
    connected: bool
    health_latency_ms: float
    # Symptom classification
    symptoms: list[str]
    dispatched_agents: list[str]
    # Adapter reference (injected at runtime)
    _adapter: object
    _run_store: object
    # Agent outputs
    findings: list[dict]
    summary: str

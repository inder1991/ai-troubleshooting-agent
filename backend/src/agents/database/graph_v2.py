"""LangGraph V2 for AI-powered database diagnostics.

Replaces heuristic graph.py with LLM-powered agents using a tool-first
pattern. Haiku for extraction agents, Opus for synthesizer/dossier.
"""

import asyncio
import logging
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)


class DBDiagnosticStateV2(TypedDict, total=False):
    # Session identity
    run_id: str
    session_id: str
    profile_id: str
    profile_name: str
    host: str
    port: int
    database: str
    engine: str

    # Investigation config
    investigation_mode: str  # "standalone" | "contextual"
    sampling_mode: str  # "light" | "standard" | "deep"
    focus: list[str]
    table_filter: list[str]
    include_explain_plans: bool
    parent_session_id: str
    app_context: dict  # Findings from parent app session

    # Runtime injections
    _adapter: object
    _evidence_store: object
    _job_queue: object
    _emitter: object

    # Execution state
    status: str  # "running" | "completed" | "failed"
    connected: bool
    health_latency_ms: float
    error: Optional[str]

    # Results
    findings: list[dict]
    query_findings: list[dict]
    health_findings: list[dict]
    schema_findings: list[dict]
    summary: str
    root_cause: str
    needs_human_review: bool
    dossier: dict


# --- Node: Connection Validator (no LLM) ---

async def connection_validator(state: DBDiagnosticStateV2) -> dict:
    adapter = state["_adapter"]
    emitter = state.get("_emitter")

    if emitter:
        await emitter.emit("connection_validator", "started", "Checking database connectivity")

    try:
        health = await adapter.health_check()
    except Exception as e:
        logger.error("Connection validation failed: %s", e)
        if emitter:
            await emitter.emit("connection_validator", "error", f"Connection failed: {e}")
        return {"connected": False, "status": "failed", "error": str(e)}

    if health.status == "unreachable" or health.status == "degraded":
        if emitter:
            await emitter.emit("connection_validator", "error",
                              f"Database unreachable: {health.error}")
        return {"connected": False, "status": "failed", "error": health.error}

    if emitter:
        await emitter.emit("connection_validator", "success",
                          f"Connected ({health.latency_ms}ms)")

    return {
        "connected": True,
        "health_latency_ms": getattr(health, "latency_ms", 0),
    }


def should_continue(state: DBDiagnosticStateV2) -> str:
    if state.get("connected"):
        return "context_loader"
    return END


# --- Node: Context Loader (no LLM) ---

async def context_loader(state: DBDiagnosticStateV2) -> dict:
    """Load parent app session findings if in contextual mode."""
    emitter = state.get("_emitter")
    parent_id = state.get("parent_session_id")

    if state.get("investigation_mode") != "contextual" or not parent_id:
        if emitter:
            await emitter.emit("context_loader", "success", "Standalone mode — no app context")
        return {"app_context": {}, "investigation_mode": "standalone"}

    if emitter:
        await emitter.emit("context_loader", "started",
                          f"Loading context from app session {parent_id}")

    # TODO: Fetch findings from parent session via internal API
    # For now, return empty context
    return {"app_context": {"parent_session_id": parent_id}}


# --- Node: Query Analyst (LLM + tools) ---

async def query_analyst(state: DBDiagnosticStateV2) -> dict:
    """Analyze query performance using LLM with read-only PG tools."""
    emitter = state.get("_emitter")
    if emitter:
        await emitter.emit("query_analyst", "started", "Analyzing query performance")

    # Phase 1: Use heuristic analysis (same as v1 but with evidence storage)
    # Phase 2: Replace with LLM tool-calling agent (Haiku)
    adapter = state["_adapter"]
    findings = []

    try:
        queries = await adapter.get_active_queries()
        slow = [q for q in queries if q.duration_ms > 5000]

        for q in slow:
            severity = "critical" if q.duration_ms > 30000 else "high" if q.duration_ms > 10000 else "medium"
            findings.append({
                "finding_id": f"f-qa-{q.pid}",
                "agent": "query_analyst",
                "category": "slow_query",
                "title": f"Slow query (pid={q.pid}, {q.duration_ms}ms)",
                "severity": severity,
                "confidence_raw": 0.9,
                "confidence_calibrated": 0.85,
                "detail": f"Query running for {q.duration_ms}ms: {q.query[:200]}",
                "evidence_ids": [],
                "recommendation": "Review query plan and consider adding indexes",
                "remediation_available": True,
                "rule_check": f"duration_ms={q.duration_ms} > 5000",
            })
    except Exception as e:
        logger.error("Query analyst failed: %s", e)
        if emitter:
            await emitter.emit("query_analyst", "error", str(e))

    if emitter:
        await emitter.emit("query_analyst", "success", f"Found {len(findings)} query issues")

    return {"query_findings": findings}


# --- Node: Health Analyst (LLM + tools) ---

async def health_analyst(state: DBDiagnosticStateV2) -> dict:
    """Analyze database health metrics."""
    emitter = state.get("_emitter")
    if emitter:
        await emitter.emit("health_analyst", "started", "Analyzing database health")

    adapter = state["_adapter"]
    engine = state.get("engine", "postgresql")
    is_mongo = engine == "mongodb"
    findings = []

    try:
        pool = await adapter.get_connection_pool()
        if pool.max_connections and pool.active / pool.max_connections > 0.8:
            utilization = round(pool.active / pool.max_connections * 100, 1)
            conn_rec = (
                "Review application connection pooling and increase maxPoolSize"
                if is_mongo
                else "Increase max_connections or reduce connection leaks"
            )
            findings.append({
                "finding_id": "f-ha-conn-sat",
                "agent": "health_analyst",
                "category": "connections",
                "title": f"Connection pool saturation ({utilization}%)",
                "severity": "critical" if utilization > 95 else "high",
                "confidence_raw": 0.95,
                "confidence_calibrated": 0.90,
                "detail": f"Active: {pool.active}, Max: {pool.max_connections}",
                "evidence_ids": [],
                "recommendation": conn_rec,
                "remediation_available": True,
                "rule_check": f"utilization={utilization}% > 80%",
            })

        perf = await adapter.get_performance_stats()
        if perf.cache_hit_ratio < 0.9:
            cache_rec = (
                "Increase WiredTiger cacheSizeGB or review query access patterns"
                if is_mongo
                else "Increase shared_buffers or review query access patterns"
            )
            findings.append({
                "finding_id": "f-ha-cache",
                "agent": "health_analyst",
                "category": "memory",
                "title": f"Low cache hit ratio ({perf.cache_hit_ratio:.2%})",
                "severity": "medium",
                "confidence_raw": 0.85,
                "confidence_calibrated": 0.80,
                "detail": f"Cache hit ratio is {perf.cache_hit_ratio:.2%}, below 90% threshold",
                "evidence_ids": [],
                "recommendation": cache_rec,
                "remediation_available": True,
                "rule_check": f"cache_hit_ratio={perf.cache_hit_ratio:.4f} < 0.9",
            })

        if perf.deadlocks > 0:
            deadlock_rec = (
                "Review write concern settings and document access patterns"
                if is_mongo
                else "Review lock ordering and transaction isolation"
            )
            findings.append({
                "finding_id": "f-ha-deadlock",
                "agent": "health_analyst",
                "category": "deadlock",
                "title": f"{perf.deadlocks} deadlocks detected",
                "severity": "high",
                "confidence_raw": 0.80,
                "confidence_calibrated": 0.75,
                "detail": f"Deadlock count: {perf.deadlocks}",
                "evidence_ids": [],
                "recommendation": deadlock_rec,
                "remediation_available": False,
                "rule_check": f"deadlocks={perf.deadlocks} > 0",
            })
    except Exception as e:
        logger.error("Health analyst failed: %s", e)
        if emitter:
            await emitter.emit("health_analyst", "error", str(e))

    if emitter:
        await emitter.emit("health_analyst", "success", f"Found {len(findings)} health issues")

    return {"health_findings": findings}


# --- Node: Schema Analyst (LLM + tools) ---

async def schema_analyst(state: DBDiagnosticStateV2) -> dict:
    """Analyze schema health and index usage."""
    emitter = state.get("_emitter")
    if emitter:
        await emitter.emit("schema_analyst", "started", "Analyzing schema health")

    # Placeholder — will be enhanced with LLM tool-calling in Phase 2
    findings = []

    if emitter:
        await emitter.emit("schema_analyst", "success", f"Found {len(findings)} schema issues")

    return {"schema_findings": findings}


# --- Node: Synthesizer (Sonnet/Opus) ---

async def synthesizer(state: DBDiagnosticStateV2) -> dict:
    """Combine all findings, identify root cause, generate summary."""
    emitter = state.get("_emitter")
    if emitter:
        await emitter.emit("synthesizer", "started", "Synthesizing root cause analysis")

    all_findings = (
        state.get("query_findings", [])
        + state.get("health_findings", [])
        + state.get("schema_findings", [])
    )

    # Sort by severity priority * confidence
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    all_findings.sort(
        key=lambda f: severity_order.get(f.get("severity", "info"), 0)
        * f.get("confidence_raw", 0),
        reverse=True,
    )

    needs_review = any(f.get("confidence_calibrated", 1.0) < 0.7 for f in all_findings)

    root_cause = all_findings[0]["title"] if all_findings else "No issues detected"
    finding_count = len(all_findings)
    critical_count = sum(1 for f in all_findings if f.get("severity") == "critical")

    summary = (
        f"Investigated {state.get('profile_name', 'unknown')} database. "
        f"Found {finding_count} issue(s), {critical_count} critical. "
        f"Primary concern: {root_cause}."
    )

    if emitter:
        await emitter.emit("synthesizer", "success", summary)
        if needs_review:
            await emitter.emit("synthesizer", "warning",
                              "Low confidence findings detected — human review recommended")

    return {
        "findings": all_findings,
        "summary": summary,
        "root_cause": root_cause,
        "needs_human_review": needs_review,
        "status": "completed",
    }


# --- Graph Builder ---

def build_db_diagnostic_graph_v2():
    graph = StateGraph(DBDiagnosticStateV2)

    graph.add_node("connection_validator", connection_validator)
    graph.add_node("context_loader", context_loader)
    graph.add_node("query_analyst", query_analyst)
    graph.add_node("health_analyst", health_analyst)
    graph.add_node("schema_analyst", schema_analyst)
    graph.add_node("synthesizer", synthesizer)

    graph.set_entry_point("connection_validator")

    graph.add_conditional_edges(
        "connection_validator",
        should_continue,
        {"context_loader": "context_loader", END: END},
    )

    # After context_loader, dispatch all analysts in parallel
    graph.add_edge("context_loader", "query_analyst")
    graph.add_edge("context_loader", "health_analyst")
    graph.add_edge("context_loader", "schema_analyst")

    # All analysts feed into synthesizer
    graph.add_edge("query_analyst", "synthesizer")
    graph.add_edge("health_analyst", "synthesizer")
    graph.add_edge("schema_analyst", "synthesizer")

    graph.add_edge("synthesizer", END)

    return graph.compile()

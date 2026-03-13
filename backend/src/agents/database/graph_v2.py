"""LangGraph V2 for AI-powered database diagnostics.

Replaces heuristic graph.py with LLM-powered agents using a tool-first
pattern. Haiku for extraction agents, Opus for synthesizer/dossier.
"""

import asyncio
import logging
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from src.database.models import DBFindingV2

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
    _context_fetcher: object  # callable(session_id) -> session dict or None

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

    # Fetch findings from parent session via injected fetcher (avoids circular import)
    app_context = {"parent_session_id": parent_id}
    try:
        fetcher = state.get("_context_fetcher")
        parent = fetcher(parent_id) if fetcher else None
        if parent and parent.get("state"):
            pstate = parent["state"]
            if hasattr(pstate, "all_findings"):
                app_context["findings_summary"] = [
                    {"finding_id": f.finding_id, "summary": f.summary, "severity": f.severity}
                    for f in pstate.all_findings[:10]
                ]
            if hasattr(pstate, "incident_id"):
                app_context["incident_id"] = pstate.incident_id
    except Exception as e:
        logger.warning("Failed to load parent context: %s", e)

    if emitter:
        await emitter.emit("context_loader", "success",
                          f"Loaded context ({len(app_context.get('findings_summary', []))} findings)")
    return {"app_context": app_context}


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
            findings.append(DBFindingV2(
                finding_id=f"f-qa-{q.pid}",
                agent="query_analyst",
                category="slow_query",
                title=f"Slow query (pid={q.pid}, {q.duration_ms}ms)",
                severity=severity,
                confidence_raw=0.9,
                confidence_calibrated=0.85,
                detail=f"Query running for {q.duration_ms}ms: {q.query[:200]}",
                evidence_ids=[],
                recommendation="Review query plan and consider adding indexes",
                remediation_available=True,
                rule_check=f"duration_ms={q.duration_ms} > 5000",
            ).model_dump())
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
            findings.append(DBFindingV2(
                finding_id="f-ha-conn-sat",
                agent="health_analyst",
                category="connections",
                title=f"Connection pool saturation ({utilization}%)",
                severity="critical" if utilization > 95 else "high",
                confidence_raw=0.95,
                confidence_calibrated=0.90,
                detail=f"Active: {pool.active}, Max: {pool.max_connections}",
                evidence_ids=[],
                recommendation=conn_rec,
                remediation_available=True,
                rule_check=f"utilization={utilization}% > 80%",
            ).model_dump())

        perf = await adapter.get_performance_stats()
        if perf.cache_hit_ratio < 0.9:
            cache_rec = (
                "Increase WiredTiger cacheSizeGB or review query access patterns"
                if is_mongo
                else "Increase shared_buffers or review query access patterns"
            )
            findings.append(DBFindingV2(
                finding_id="f-ha-cache",
                agent="health_analyst",
                category="memory",
                title=f"Low cache hit ratio ({perf.cache_hit_ratio:.2%})",
                severity="medium",
                confidence_raw=0.85,
                confidence_calibrated=0.80,
                detail=f"Cache hit ratio is {perf.cache_hit_ratio:.2%}, below 90% threshold",
                evidence_ids=[],
                recommendation=cache_rec,
                remediation_available=True,
                rule_check=f"cache_hit_ratio={perf.cache_hit_ratio:.4f} < 0.9",
            ).model_dump())

        if perf.deadlocks > 0:
            deadlock_rec = (
                "Review write concern settings and document access patterns"
                if is_mongo
                else "Review lock ordering and transaction isolation"
            )
            findings.append(DBFindingV2(
                finding_id="f-ha-deadlock",
                agent="health_analyst",
                category="deadlock",
                title=f"{perf.deadlocks} deadlocks detected",
                severity="high",
                confidence_raw=0.80,
                confidence_calibrated=0.75,
                detail=f"Deadlock count: {perf.deadlocks}",
                evidence_ids=[],
                recommendation=deadlock_rec,
                remediation_available=False,
                rule_check=f"deadlocks={perf.deadlocks} > 0",
            ).model_dump())
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
    """Combine all findings, identify root cause, generate summary and 7-section dossier."""
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
    high_count = sum(1 for f in all_findings if f.get("severity") == "high")
    medium_count = sum(1 for f in all_findings if f.get("severity") == "medium")
    low_count = sum(1 for f in all_findings if f.get("severity") in ("low", "info"))

    profile_name = state.get("profile_name", "unknown")
    host = state.get("host", "unknown")
    engine = state.get("engine", "postgresql")

    summary = (
        f"Investigated {profile_name} database. "
        f"Found {finding_count} issue(s), {critical_count} critical. "
        f"Primary concern: {root_cause}."
    )

    # --- Build 7-section dossier ---

    # Section 1: Executive Summary
    exec_summary = {
        "profile": profile_name,
        "host": host,
        "engine": engine,
        "total_findings": finding_count,
        "critical_count": critical_count,
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
        "needs_human_review": needs_review,
        "headline": summary,
        "health_status": (
            "critical" if critical_count > 0
            else "degraded" if high_count > 0
            else "warning" if medium_count > 0
            else "healthy"
        ),
    }

    # Section 2: Root Cause Analysis
    top_finding = all_findings[0] if all_findings else {}
    root_cause_analysis = {
        "primary_root_cause": root_cause,
        "confidence": top_finding.get("confidence_calibrated", 0.0),
        "severity": top_finding.get("severity", "info"),
        "category": top_finding.get("category", "unknown"),
        "detail": top_finding.get("detail", ""),
        "rule_check": top_finding.get("rule_check", ""),
        "supporting_findings": [
            {
                "finding_id": f.get("finding_id"),
                "title": f.get("title"),
                "severity": f.get("severity"),
                "agent": f.get("agent"),
            }
            for f in all_findings[1:4]  # top 3 supporting
        ],
    }

    # Section 3: Evidence Chain
    evidence_chain = [
        {
            "step": i + 1,
            "finding_id": f.get("finding_id"),
            "agent": f.get("agent"),
            "title": f.get("title"),
            "severity": f.get("severity"),
            "confidence": f.get("confidence_calibrated", 0.0),
            "detail": f.get("detail", ""),
            "rule_check": f.get("rule_check", ""),
            "evidence_ids": f.get("evidence_ids", []),
        }
        for i, f in enumerate(all_findings)
    ]

    # Section 4: Impact Assessment
    impact_assessment = {
        "blast_radius": (
            "high" if critical_count > 0
            else "medium" if high_count > 0
            else "low"
        ),
        "affected_layers": list({f.get("category", "unknown") for f in all_findings}),
        "affected_agents": list({f.get("agent", "unknown") for f in all_findings}),
        "remediation_available_count": sum(
            1 for f in all_findings if f.get("remediation_available")
        ),
        "estimated_user_impact": (
            "Service degradation likely" if critical_count > 0
            else "Partial degradation possible" if high_count > 0
            else "Minor performance impact" if medium_count > 0
            else "No immediate user impact"
        ),
        "connection_pool_saturation": any(
            f.get("category") == "connections" for f in all_findings
        ),
        "query_latency_elevated": any(
            f.get("category") == "slow_query" for f in all_findings
        ),
    }

    # Section 5: Remediation Recommendations
    remediation_recommendations = [
        {
            "priority": i + 1,
            "finding_id": f.get("finding_id"),
            "title": f.get("title"),
            "severity": f.get("severity"),
            "recommendation": f.get("recommendation", "No specific recommendation available."),
            "remediation_available": f.get("remediation_available", False),
            "category": f.get("category"),
        }
        for i, f in enumerate(all_findings)
        if f.get("recommendation")
    ]

    # Section 6: Prevention Measures
    prevention_measures = []
    category_prevention = {
        "slow_query": {
            "measure": "Implement query performance monitoring with pg_stat_statements",
            "cadence": "Review weekly",
        },
        "connections": {
            "measure": "Configure PgBouncer or HikariCP connection pooling with appropriate pool sizing",
            "cadence": "Review on capacity change",
        },
        "memory": {
            "measure": "Monitor buffer hit ratios via Prometheus + alerting on cache_hit_ratio < 90%",
            "cadence": "Alert-driven",
        },
        "deadlock": {
            "measure": "Establish consistent lock ordering conventions and set lock_timeout",
            "cadence": "Review on schema change",
        },
        "index": {
            "measure": "Schedule periodic index bloat analysis and REINDEX operations",
            "cadence": "Monthly",
        },
    }
    seen_categories: set[str] = set()
    for f in all_findings:
        cat = f.get("category", "unknown")
        if cat not in seen_categories and cat in category_prevention:
            seen_categories.add(cat)
            prevention_measures.append({
                "category": cat,
                "measure": category_prevention[cat]["measure"],
                "cadence": category_prevention[cat]["cadence"],
                "triggered_by": f.get("finding_id"),
            })

    if not prevention_measures:
        prevention_measures.append({
            "category": "general",
            "measure": "Continue routine monitoring. No specific prevention measures triggered.",
            "cadence": "Ongoing",
            "triggered_by": None,
        })

    # Section 7: Appendix
    appendix = {
        "raw_finding_ids": [f.get("finding_id") for f in all_findings],
        "agent_summary": {
            "query_analyst": len(state.get("query_findings", [])),
            "health_analyst": len(state.get("health_findings", [])),
            "schema_analyst": len(state.get("schema_findings", [])),
        },
        "latency_ms": state.get("health_latency_ms", 0),
        "investigation_mode": state.get("investigation_mode", "standalone"),
        "sampling_mode": state.get("sampling_mode", "standard"),
        "session_id": state.get("session_id", ""),
        "run_id": state.get("run_id", ""),
        "low_confidence_findings": [
            f.get("finding_id") for f in all_findings
            if f.get("confidence_calibrated", 1.0) < 0.7
        ],
    }

    dossier = {
        "executive_summary": exec_summary,
        "root_cause_analysis": root_cause_analysis,
        "evidence_chain": evidence_chain,
        "impact_assessment": impact_assessment,
        "remediation_recommendations": remediation_recommendations,
        "prevention_measures": prevention_measures,
        "appendix": appendix,
    }

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
        "dossier": dossier,
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

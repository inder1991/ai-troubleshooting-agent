"""LangGraph V2 for AI-powered database diagnostics.

Replaces heuristic graph.py with LLM-powered agents using a tool-first
pattern. Haiku for extraction agents, Opus for synthesizer/dossier.
"""

import asyncio
import logging
import re as _re
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
    fix_recommendations: list[dict]


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

    # Permission pre-check
    try:
        permissions = await adapter.check_permissions()
        missing = [view for view, ok in permissions.items() if not ok]
        if missing and emitter:
            await emitter.emit("connection_validator", "warning",
                              f"Missing permissions on: {', '.join(missing)}. Some diagnostics may be limited.")
        if emitter and not missing:
            await emitter.emit("connection_validator", "success",
                              "All diagnostic view permissions verified")
    except Exception as e:
        logger.warning("Permission check failed: %s", e)
        if emitter:
            await emitter.emit("connection_validator", "warning",
                              f"Could not verify permissions: {e}")

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


def _detect_index_suggestions(node: dict) -> list[dict]:
    """Scan EXPLAIN plan for Seq Scans with Filter — suggest indexes."""
    suggestions = []
    def scan(n):
        node_type = n.get('Node Type', '')
        if 'Seq Scan' in node_type and n.get('Relation Name') and n.get('Filter'):
            table = n['Relation Name']
            filter_text = n['Filter']
            cols = _re.findall(r'\b([a-z_][a-z0-9_]*)\s*[>=<]', filter_text, _re.IGNORECASE)
            if cols:
                suggestions.append({
                    "table": table,
                    "columns": list(dict.fromkeys(cols)),  # unique, preserve order
                    "filter": filter_text,
                    "rows_scanned": n.get('Plan Rows', 0),
                })
        for child in n.get('Plans', []):
            scan(child)
    scan(node)
    return suggestions


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
    slow = []

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

    # Historical slow queries from pg_stat_statements
    hist_slow: list[dict] = []
    try:
        hist_slow = await adapter.get_slow_queries_from_stats()
        for hs in hist_slow:
            mean_ms = hs.get("mean_exec_time", 0)
            if mean_ms > 100:  # only report queries averaging > 100ms
                findings.append(DBFindingV2(
                    finding_id=f"f-qa-hist-{hs.get('queryid', 0)}",
                    agent="query_analyst",
                    category="slow_query",
                    title=f"Historically slow query (avg {mean_ms:.0f}ms, {hs.get('calls', 0)} calls)",
                    severity="high" if mean_ms > 500 else "medium",
                    confidence_raw=0.85,
                    confidence_calibrated=0.80,
                    detail=f"Query: {str(hs.get('query', ''))[:200]}",
                    evidence_ids=[],
                    recommendation="Review query plan and optimize or add indexes",
                    remediation_available=False,
                    rule_check=f"mean_exec_time={mean_ms:.1f}ms > 100ms",
                ).model_dump())
    except Exception as e:
        logger.warning("pg_stat_statements check skipped: %s", e)

    # EXPLAIN the top 3 slow queries (read-only, no ANALYZE)
    explain_plans = []
    for q in sorted(slow, key=lambda q: q.duration_ms, reverse=True)[:3]:
        try:
            plan = await adapter.explain_query(q.query)
            if plan:
                explain_plans.append({
                    "plan": plan,
                    "query": q.query[:500],
                    "pid": q.pid,
                    "duration_ms": q.duration_ms,
                    "user": getattr(q, 'user', ''),
                })
                if emitter:
                    node_type = plan.get('Node Type', '?') if isinstance(plan, dict) else '?'
                    await emitter.emit("query_analyst", "reasoning",
                        f"EXPLAIN pid:{q.pid}: root node is {node_type}")
        except Exception as e:
            logger.warning("explain_query failed for pid %s: %s", q.pid, e)

    # Detect missing indexes from EXPLAIN plans
    for ep in explain_plans:
        plan_node = ep.get("plan", {})
        index_suggestions = _detect_index_suggestions(plan_node)
        for suggestion in index_suggestions:
            cols_str = ', '.join(suggestion['columns'])
            idx_name = f"idx_{suggestion['table']}_{'_'.join(suggestion['columns'])}"
            findings.append(DBFindingV2(
                finding_id=f"f-qa-idx-{suggestion['table']}",
                agent="query_analyst",
                category="index_candidate",
                title=f"Missing index: {suggestion['table']} ({cols_str})",
                severity="high",
                confidence_raw=0.80,
                confidence_calibrated=0.75,
                detail=f"Seq Scan on {suggestion['table']} with filter: {suggestion['filter']}. Scanned ~{suggestion['rows_scanned']} rows.",
                evidence_ids=[],
                recommendation=f"Create index on {suggestion['table']}({cols_str}) to eliminate sequential scan",
                remediation_sql=f"CREATE INDEX CONCURRENTLY {idx_name} ON {suggestion['table']} ({cols_str});",
                remediation_warning="CREATE INDEX CONCURRENTLY is non-blocking but may take minutes on large tables.",
                remediation_available=True,
                rule_check=f"seq_scan on {suggestion['table']} with filter",
            ).model_dump())

    if emitter:
        # Reasoning: explain what was found and why it matters
        total_queries = len(queries) if 'queries' in dir() else 0
        await emitter.emit("query_analyst", "reasoning", f"Scanned {total_queries} active queries, {len(slow)} exceed 5s threshold")
        for q in slow:
            sev = "CRITICAL" if q.duration_ms > 30000 else "HIGH" if q.duration_ms > 10000 else "MEDIUM"
            await emitter.emit("query_analyst", "reasoning", f"[{sev}] pid:{q.pid} running {q.duration_ms/1000:.1f}s — {q.query[:100]}...")
        if slow:
            await emitter.emit("query_analyst", "reasoning", "Recommendation: Review query plans, add missing indexes, consider connection pooling timeouts")
        else:
            await emitter.emit("query_analyst", "reasoning", "All queries within acceptable duration thresholds")

        # Historical slow query reasoning
        if hist_slow:
            await emitter.emit("query_analyst", "reasoning",
                              f"pg_stat_statements: {len(hist_slow)} historically slow queries found")
            for hs in hist_slow[:5]:
                mean_ms = hs.get("mean_exec_time", 0)
                calls = hs.get("calls", 0)
                await emitter.emit("query_analyst", "reasoning",
                                  f"  avg {mean_ms:.0f}ms x {calls} calls — {str(hs.get('query', ''))[:100]}...")

        # Structured data for visualization panels
        slow_queries_data = [{"pid": q.pid, "duration_ms": q.duration_ms, "query": q.query[:500]} for q in slow]
        finding_details: dict = {
            "slow_queries": slow_queries_data,
            "historical_slow_queries": hist_slow[:5] if hist_slow else None,
        }
        if explain_plans:
            finding_details["explain_plans"] = explain_plans
            # Keep backward compat: also set explain_plan to the first one
            finding_details["explain_plan"] = explain_plans[0]
        await emitter.emit("query_analyst", "finding", f"Found {len(findings)} query issues", details=finding_details)
        await emitter.emit("query_analyst", "success", f"Query analysis complete — {len(findings)} issues")

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
    pool = None
    perf = None
    replication_data = None

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

        # Replication data
        repl = await adapter.get_replication_status()
        if repl.replicas:
            replication_data = {
                "primary": {"host": state.get("host", "primary"), "lag_ms": 0},
                "replicas": [{"host": r.name, "lag_ms": int(r.lag_seconds * 1000), "status": r.state} for r in repl.replicas],
            }
            lagging = [r for r in repl.replicas if r.lag_seconds > 10]
            if lagging:
                findings.append(DBFindingV2(
                    finding_id="f-ha-repl-lag",
                    agent="health_analyst",
                    category="replication",
                    title=f"Replication lag detected ({len(lagging)} replicas behind)",
                    severity="high" if any(r.lag_seconds > 30 for r in lagging) else "medium",
                    confidence_raw=0.90,
                    confidence_calibrated=0.85,
                    detail=f"Replicas lagging: {', '.join(f'{r.name} ({r.lag_seconds}s)' for r in lagging)}",
                    evidence_ids=[],
                    recommendation="Check network connectivity and replica load",
                    remediation_available=False,
                    rule_check=f"replicas_lagging={len(lagging)}",
                ).model_dump())
    except Exception as e:
        logger.error("Health analyst failed: %s", e)
        if emitter:
            await emitter.emit("health_analyst", "error", str(e))

    if emitter:
        # Reasoning: explain observations
        if pool:
            util = round(pool.active / pool.max_connections * 100, 1) if pool.max_connections else 0
            await emitter.emit("health_analyst", "reasoning", f"Connection pool: {pool.active}/{pool.max_connections} active ({util}% utilization), {pool.waiting} waiting")
            if util > 80:
                await emitter.emit("health_analyst", "reasoning", f"Pool near saturation — queries may queue. Consider increasing max_connections or adding PgBouncer")
        if perf:
            await emitter.emit("health_analyst", "reasoning", f"Cache hit ratio: {perf.cache_hit_ratio:.1%} {'(healthy)' if perf.cache_hit_ratio >= 0.9 else '(below 90% — shared_buffers may need increase)'}")
            if perf.deadlocks > 0:
                await emitter.emit("health_analyst", "reasoning", f"{perf.deadlocks} deadlocks detected — review transaction isolation and lock ordering")
            await emitter.emit("health_analyst", "reasoning", f"Throughput: {perf.transactions_per_sec:.0f} TPS, uptime: {perf.uptime_seconds // 86400}d {(perf.uptime_seconds % 86400) // 3600}h")
        if replication_data and replication_data.get("replicas"):
            lagging_repls = [r for r in replication_data["replicas"] if r["lag_ms"] > 10000]
            healthy_repls = [r for r in replication_data["replicas"] if r["lag_ms"] <= 10000]
            await emitter.emit("health_analyst", "reasoning", f"Replication: {len(replication_data['replicas'])} replicas — {len(healthy_repls)} healthy, {len(lagging_repls)} lagging")
            for r in lagging_repls:
                await emitter.emit("health_analyst", "reasoning", f"  ⚠ {r['host']} lagging {r['lag_ms']/1000:.1f}s ({r['status']})")

        # Structured data for visualization panels
        conn_data = {"active": pool.active, "idle": pool.idle, "waiting": pool.waiting, "max_connections": pool.max_connections} if pool else None
        perf_data = {"cache_hit_ratio": perf.cache_hit_ratio, "transactions_per_sec": perf.transactions_per_sec, "deadlocks": perf.deadlocks, "uptime_seconds": perf.uptime_seconds} if perf else None
        await emitter.emit("health_analyst", "finding", f"Found {len(findings)} health issues", details={
            "connections": conn_data,
            "performance": perf_data,
            "replication": replication_data,
        })
        await emitter.emit("health_analyst", "success", f"Health analysis complete — {len(findings)} issues")

    return {"health_findings": findings}


# --- Node: Schema Analyst (LLM + tools) ---

async def schema_analyst(state: DBDiagnosticStateV2) -> dict:
    """Analyze schema health and index usage."""
    emitter = state.get("_emitter")
    if emitter:
        await emitter.emit("schema_analyst", "started", "Analyzing schema health")

    adapter = state["_adapter"]
    findings = []
    indexes_data = []
    bloat_data = []

    try:
        schema = await adapter.get_schema_snapshot()
        # Get detailed info per table (includes bloat_ratio, indexes)
        for tbl_dict in schema.tables:
            tbl_name = tbl_dict.get("name", "") if isinstance(tbl_dict, dict) else getattr(tbl_dict, "name", "")
            try:
                detail = await adapter.get_table_detail(tbl_name)
                bloat = detail.bloat_ratio
                if bloat > 0.15:
                    findings.append(DBFindingV2(
                        finding_id=f"f-sa-bloat-{tbl_name}",
                        agent="schema_analyst",
                        category="bloat",
                        title=f"Table bloat: {tbl_name} ({bloat:.0%})",
                        severity="high" if bloat > 0.4 else "medium",
                        confidence_raw=0.9,
                        confidence_calibrated=0.85,
                        detail=f"Table {tbl_name} has {bloat:.0%} bloat",
                        evidence_ids=[],
                        recommendation="Run VACUUM FULL or pg_repack",
                        remediation_available=True,
                        rule_check=f"bloat_ratio={bloat:.2f} > 0.15",
                    ).model_dump())
                bloat_data.append({"name": tbl_name, "bloat_ratio": bloat, "dead_tuples": 0, "size_mb": round(detail.total_size_bytes / 1048576, 1)})
                for idx in detail.indexes:
                    scans = getattr(idx, "scan_count", 0)
                    indexes_data.append({"name": idx.name, "table": tbl_name, "scans": scans, "size_mb": round(idx.size_bytes / 1048576, 1), "unused": scans == 0})
            except Exception:
                pass
    except Exception as e:
        logger.error("Schema analyst failed: %s", e)
        if emitter:
            await emitter.emit("schema_analyst", "error", str(e))

    if emitter:
        # Reasoning: explain observations
        await emitter.emit("schema_analyst", "reasoning", f"Scanned {len(bloat_data)} tables, {len(indexes_data)} indexes")
        bloated = [t for t in bloat_data if t["bloat_ratio"] > 0.15]
        if bloated:
            await emitter.emit("schema_analyst", "reasoning", f"{len(bloated)} tables have significant bloat (>15%):")
            for t in sorted(bloated, key=lambda x: x["bloat_ratio"], reverse=True):
                await emitter.emit("schema_analyst", "reasoning", f"  {t['name']}: {t['bloat_ratio']:.0%} bloat ({t['size_mb']:.0f} MB) — VACUUM recommended")
        else:
            await emitter.emit("schema_analyst", "reasoning", "All tables within acceptable bloat thresholds")
        total_idx_size = sum(i["size_mb"] for i in indexes_data)
        await emitter.emit("schema_analyst", "reasoning", f"Total index footprint: {total_idx_size:.1f} MB across {len(indexes_data)} indexes")

        # Structured data for visualization panels
        await emitter.emit("schema_analyst", "finding", f"Found {len(findings)} schema issues", details={
            "indexes": indexes_data if indexes_data else None,
            "table_bloat": bloat_data if bloat_data else None,
        })
        await emitter.emit("schema_analyst", "success", f"Schema analysis complete — {len(findings)} issues")

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

    # Generate copy-pasteable SQL for each recommendation
    engine = state.get("engine", "postgresql")
    fix_recommendations = []
    for i, f in enumerate(all_findings):
        if not f.get("recommendation"):
            continue
        cat = f.get("category", "")
        sql = ""
        warning = "Review carefully before executing."
        verification_sql = ""
        estimated_impact = ""
        if cat == "slow_query":
            pid = f.get("finding_id", "").replace("f-qa-", "")
            if engine == "mongodb":
                sql = f"db.killOp({pid})"
            else:
                sql = f"SELECT pg_terminate_backend({pid});"
            warning = "Terminates the query immediately. Active transactions will be rolled back."
            verification_sql = f"SELECT pid, state FROM pg_stat_activity WHERE pid = {pid};\n-- Should return 0 rows after termination"
            estimated_impact = "Immediate — query terminated, connection freed"
        elif cat == "bloat":
            table = f.get("title", "").split(":")[1].split("(")[0].strip() if ":" in f.get("title", "") else ""
            bloat_pct = f.get("detail", "")
            if "67%" in bloat_pct or "42%" in bloat_pct:
                sql = f"VACUUM FULL {table};"
            else:
                sql = f"VACUUM (VERBOSE, ANALYZE) {table};"
            warning = "VACUUM FULL locks the table for the duration. Schedule during maintenance window."
            verification_sql = f"SELECT relname, n_dead_tup, n_live_tup,\n  round(n_dead_tup::numeric / GREATEST(n_live_tup,1) * 100, 1) AS bloat_pct\nFROM pg_stat_user_tables WHERE relname = '{table}';\n-- bloat_pct should be < 5% after VACUUM"
            estimated_impact = "Table locked during VACUUM FULL. Use pg_repack for zero-downtime alternative."
        elif cat == "connections":
            if engine == "mongodb":
                sql = "db.serverStatus().connections"
            else:
                sql = "-- Review connection pooling configuration\n-- Consider: ALTER SYSTEM SET max_connections = 200;\n-- Requires: SELECT pg_reload_conf(); + restart"
            warning = "Requires PostgreSQL restart to take effect. Plan for brief downtime."
            verification_sql = "SELECT count(*) AS active FROM pg_stat_activity WHERE state = 'active';\n-- Should decrease after pool tuning"
            estimated_impact = "Requires restart if max_connections changed."
        elif cat == "memory":
            if engine == "mongodb":
                sql = "db.serverStatus().wiredTiger.cache"
            else:
                sql = "ALTER SYSTEM SET shared_buffers = '1GB';\nSELECT pg_reload_conf();\n-- Note: Requires PostgreSQL restart to take effect"
            warning = "Requires PostgreSQL restart. Ensure server has enough RAM."
            verification_sql = "SHOW shared_buffers;\nSELECT round(heap_blks_hit::numeric / (heap_blks_hit + heap_blks_read) * 100, 1) AS cache_hit_pct\nFROM pg_statio_user_tables;\n-- cache_hit_pct should improve after restart"
            estimated_impact = "Requires PostgreSQL restart. Plan 30-60s downtime."
        elif cat == "deadlock":
            sql = "-- Investigate current locks:\nSELECT * FROM pg_locks WHERE NOT granted;\n\n-- Review blocking queries:\nSELECT blocked.pid, blocked.query, blocking.pid AS blocking_pid, blocking.query AS blocking_query\nFROM pg_stat_activity blocked\nJOIN pg_locks bl ON bl.pid = blocked.pid\nJOIN pg_locks blk ON blk.locktype = bl.locktype AND blk.granted\nJOIN pg_stat_activity blocking ON blocking.pid = blk.pid\nWHERE NOT bl.granted;"
            warning = "Diagnostic query only. Review results before taking action."
            verification_sql = "SELECT deadlocks FROM pg_stat_database WHERE datname = current_database();\n-- Monitor for decrease"
            estimated_impact = "Diagnostic only — review lock ordering in application code."
        elif cat == "replication":
            sql = "-- Check replication status:\nSELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn,\n  (extract(epoch from now() - pg_last_xact_replay_timestamp()))::int AS lag_seconds\nFROM pg_stat_replication;"
            warning = "Diagnostic query only. Do not modify replication settings without DBA review."
            verification_sql = "SELECT client_addr, state, replay_lag FROM pg_stat_replication;\n-- replay_lag should decrease"
            estimated_impact = "Diagnostic only — check network and replica load."
        elif cat == "index_candidate":
            verification_sql = "-- After creating index, verify plan changed:\nEXPLAIN SELECT ... -- Should show Index Scan"
            estimated_impact = "Non-blocking with CONCURRENTLY. Minutes on large tables."

        fix_recommendations.append({
            "priority": i + 1,
            "finding_id": f.get("finding_id"),
            "title": f.get("title"),
            "severity": f.get("severity"),
            "category": cat,
            "recommendation": f.get("recommendation"),
            "sql": sql,
            "warning": warning,
            "verification_sql": verification_sql,
            "estimated_impact": estimated_impact,
            "agent": f.get("agent"),
        })

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
        top_severity = top_finding.get("severity", "medium") if all_findings else "info"
        top_rec = top_finding.get("recommendation", "") if all_findings else ""
        await emitter.emit("synthesizer", "success", summary, details={
            "severity": top_severity,
            "recommendation": top_rec,
            "root_cause": root_cause,
            "finding_count": finding_count,
            "critical_count": critical_count,
        })
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
        "fix_recommendations": fix_recommendations,
    }


# --- Node: Orchestrator (LLM-powered agents) ---

async def orchestrator_node(state: DBDiagnosticStateV2) -> dict:
    """Run LLM-powered agents via DiagnosticOrchestrator."""
    from .orchestrator import DiagnosticOrchestrator

    orchestrator = DiagnosticOrchestrator()
    result = await orchestrator.run(state)
    return result


# --- Graph Builder ---

def build_db_diagnostic_graph_v2():
    graph = StateGraph(DBDiagnosticStateV2)

    graph.add_node("connection_validator", connection_validator)
    graph.add_node("context_loader", context_loader)
    graph.add_node("orchestrator", orchestrator_node)

    graph.set_entry_point("connection_validator")

    graph.add_conditional_edges(
        "connection_validator",
        lambda s: "context_loader" if s.get("connected") else END,
    )

    graph.add_edge("context_loader", "orchestrator")
    graph.add_edge("orchestrator", END)

    return graph.compile()

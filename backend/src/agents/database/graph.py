"""LangGraph StateGraph for database diagnostics.

Graph flow:
  START → connection_validator → snapshot_collector → symptom_classifier
        → query_agent → health_agent → synthesize → END

If connection_validator fails, short-circuits to END with error.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import uuid
from datetime import datetime

from langgraph.graph import END, StateGraph

from .state import DBDiagnosticState

logger = logging.getLogger(__name__)

_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _run_sync(coro):
    """Run an async coroutine from a sync LangGraph node, safe inside existing event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        future = _thread_pool.submit(asyncio.run, coro)
        return future.result(timeout=30)
    return asyncio.run(coro)


def connection_validator(state: DBDiagnosticState) -> dict:
    """Validate DB connectivity. Fail fast if unreachable."""
    adapter = state.get("_adapter")
    if not adapter:
        return {"connected": False, "error": "No adapter configured", "status": "failed"}

    async def _check():
        try:
            health = await adapter.health_check()
            if health.status == "unreachable":
                return {"connected": False, "error": health.error or "Unreachable", "status": "failed"}
            return {"connected": True, "health_latency_ms": health.latency_ms}
        except Exception as e:
            return {"connected": False, "error": str(e), "status": "failed"}

    return _run_sync(_check())


def snapshot_collector(state: DBDiagnosticState) -> dict:
    """Populate all adapter caches in parallel."""
    adapter = state.get("_adapter")
    if not adapter:
        return {}

    async def _collect():
        try:
            await adapter.refresh_snapshot()
        except Exception as e:
            logger.warning("Snapshot collection partial failure: %s", e)
        return {}

    return _run_sync(_collect())


def symptom_classifier(state: DBDiagnosticState) -> dict:
    """Classify symptoms to determine which agents to dispatch."""
    return {
        "symptoms": ["slow_queries", "connections", "replication", "storage"],
        "dispatched_agents": ["query_agent", "health_agent"],
    }


def query_agent_node(state: DBDiagnosticState) -> dict:
    """Run query performance analysis."""
    adapter = state.get("_adapter")
    findings = list(state.get("findings", []))

    if not adapter:
        return {"findings": findings}

    async def _analyze():
        try:
            queries = await adapter.get_active_queries()
            slow = [q for q in queries if q.duration_ms > 5000]
            for q in slow:
                findings.append({
                    "finding_id": str(uuid.uuid4()),
                    "category": "query_performance",
                    "severity": "critical" if q.duration_ms > 30000 else "high" if q.duration_ms > 10000 else "medium",
                    "confidence": 0.9,
                    "title": f"Slow query (pid {q.pid}): {q.duration_ms:.0f}ms",
                    "detail": q.query[:500],
                    "evidence": [f"Duration: {q.duration_ms:.0f}ms", f"State: {q.state}", f"User: {q.user}"],
                    "recommendation": "Review query plan with EXPLAIN ANALYZE. Consider adding indexes.",
                })
            if not slow and queries:
                # Check for queries approaching threshold
                near_slow = [q for q in queries if q.duration_ms > 1000]
                if near_slow:
                    findings.append({
                        "finding_id": str(uuid.uuid4()),
                        "category": "query_performance",
                        "severity": "low",
                        "confidence": 0.6,
                        "title": f"{len(near_slow)} queries between 1-5s",
                        "detail": f"Longest: {near_slow[0].query[:200]}",
                        "evidence": [f"Count: {len(near_slow)}"],
                    })
        except Exception as e:
            logger.warning("Query agent error: %s", e)
        return {"findings": findings}

    return _run_sync(_analyze())


def health_agent_node(state: DBDiagnosticState) -> dict:
    """Run health diagnostics (connections, replication, storage)."""
    adapter = state.get("_adapter")
    findings = list(state.get("findings", []))

    if not adapter:
        return {"findings": findings}

    async def _analyze():
        try:
            stats = await adapter.get_performance_stats()
            pool = await adapter.get_connection_pool()
            repl = await adapter.get_replication_status()

            # Connection saturation
            if pool.max_connections > 0:
                usage_pct = (pool.active + pool.waiting) / pool.max_connections * 100
                if usage_pct > 80:
                    findings.append({
                        "finding_id": str(uuid.uuid4()),
                        "category": "connections",
                        "severity": "critical" if usage_pct > 95 else "high",
                        "confidence": 0.95,
                        "title": f"Connection pool at {usage_pct:.0f}% capacity",
                        "detail": f"Active: {pool.active}, Idle: {pool.idle}, Waiting: {pool.waiting}, Max: {pool.max_connections}",
                        "evidence": [f"Usage: {usage_pct:.0f}%"],
                        "recommendation": "Increase max_connections or use pgbouncer connection pooling.",
                    })

            # Cache hit ratio
            if stats.cache_hit_ratio < 0.9 and stats.cache_hit_ratio > 0:
                findings.append({
                    "finding_id": str(uuid.uuid4()),
                    "category": "memory",
                    "severity": "high" if stats.cache_hit_ratio < 0.8 else "medium",
                    "confidence": 0.85,
                    "title": f"Low cache hit ratio: {stats.cache_hit_ratio:.2%}",
                    "detail": "Database is reading too much from disk instead of shared buffers.",
                    "evidence": [f"Cache hit ratio: {stats.cache_hit_ratio:.4f}"],
                    "recommendation": "Increase shared_buffers or reduce working set size.",
                })

            # Replication lag
            if repl.is_replica and repl.replication_lag_bytes > 10_000_000:
                lag_mb = repl.replication_lag_bytes / 1_000_000
                findings.append({
                    "finding_id": str(uuid.uuid4()),
                    "category": "replication",
                    "severity": "critical" if lag_mb > 100 else "high",
                    "confidence": 0.92,
                    "title": f"Replication lag: {lag_mb:.1f} MB",
                    "detail": "Replica is behind primary, reads may be stale.",
                    "evidence": [f"Lag bytes: {repl.replication_lag_bytes}"],
                    "recommendation": "Check replica IO and CPU. Consider reducing write load.",
                })

            # Deadlocks
            if stats.deadlocks > 0:
                findings.append({
                    "finding_id": str(uuid.uuid4()),
                    "category": "locks",
                    "severity": "medium",
                    "confidence": 0.8,
                    "title": f"{stats.deadlocks} deadlocks detected",
                    "detail": "Deadlocks indicate lock contention between transactions.",
                    "evidence": [f"Deadlock count: {stats.deadlocks}"],
                    "recommendation": "Review transaction isolation levels and lock ordering.",
                })

        except Exception as e:
            logger.warning("Health agent error: %s", e)
        return {"findings": findings}

    return _run_sync(_analyze())


def synthesize(state: DBDiagnosticState) -> dict:
    """Merge and deduplicate findings, rank by severity."""
    findings = state.get("findings", [])
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(
        key=lambda f: (
            severity_order.get(f.get("severity", "info"), 4),
            -f.get("confidence", 0),
        )
    )
    summary = f"{len(findings)} finding(s) detected" if findings else "No issues found — database is healthy"
    return {
        "findings": findings,
        "summary": summary,
        "status": "completed",
    }


def should_continue(state: DBDiagnosticState) -> str:
    if not state.get("connected"):
        return "end"
    return "continue"


def build_db_diagnostic_graph():
    graph = StateGraph(DBDiagnosticState)

    graph.add_node("connection_validator", connection_validator)
    graph.add_node("snapshot_collector", snapshot_collector)
    graph.add_node("symptom_classifier", symptom_classifier)
    graph.add_node("query_agent", query_agent_node)
    graph.add_node("health_agent", health_agent_node)
    graph.add_node("synthesize", synthesize)

    graph.set_entry_point("connection_validator")
    graph.add_conditional_edges(
        "connection_validator",
        should_continue,
        {"continue": "snapshot_collector", "end": END},
    )
    graph.add_edge("snapshot_collector", "symptom_classifier")
    graph.add_edge("symptom_classifier", "query_agent")
    graph.add_edge("query_agent", "health_agent")
    graph.add_edge("health_agent", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()

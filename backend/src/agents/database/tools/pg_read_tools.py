"""Read-only PostgreSQL diagnostic tools.

Every tool returns a ToolOutput dict with:
- summary: compact dict for LLM consumption
- artifact_id: reference to evidence_artifacts row
- evidence_id: unique fingerprint for citation
"""

import uuid
from typing import Any

from src.database.evidence_store import EvidenceStore


def _evidence_id() -> str:
    return f"e-{uuid.uuid4().hex[:8]}"


async def run_explain(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
    sql: str,
    analyze: bool = False,
) -> dict:
    """Run EXPLAIN (FORMAT JSON) on a query. ANALYZE only when explicitly allowed."""
    explain_prefix = "EXPLAIN (FORMAT JSON, ANALYZE)" if analyze else "EXPLAIN (FORMAT JSON)"
    result = await adapter.execute_diagnostic_query(f"{explain_prefix} {sql}")

    full_content = str(result)
    rows = result.get("rows", [])
    plan_summary = "No plan returned"
    if rows and rows[0]:
        plan_summary = str(rows[0][0])[:200]

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id,
        evidence_id=eid,
        source_agent=agent_name,
        artifact_type="explain_plan",
        summary_json={"plan_preview": plan_summary, "analyze": analyze},
        full_content=full_content,
        preview=plan_summary[:100],
    )
    return {"summary": {"plan_preview": plan_summary, "analyze": analyze},
            "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_pg_stat_statements(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
    top_n: int = 20,
    order_by: str = "total_exec_time",
) -> dict:
    sql = f"""
        SELECT queryid, query, calls, total_exec_time, mean_exec_time,
               rows, shared_blks_hit, shared_blks_read
        FROM pg_stat_statements
        ORDER BY {order_by} DESC
        LIMIT {top_n}
    """
    result = await adapter.execute_diagnostic_query(sql)
    rows = result.get("rows", [])
    columns = result.get("columns", [])

    summary = {"top_queries_count": len(rows), "order_by": order_by}
    if rows:
        summary["top_query_preview"] = str(rows[0])[:200]

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="pg_stat_statements",
        summary_json=summary,
        full_content=str({"columns": columns, "rows": rows}),
        preview=f"Top {len(rows)} queries by {order_by}",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_pg_stat_activity(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    queries = await adapter.get_active_queries()
    query_list = [
        {"pid": q.pid, "duration_ms": q.duration_ms, "state": q.state, "query": q.query[:100]}
        for q in queries
    ] if queries else []

    summary = {
        "active_count": len(query_list),
        "slow_count": sum(1 for q in query_list if q["duration_ms"] > 5000),
    }

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="pg_stat_activity",
        summary_json=summary,
        full_content=str(query_list),
        preview=f"{summary['active_count']} active queries, {summary['slow_count']} slow (>5s)",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_pg_locks(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    sql = """
        SELECT l.pid, l.locktype, l.mode, l.granted, l.relation::regclass AS relation,
               a.query, a.state, a.wait_event_type
        FROM pg_locks l
        JOIN pg_stat_activity a ON l.pid = a.pid
        WHERE NOT l.granted
        ORDER BY a.query_start
    """
    result = await adapter.execute_diagnostic_query(sql)
    rows = result.get("rows", [])

    summary = {"blocked_count": len(rows)}
    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="pg_locks",
        summary_json=summary,
        full_content=str(result),
        preview=f"{len(rows)} blocked lock requests",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def inspect_table_stats(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
    table_filter: list[str] | None = None,
) -> dict:
    where_clause = ""
    if table_filter:
        tables = ", ".join(f"'{t}'" for t in table_filter)
        where_clause = f"WHERE relname IN ({tables})"

    sql = f"""
        SELECT relname, seq_scan, idx_scan, n_tup_ins, n_tup_upd, n_tup_del,
               n_dead_tup, n_live_tup, last_vacuum, last_autovacuum, last_analyze
        FROM pg_stat_user_tables
        {where_clause}
        ORDER BY n_dead_tup DESC
        LIMIT 50
    """
    result = await adapter.execute_diagnostic_query(sql)
    rows = result.get("rows", [])

    summary = {"tables_scanned": len(rows)}
    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="table_stats",
        summary_json=summary,
        full_content=str(result),
        preview=f"Stats for {len(rows)} tables",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def inspect_index_usage(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    sql = """
        SELECT s.relname AS table, s.indexrelname AS index, s.idx_scan,
               pg_relation_size(s.indexrelid) AS index_size
        FROM pg_stat_user_indexes s
        ORDER BY s.idx_scan ASC
        LIMIT 50
    """
    result = await adapter.execute_diagnostic_query(sql)
    rows = result.get("rows", [])

    unused = [r for r in rows if r and len(r) > 2 and r[2] == 0]
    summary = {"indexes_checked": len(rows), "unused_indexes": len(unused)}

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="index_usage",
        summary_json=summary,
        full_content=str(result),
        preview=f"{len(rows)} indexes checked, {len(unused)} unused",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def get_connection_pool(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    pool = await adapter.get_connection_pool()
    utilization = round((pool.active / pool.max_connections) * 100, 1) if pool.max_connections else 0

    summary = {
        "active": pool.active,
        "idle": pool.idle,
        "waiting": pool.waiting,
        "max": pool.max_connections,
        "utilization_pct": utilization,
    }

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="connection_pool",
        summary_json=summary,
        full_content=str(summary),
        preview=f"Connections: {pool.active}/{pool.max_connections} ({utilization}%)",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}

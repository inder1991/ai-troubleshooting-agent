"""Read-only MongoDB diagnostic tools.

Every tool returns a ToolOutput dict with:
- summary: compact dict for LLM consumption
- artifact_id: reference to evidence_artifacts row
- evidence_id: unique fingerprint for citation
"""

import json
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
    collection: str,
    query_filter: dict | None = None,
) -> dict:
    """Run explain on a MongoDB collection query via the adapter."""
    if query_filter is None:
        query_filter = {}

    diagnostic_input = json.dumps({"collection": collection, "filter": query_filter})
    result = await adapter.execute_diagnostic_query(diagnostic_input)

    # result is a QueryResult pydantic model
    plan_summary = f"collection={collection}, rows_returned={result.rows_returned}, time_ms={result.execution_time_ms}"
    if result.error:
        plan_summary = f"Error: {result.error}"

    full_content = result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id,
        evidence_id=eid,
        source_agent=agent_name,
        artifact_type="mongo_explain",
        summary_json={
            "collection": collection,
            "query_filter": query_filter,
            "rows_returned": result.rows_returned,
            "execution_time_ms": result.execution_time_ms,
            "error": result.error,
        },
        full_content=full_content,
        preview=plan_summary[:100],
    )
    return {
        "summary": {
            "collection": collection,
            "rows_returned": result.rows_returned,
            "execution_time_ms": result.execution_time_ms,
            "error": result.error,
        },
        "artifact_id": artifact["artifact_id"],
        "evidence_id": eid,
    }


async def query_current_ops(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    """Query current MongoDB operations (equivalent to pg_stat_activity)."""
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
        session_id=session_id,
        evidence_id=eid,
        source_agent=agent_name,
        artifact_type="mongo_current_ops",
        summary_json=summary,
        full_content=str(query_list),
        preview=f"{summary['active_count']} active ops, {summary['slow_count']} slow (>5s)",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_server_status(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    """Query MongoDB serverStatus (connections, cache, ops/sec, uptime)."""
    perf = await adapter.get_performance_stats()

    summary = {
        "connections": perf.connections_active + perf.connections_idle,
        "cache_hit_ratio": perf.cache_hit_ratio,
        "ops_per_sec": perf.transactions_per_sec,
        "uptime_seconds": perf.uptime_seconds,
    }

    eid = _evidence_id()
    full_content = perf.model_dump_json() if hasattr(perf, "model_dump_json") else str(perf)
    artifact = evidence_store.create(
        session_id=session_id,
        evidence_id=eid,
        source_agent=agent_name,
        artifact_type="mongo_server_status",
        summary_json=summary,
        full_content=full_content,
        preview=f"conns={summary['connections']}, cache={summary['cache_hit_ratio']}, ops/s={summary['ops_per_sec']}",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_collection_stats(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
    collection_filter: list[str] | None = None,
) -> dict:
    """Query MongoDB collection stats via schema snapshot."""
    schema = await adapter.get_schema_snapshot()
    tables = schema.tables

    if collection_filter:
        tables = [t for t in tables if t.get("name") in collection_filter]

    summary = {"collections_scanned": len(tables)}

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id,
        evidence_id=eid,
        source_agent=agent_name,
        artifact_type="mongo_collection_stats",
        summary_json=summary,
        full_content=str(tables),
        preview=f"Stats for {len(tables)} collections",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def inspect_collection_indexes(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    """Inspect indexes across all MongoDB collections."""
    schema = await adapter.get_schema_snapshot()
    indexes = schema.indexes

    summary = {"indexes_checked": len(indexes)}

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id,
        evidence_id=eid,
        source_agent=agent_name,
        artifact_type="mongo_index_inspection",
        summary_json=summary,
        full_content=str(indexes),
        preview=f"{len(indexes)} indexes checked",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def get_connection_info(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    """Get MongoDB connection pool info."""
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
        session_id=session_id,
        evidence_id=eid,
        source_agent=agent_name,
        artifact_type="mongo_connection_info",
        summary_json=summary,
        full_content=str(summary),
        preview=f"Connections: {pool.active}/{pool.max_connections} ({utilization}%)",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def get_replication_status(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    """Get MongoDB replica set status."""
    repl = await adapter.get_replication_status()

    members = [
        {"name": r.name, "state": r.state, "lag_seconds": r.lag_seconds}
        for r in repl.replicas
    ]

    summary = {
        "is_replica": repl.is_replica,
        "replica_count": len(repl.replicas),
        "members": members,
    }

    eid = _evidence_id()
    full_content = repl.model_dump_json() if hasattr(repl, "model_dump_json") else str(repl)
    artifact = evidence_store.create(
        session_id=session_id,
        evidence_id=eid,
        source_agent=agent_name,
        artifact_type="mongo_replication_status",
        summary_json=summary,
        full_content=full_content,
        preview=f"is_replica={repl.is_replica}, members={len(repl.replicas)}",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}

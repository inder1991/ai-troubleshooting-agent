import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.database.tools.mongo_read_tools import (
    run_explain,
    query_current_ops,
    query_server_status,
    query_collection_stats,
    inspect_collection_indexes,
    get_connection_info,
    get_replication_status,
)


class FakeEvidenceStore:
    def create(self, **kwargs):
        return {"artifact_id": "art-1"}


@pytest.fixture
def evidence_store():
    return FakeEvidenceStore()


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()

    # execute_diagnostic_query returns a QueryResult-like object
    adapter.execute_diagnostic_query = AsyncMock(return_value=MagicMock(
        rows_returned=42,
        execution_time_ms=12.5,
        error=None,
        model_dump_json=MagicMock(return_value='{"query":"test","rows_returned":42}'),
    ))

    # get_active_queries returns list of ActiveQuery-like objects
    slow_query = MagicMock(pid=101, duration_ms=8000, state="query", query="db.orders.find({})")
    fast_query = MagicMock(pid=102, duration_ms=50, state="query", query="db.users.find({})")
    adapter.get_active_queries = AsyncMock(return_value=[slow_query, fast_query])

    # get_performance_stats returns PerfSnapshot-like object
    adapter.get_performance_stats = AsyncMock(return_value=MagicMock(
        connections_active=15,
        connections_idle=85,
        connections_max=200,
        cache_hit_ratio=0.97,
        transactions_per_sec=1250.0,
        uptime_seconds=86400,
        deadlocks=0,
        model_dump_json=MagicMock(return_value="{}"),
    ))

    # get_schema_snapshot returns SchemaSnapshot-like object
    adapter.get_schema_snapshot = AsyncMock(return_value=MagicMock(
        tables=[
            {"name": "orders", "rows": 50000, "size_bytes": 10240000},
            {"name": "users", "rows": 1000, "size_bytes": 204800},
        ],
        indexes=[
            {"name": "_id_", "table": "orders", "size_bytes": 512000},
            {"name": "user_id_1", "table": "orders", "size_bytes": 256000},
            {"name": "_id_", "table": "users", "size_bytes": 128000},
        ],
        total_size_bytes=11000000,
    ))

    # get_connection_pool returns ConnectionPoolSnapshot-like object
    adapter.get_connection_pool = AsyncMock(return_value=MagicMock(
        active=10, idle=5, waiting=2, max_connections=100,
    ))

    # get_replication_status returns ReplicationSnapshot-like object
    member1 = MagicMock(name="mongo-rs0:27017", state="PRIMARY", lag_seconds=0.0)
    member1.name = "mongo-rs0:27017"
    member2 = MagicMock(name="mongo-rs1:27017", state="SECONDARY", lag_seconds=1.2)
    member2.name = "mongo-rs1:27017"
    adapter.get_replication_status = AsyncMock(return_value=MagicMock(
        is_replica=True,
        replicas=[member1, member2],
        replication_lag_bytes=0,
        replication_lag_seconds=1.2,
        model_dump_json=MagicMock(return_value="{}"),
    ))

    return adapter


# ── Core tests (required 3) ──


@pytest.mark.asyncio
async def test_query_current_ops(mock_adapter, evidence_store):
    result = await query_current_ops(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="mongo_analyst",
    )
    assert "artifact_id" in result
    assert "evidence_id" in result
    assert result["summary"]["active_count"] == 2
    assert result["summary"]["slow_count"] == 1  # only the 8000ms query
    mock_adapter.get_active_queries.assert_called_once()


@pytest.mark.asyncio
async def test_query_server_status(mock_adapter, evidence_store):
    result = await query_server_status(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="mongo_analyst",
    )
    assert result["summary"]["connections"] == 100  # 15 active + 85 idle
    assert result["summary"]["cache_hit_ratio"] == 0.97
    assert result["summary"]["ops_per_sec"] == 1250.0
    assert result["summary"]["uptime_seconds"] == 86400
    mock_adapter.get_performance_stats.assert_called_once()


@pytest.mark.asyncio
async def test_get_connection_info(mock_adapter, evidence_store):
    result = await get_connection_info(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="mongo_analyst",
    )
    assert result["summary"]["active"] == 10
    assert result["summary"]["idle"] == 5
    assert result["summary"]["waiting"] == 2
    assert result["summary"]["max"] == 100
    assert result["summary"]["utilization_pct"] == 10.0
    mock_adapter.get_connection_pool.assert_called_once()


# ── Additional tests for completeness ──


@pytest.mark.asyncio
async def test_run_explain(mock_adapter, evidence_store):
    result = await run_explain(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="mongo_analyst",
        collection="orders",
        query_filter={"status": "pending"},
    )
    assert "artifact_id" in result
    assert result["summary"]["collection"] == "orders"
    assert result["summary"]["rows_returned"] == 42
    mock_adapter.execute_diagnostic_query.assert_called_once()


@pytest.mark.asyncio
async def test_query_collection_stats(mock_adapter, evidence_store):
    result = await query_collection_stats(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="mongo_analyst",
    )
    assert result["summary"]["collections_scanned"] == 2


@pytest.mark.asyncio
async def test_query_collection_stats_with_filter(mock_adapter, evidence_store):
    result = await query_collection_stats(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="mongo_analyst",
        collection_filter=["orders"],
    )
    assert result["summary"]["collections_scanned"] == 1


@pytest.mark.asyncio
async def test_inspect_collection_indexes(mock_adapter, evidence_store):
    result = await inspect_collection_indexes(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="mongo_analyst",
    )
    assert result["summary"]["indexes_checked"] == 3


@pytest.mark.asyncio
async def test_get_replication_status(mock_adapter, evidence_store):
    result = await get_replication_status(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="mongo_analyst",
    )
    assert result["summary"]["is_replica"] is True
    assert result["summary"]["replica_count"] == 2
    assert len(result["summary"]["members"]) == 2
    assert result["summary"]["members"][0]["name"] == "mongo-rs0:27017"


@pytest.mark.asyncio
async def test_query_current_ops_empty(evidence_store):
    """Test with no active operations."""
    adapter = AsyncMock()
    adapter.get_active_queries = AsyncMock(return_value=[])
    result = await query_current_ops(
        adapter=adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="mongo_analyst",
    )
    assert result["summary"]["active_count"] == 0
    assert result["summary"]["slow_count"] == 0


@pytest.mark.asyncio
async def test_get_connection_info_zero_max(evidence_store):
    """Test utilization when max_connections is 0 (avoids division by zero)."""
    adapter = AsyncMock()
    adapter.get_connection_pool = AsyncMock(return_value=MagicMock(
        active=0, idle=0, waiting=0, max_connections=0,
    ))
    result = await get_connection_info(
        adapter=adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="mongo_analyst",
    )
    assert result["summary"]["utilization_pct"] == 0

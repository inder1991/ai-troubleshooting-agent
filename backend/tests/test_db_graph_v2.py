import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.database.graph_v2 import build_db_diagnostic_graph_v2, DBDiagnosticStateV2


@pytest.mark.asyncio
async def test_graph_compiles():
    graph = build_db_diagnostic_graph_v2()
    assert graph is not None


@pytest.mark.asyncio
async def test_connection_validator_fails_gracefully():
    graph = build_db_diagnostic_graph_v2()

    mock_adapter = AsyncMock()
    mock_adapter.health_check = AsyncMock(return_value=MagicMock(
        status="unreachable", error="Connection refused"
    ))

    initial_state: DBDiagnosticStateV2 = {
        "run_id": "R-1",
        "session_id": "S-1",
        "profile_id": "prof-1",
        "profile_name": "test-db",
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "engine": "postgresql",
        "investigation_mode": "standalone",
        "sampling_mode": "standard",
        "focus": ["queries"],
        "status": "running",
        "findings": [],
        "summary": "",
        "_adapter": mock_adapter,
    }

    result = await graph.ainvoke(initial_state)
    assert result["status"] == "failed"
    assert result["connected"] is False


@pytest.mark.asyncio
async def test_graph_works_with_mongo_adapter():
    """The same graph should work with a MongoDB-like adapter."""
    graph = build_db_diagnostic_graph_v2()

    mock_adapter = AsyncMock()
    mock_adapter.health_check = AsyncMock(return_value=MagicMock(
        status="healthy", latency_ms=5.0, version="MongoDB 7.0.4"
    ))
    mock_adapter.check_permissions = AsyncMock(return_value={"serverStatus": True, "currentOp": True})
    mock_adapter.get_active_queries = AsyncMock(return_value=[
        MagicMock(pid=100, query="testdb.orders: {'find': 'orders'}", duration_ms=8000,
                  state="query", user="app", database="testdb", waiting=False),
    ])
    mock_adapter.get_slow_queries_from_stats = AsyncMock(return_value=[])
    mock_adapter.explain_query = AsyncMock(return_value={})
    mock_adapter.get_connection_pool = AsyncMock(return_value=MagicMock(
        active=10, idle=5, waiting=0, max_connections=100
    ))
    mock_adapter.get_performance_stats = AsyncMock(return_value=MagicMock(
        connections_active=10, connections_idle=5, connections_max=100,
        cache_hit_ratio=0.92, transactions_per_sec=500.0, deadlocks=0, uptime_seconds=3600,
    ))
    mock_adapter.get_schema_snapshot = AsyncMock(return_value=MagicMock(tables=[]))

    initial_state: DBDiagnosticStateV2 = {
        "run_id": "R-mongo-1",
        "session_id": "S-mongo-1",
        "profile_id": "prof-mongo",
        "profile_name": "test-mongo",
        "host": "localhost",
        "port": 27017,
        "database": "testdb",
        "engine": "mongodb",
        "investigation_mode": "standalone",
        "sampling_mode": "standard",
        "focus": ["queries", "connections"],
        "status": "running",
        "findings": [],
        "summary": "",
        "_adapter": mock_adapter,
    }

    result = await graph.ainvoke(initial_state)
    assert result["status"] == "completed"
    assert result["connected"] is True
    assert len(result["findings"]) > 0

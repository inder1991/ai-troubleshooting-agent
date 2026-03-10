import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.database.tools.pg_read_tools import (
    run_explain,
    query_pg_stat_statements,
    query_pg_stat_activity,
    query_pg_locks,
    inspect_table_stats,
    inspect_index_usage,
    get_connection_pool,
)
from src.database.evidence_store import EvidenceStore


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.execute_diagnostic_query = AsyncMock(return_value={
        "columns": ["QUERY PLAN"],
        "rows": [['{"Plan": {"Node Type": "Seq Scan"}}']],
        "row_count": 1,
    })
    adapter.get_active_queries = AsyncMock(return_value=[])
    adapter.get_connection_pool = AsyncMock(return_value=MagicMock(
        active=10, idle=5, waiting=0, max_connections=100
    ))
    return adapter


@pytest.fixture
def evidence_store(tmp_path):
    return EvidenceStore(str(tmp_path / "test.db"))


@pytest.mark.asyncio
async def test_run_explain(mock_adapter, evidence_store):
    result = await run_explain(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="query_analyst",
        sql="SELECT * FROM orders WHERE user_id = 1",
    )
    assert "artifact_id" in result
    assert "summary" in result
    mock_adapter.execute_diagnostic_query.assert_called_once()


@pytest.mark.asyncio
async def test_get_connection_pool(mock_adapter, evidence_store):
    result = await get_connection_pool(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="health_analyst",
    )
    assert result["summary"]["active"] == 10
    assert result["summary"]["utilization_pct"] == 10.0

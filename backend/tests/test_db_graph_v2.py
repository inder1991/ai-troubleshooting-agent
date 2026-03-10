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

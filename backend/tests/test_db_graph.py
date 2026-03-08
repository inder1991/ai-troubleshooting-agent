"""Tests for database diagnostic LangGraph graph."""
import pytest


def test_state_defaults():
    from src.agents.database.state import DBDiagnosticState
    state: DBDiagnosticState = {
        "run_id": "r1",
        "profile_id": "p1",
        "engine": "postgresql",
        "status": "running",
        "findings": [],
        "dispatched_agents": [],
    }
    assert state["status"] == "running"
    assert state["findings"] == []
    assert state["dispatched_agents"] == []


def test_graph_compiles():
    from src.agents.database.graph import build_db_diagnostic_graph
    graph = build_db_diagnostic_graph()
    assert graph is not None


def test_graph_runs_with_mock_adapter():
    """Run the full graph with a mock adapter to verify end-to-end."""
    import asyncio
    from src.agents.database.graph import build_db_diagnostic_graph
    from src.database.adapters.mock_adapter import MockDatabaseAdapter

    adapter = MockDatabaseAdapter(
        engine="postgresql", host="localhost", port=5432, database="testdb"
    )

    async def _run():
        await adapter.connect()
        graph = build_db_diagnostic_graph()
        result = graph.invoke({
            "run_id": "test-run",
            "profile_id": "test-profile",
            "engine": "postgresql",
            "status": "running",
            "findings": [],
            "symptoms": [],
            "dispatched_agents": [],
            "summary": "",
            "_adapter": adapter,
        })
        await adapter.disconnect()
        return result

    result = asyncio.run(_run())
    assert result["status"] == "completed"
    assert isinstance(result["findings"], list)
    assert result["summary"]


def test_graph_fails_without_adapter():
    """Graph should fail gracefully when no adapter provided."""
    from src.agents.database.graph import build_db_diagnostic_graph

    graph = build_db_diagnostic_graph()
    result = graph.invoke({
        "run_id": "no-adapter",
        "profile_id": "p1",
        "engine": "postgresql",
        "status": "running",
        "findings": [],
    })
    assert result.get("connected") is False
    assert result.get("status") == "failed"

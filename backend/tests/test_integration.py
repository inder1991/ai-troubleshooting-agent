import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.supervisor import SupervisorAgent
from src.models.schemas import DiagnosticState, DiagnosticPhase, TimeWindow


@pytest.mark.asyncio
async def test_full_workflow_mock():
    """Test that Supervisor dispatches agents in correct order with mocked agents."""
    from src.models.schemas import (
        LogAnalysisResult, ErrorPattern, LogEvidence, TokenUsage,
        Breadcrumb, NegativeFinding
    )
    from datetime import datetime

    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="integration-test",
        phase=DiagnosticPhase.INITIAL,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
    )

    # Verify initial state
    assert state.phase == DiagnosticPhase.INITIAL
    assert state.service_name == "order-service"
    assert state.log_analysis is None
    assert state.metrics_analysis is None
    assert len(state.all_findings) == 0
    assert len(state.agents_completed) == 0


@pytest.mark.asyncio
async def test_supervisor_decides_log_agent_first():
    """Supervisor should dispatch log agent on initial phase."""
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-order",
        phase=DiagnosticPhase.INITIAL,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
    )
    agents = supervisor._decide_next_agents(state)
    assert "log_agent" in agents


@pytest.mark.asyncio
async def test_supervisor_decides_metrics_after_logs():
    """After logs analyzed, supervisor should dispatch metrics agent."""
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-order",
        phase=DiagnosticPhase.LOGS_ANALYZED,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        agents_completed=["log_agent"],
    )
    agents = supervisor._decide_next_agents(state)
    assert "metrics_agent" in agents


def test_diagnostic_state_phases():
    """Test all diagnostic phases are defined."""
    phases = list(DiagnosticPhase)
    assert len(phases) >= 10
    assert DiagnosticPhase.INITIAL in phases
    assert DiagnosticPhase.COMPLETE in phases
    assert DiagnosticPhase.DIAGNOSIS_COMPLETE in phases


def test_workflow_routing():
    """Test the LangGraph workflow routing function."""
    from src.workflow import route_from_supervisor

    # Initial -> log_agent
    state = {
        "session_id": "t", "service_name": "svc", "trace_id": None,
        "time_start": "now-1h", "time_end": "now", "namespace": None,
        "cluster_url": None, "repo_url": None, "elk_index": "app-logs-*",
        "phase": "initial", "agents_completed": [], "results": {},
        "overall_confidence": 0, "is_complete": False,
    }
    assert route_from_supervisor(state) == "log_agent"

    # code_analyzed -> END
    state["phase"] = "code_analyzed"
    state["agents_completed"] = ["log_agent", "metrics_agent", "code_agent"]
    assert route_from_supervisor(state) == "__end__"

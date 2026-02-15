import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.supervisor import SupervisorAgent
from src.models.schemas import DiagnosticState, DiagnosticPhase, TimeWindow, Finding


def test_supervisor_init():
    supervisor = SupervisorAgent()
    assert supervisor.agent_name == "supervisor"
    assert "log_agent" in supervisor._agents
    assert "metrics_agent" in supervisor._agents


def test_initial_dispatch():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.INITIAL,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
    )
    next_agents = supervisor._decide_next_agents(state)
    assert next_agents == ["log_agent"]


def test_dispatch_after_logs():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.LOGS_ANALYZED,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        agents_completed=["log_agent"],
    )
    next_agents = supervisor._decide_next_agents(state)
    assert "metrics_agent" in next_agents


def test_dispatch_parallel_with_k8s():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.LOGS_ANALYZED,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        namespace="prod",
        agents_completed=["log_agent"],
    )
    next_agents = supervisor._decide_next_agents(state)
    assert "metrics_agent" in next_agents
    assert "k8s_agent" in next_agents


def test_dispatch_tracing_after_metrics():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.METRICS_ANALYZED,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        trace_id="abc-123",
        agents_completed=["log_agent", "metrics_agent"],
    )
    next_agents = supervisor._decide_next_agents(state)
    assert "tracing_agent" in next_agents


def test_dispatch_code_agent():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.TRACING_ANALYZED,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        repo_url="/tmp/repo",
        agents_completed=["log_agent", "metrics_agent", "tracing_agent"],
    )
    next_agents = supervisor._decide_next_agents(state)
    assert "code_agent" in next_agents


def test_diagnosis_complete():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.CODE_ANALYZED,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        agents_completed=["log_agent", "metrics_agent", "tracing_agent", "code_agent"],
    )
    next_agents = supervisor._decide_next_agents(state)
    assert next_agents == []


def test_low_confidence_asks_user():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.LOGS_ANALYZED,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        overall_confidence=40,
    )
    action = supervisor._decide_action_for_confidence(state)
    assert action == "ask_user"


def test_high_confidence_proceeds():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.LOGS_ANALYZED,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        overall_confidence=85,
    )
    action = supervisor._decide_action_for_confidence(state)
    assert action == "proceed"


def test_update_phase():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.INITIAL,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        agents_completed=["log_agent", "metrics_agent"],
    )
    supervisor._update_phase(state)
    assert state.phase == DiagnosticPhase.METRICS_ANALYZED

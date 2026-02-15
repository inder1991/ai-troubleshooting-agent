import pytest
from src.workflow import build_workflow, route_from_supervisor, WorkflowState


def test_workflow_has_required_nodes():
    graph = build_workflow()
    node_names = set(graph.nodes.keys())
    assert "supervisor" in node_names
    assert "log_agent" in node_names
    assert "metrics_agent" in node_names
    assert "k8s_agent" in node_names
    assert "tracing_agent" in node_names
    assert "code_agent" in node_names
    assert "critic" in node_names


def test_route_initial():
    state: WorkflowState = {
        "session_id": "t", "service_name": "svc", "trace_id": None,
        "time_start": "now-1h", "time_end": "now", "namespace": None,
        "cluster_url": None, "repo_url": None, "elk_index": "app-logs-*",
        "phase": "initial", "agents_completed": [], "results": {},
        "overall_confidence": 0, "is_complete": False,
    }
    assert route_from_supervisor(state) == "log_agent"


def test_route_after_logs():
    state: WorkflowState = {
        "session_id": "t", "service_name": "svc", "trace_id": None,
        "time_start": "now-1h", "time_end": "now", "namespace": None,
        "cluster_url": None, "repo_url": None, "elk_index": "app-logs-*",
        "phase": "logs_analyzed", "agents_completed": ["log_agent"], "results": {},
        "overall_confidence": 80, "is_complete": False,
    }
    assert route_from_supervisor(state) == "metrics_agent"


def test_route_to_tracing():
    state: WorkflowState = {
        "session_id": "t", "service_name": "svc", "trace_id": "abc-123",
        "time_start": "now-1h", "time_end": "now", "namespace": None,
        "cluster_url": None, "repo_url": None, "elk_index": "app-logs-*",
        "phase": "metrics_analyzed", "agents_completed": ["log_agent", "metrics_agent"],
        "results": {}, "overall_confidence": 80, "is_complete": False,
    }
    assert route_from_supervisor(state) == "tracing_agent"


def test_route_complete():
    state: WorkflowState = {
        "session_id": "t", "service_name": "svc", "trace_id": None,
        "time_start": "now-1h", "time_end": "now", "namespace": None,
        "cluster_url": None, "repo_url": None, "elk_index": "app-logs-*",
        "phase": "code_analyzed", "agents_completed": ["log_agent", "metrics_agent", "code_agent"],
        "results": {}, "overall_confidence": 85, "is_complete": False,
    }
    result = route_from_supervisor(state)
    assert result == "__end__"  # LangGraph END constant

"""code_agent ↔ TracingAgent handoff consumption tests."""
from __future__ import annotations

from src.agents.code_agent import CodeNavigatorAgent


def test_empty_context_no_handoff():
    out = CodeNavigatorAgent._apply_tracing_handoff({})
    assert out == {
        "priority_services": [],
        "failure_service": None,
        "bottleneck_operations": [],
        "any_tracing_data": False,
    }


def test_failure_service_first_in_priority():
    out = CodeNavigatorAgent._apply_tracing_handoff({
        "failure_service_from_trace": "payments",
        "services_from_traces": ["api", "inventory"],
    })
    assert out["priority_services"][0] == "payments"


def test_bottleneck_services_before_hot_before_rest():
    """Ordering: failure → bottleneck services → hot services → rest."""
    out = CodeNavigatorAgent._apply_tracing_handoff({
        "failure_service_from_trace": "payments",
        "bottleneck_operations": [("checkout", "GET /order"), ("inventory", "deduct")],
        "hot_services_from_traces": ["db"],
        "services_from_traces": ["api", "cache"],
    })
    order = out["priority_services"]
    assert order[0] == "payments"
    assert order.index("checkout") < order.index("db")
    assert order.index("inventory") < order.index("db")
    assert order.index("db") < order.index("api")


def test_no_duplicates_in_priority():
    out = CodeNavigatorAgent._apply_tracing_handoff({
        "failure_service_from_trace": "db",
        "hot_services_from_traces": ["db", "cache"],
        "services_from_traces": ["api", "db", "cache"],
    })
    # Each service listed exactly once.
    assert out["priority_services"].count("db") == 1
    assert out["priority_services"].count("cache") == 1


def test_bottleneck_operations_normalized_from_lists():
    """JSON round-trip turns tuples into lists — detector should handle."""
    out = CodeNavigatorAgent._apply_tracing_handoff({
        "bottleneck_operations": [["payments", "authorize"]],
    })
    assert out["bottleneck_operations"] == [("payments", "authorize")]


def test_any_tracing_data_true_with_just_bottlenecks():
    out = CodeNavigatorAgent._apply_tracing_handoff({
        "bottleneck_operations": [("x", "op")],
    })
    assert out["any_tracing_data"] is True


def test_fresh_agent_defaults():
    agent = CodeNavigatorAgent()
    assert agent._tracing_handoff_used is False
    assert agent._tracing_priority_services == []
    assert agent._tracing_failure_service is None
    assert agent._tracing_bottleneck_operations == []


def test_any_tracing_data_true_with_just_failure_service():
    out = CodeNavigatorAgent._apply_tracing_handoff({
        "failure_service_from_trace": "payments",
    })
    assert out["any_tracing_data"] is True
    assert out["priority_services"] == ["payments"]

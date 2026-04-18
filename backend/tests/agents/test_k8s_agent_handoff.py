"""k8s_agent ↔ TracingAgent handoff consumption tests."""
from __future__ import annotations

from src.agents.k8s_agent import K8sAgent


def test_empty_context_no_handoff():
    out = K8sAgent._apply_tracing_handoff({})
    assert out == {
        "scope_services": [],
        "failure_service": None,
        "critical_path": [],
        "any_tracing_data": False,
    }


def test_hot_services_preferred_over_services():
    out = K8sAgent._apply_tracing_handoff({
        "hot_services_from_traces": ["db"],
        "services_from_traces": ["api", "db", "cache"],
    })
    assert out["scope_services"] == ["db"]


def test_falls_back_to_services_when_no_hot():
    out = K8sAgent._apply_tracing_handoff({
        "services_from_traces": ["api", "db"],
    })
    assert out["scope_services"] == ["api", "db"]


def test_failure_service_prepended_to_scope():
    out = K8sAgent._apply_tracing_handoff({
        "services_from_traces": ["api", "cache"],
        "failure_service_from_trace": "payments",
    })
    assert out["scope_services"][0] == "payments"
    assert "api" in out["scope_services"]
    assert out["failure_service"] == "payments"


def test_failure_service_not_duplicated_if_in_scope():
    out = K8sAgent._apply_tracing_handoff({
        "services_from_traces": ["api", "db"],
        "failure_service_from_trace": "db",
    })
    # Should NOT duplicate.
    assert out["scope_services"].count("db") == 1


def test_critical_path_carried_through():
    out = K8sAgent._apply_tracing_handoff({
        "critical_path_services": ["api", "payments", "db"],
    })
    assert out["critical_path"] == ["api", "payments", "db"]
    assert out["any_tracing_data"] is True


def test_fresh_agent_has_handoff_flag_false():
    agent = K8sAgent()
    assert agent._tracing_handoff_used is False
    assert agent._tracing_scope_services == []
    assert agent._tracing_failure_service is None
    assert agent._tracing_critical_path == []


def test_any_tracing_data_true_when_scope_only():
    out = K8sAgent._apply_tracing_handoff({"services_from_traces": ["api"]})
    assert out["any_tracing_data"] is True


def test_any_tracing_data_true_when_critical_path_only():
    out = K8sAgent._apply_tracing_handoff({"critical_path_services": ["a", "b"]})
    assert out["any_tracing_data"] is True

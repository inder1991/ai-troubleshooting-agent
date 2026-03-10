import pytest
from src.agents.supervisor import SupervisorAgent


class TestFindingToNodeType:
    """Test the _finding_to_node_type mapping."""

    def test_log_agent(self):
        assert SupervisorAgent._finding_to_node_type("log_agent", {"category": "error"}) == "error_event"

    def test_metrics_agent(self):
        assert SupervisorAgent._finding_to_node_type("metrics_agent", {}) == "metric_anomaly"

    def test_k8s_agent(self):
        assert SupervisorAgent._finding_to_node_type("k8s_agent", {}) == "k8s_event"

    def test_tracing_agent(self):
        assert SupervisorAgent._finding_to_node_type("tracing_agent", {}) == "trace_span"

    def test_code_agent(self):
        assert SupervisorAgent._finding_to_node_type("code_agent", {}) == "code_location"

    def test_change_agent(self):
        assert SupervisorAgent._finding_to_node_type("change_agent", {}) == "code_change"

    def test_unknown_defaults_to_error_event(self):
        assert SupervisorAgent._finding_to_node_type("unknown_agent", {}) == "error_event"

import pytest
from src.agents.critic_ensemble import DeterministicValidator

class TestDeterministicValidator:
    def setup_method(self):
        self.validator = DeterministicValidator()

    def test_pass_when_valid(self):
        pin = {"claim": "OOMKilled in payment pod", "source_agent": "k8s_agent", "timestamp": 1710000100, "causal_role": "root_cause"}
        graph_nodes = {"n-001": {"timestamp": 1710000000, "node_type": "error_event"}, "n-002": {"timestamp": 1710000200, "node_type": "metric_anomaly"}}
        graph_edges = [("n-001", "n-002", {"edge_type": "causes"})]
        result = self.validator.validate(pin, graph_nodes, graph_edges, [])
        assert result["status"] == "pass"

    def test_reject_missing_claim(self):
        pin = {"claim": "", "source_agent": "k8s_agent"}
        result = self.validator.validate(pin, {}, [], [])
        assert result["status"] == "hard_reject"
        assert "schema_incomplete" in result["violations"]

    def test_reject_missing_source_agent(self):
        pin = {"claim": "some claim", "source_agent": ""}
        result = self.validator.validate(pin, {}, [], [])
        assert result["status"] == "hard_reject"
        assert "schema_incomplete" in result["violations"]

    def test_reject_temporal_violation(self):
        pin = {"claim": "Pod caused etcd failure", "source_agent": "k8s_agent", "timestamp": 1710000300, "caused_node_id": "n-effect"}
        graph_nodes = {"n-effect": {"timestamp": 1710000100, "node_type": "error_event"}}
        result = self.validator.validate(pin, graph_nodes, [], [])
        assert result["status"] == "hard_reject"
        assert "temporal_violation" in result["violations"]

    def test_reject_contradiction(self):
        pin = {"claim": "Service A is healthy", "source_agent": "k8s_agent", "service": "service-a", "causal_role": "informational"}
        existing = [{"claim": "Service A is failing with OOMKilled", "source_agent": "k8s_agent", "service": "service-a", "validation_status": "validated", "causal_role": "root_cause", "pin_id": "p-001"}]
        result = self.validator.validate(pin, {}, [], existing)
        assert result["status"] == "hard_reject"
        assert any("contradicts" in v for v in result["violations"])

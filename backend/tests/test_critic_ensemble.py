import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.critic_ensemble import DeterministicValidator, EnsembleCritic

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


class TestEnsembleCritic:
    def setup_method(self):
        self.mock_llm = MagicMock()
        self.critic = EnsembleCritic(llm_client=self.mock_llm)

    def test_hard_reject_skips_llm(self):
        finding = {"claim": "", "source_agent": ""}
        state = {"all_findings": []}
        graph = {"nodes": {}, "edges": []}
        result = asyncio.run(
            self.critic.validate(finding, state, graph)
        )
        assert result["verdict"] == "challenged"
        self.mock_llm.chat.assert_not_called()

    @patch("src.agents.critic_ensemble.EnsembleCritic._run_evidence_retriever")
    def test_full_debate_calls_four_roles(self, mock_retriever):
        mock_retriever.return_value = "No additional evidence."
        self.mock_llm.chat = AsyncMock(side_effect=[
            "The finding is valid because...",
            "However, there are concerns...",
            '{"verdict":"validated","confidence":0.82,"causal_role":"root_cause",'
            '"reasoning":"Valid","supporting_evidence":[],"contradictions":[],"graph_edges":[]}',
        ])
        finding = {
            "claim": "OOMKilled in payment pod",
            "source_agent": "k8s_agent",
            "timestamp": 1710000100,
        }
        state = {"all_findings": [finding]}
        graph = {"nodes": {}, "edges": []}
        result = asyncio.run(
            self.critic.validate(finding, state, graph)
        )
        assert result["verdict"] == "validated"
        assert result["confidence"] == 0.82
        assert self.mock_llm.chat.call_count == 3
        mock_retriever.assert_called_once()

    def test_parse_judge_output_valid_json(self):
        raw = '{"verdict":"challenged","confidence":0.4,"causal_role":"correlated","reasoning":"Weak evidence","supporting_evidence":[],"contradictions":["metric data missing"],"graph_edges":[]}'
        result = self.critic._parse_judge_output(raw)
        assert result["verdict"] == "challenged"
        assert result["confidence"] == 0.4

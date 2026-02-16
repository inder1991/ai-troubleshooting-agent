import pytest
from datetime import datetime
from src.agents.react_base import ReActAgent
from src.models.schemas import EvidencePin


class ConcreteAgent(ReActAgent):
    """Minimal concrete implementation for testing."""
    async def _define_tools(self): return []
    async def _build_system_prompt(self): return "test"
    async def _build_initial_prompt(self, context): return "test"
    async def _handle_tool_call(self, tool_name, tool_input): return "result"
    def _parse_final_response(self, text): return {"test": True}


class TestEvidencePinning:
    def test_agent_has_evidence_pins_list(self):
        agent = ConcreteAgent("test_agent")
        assert hasattr(agent, "evidence_pins")
        assert agent.evidence_pins == []

    def test_add_evidence_pin(self):
        agent = ConcreteAgent("test_agent")
        pin = agent.add_evidence_pin(
            claim="Found connection timeout",
            supporting_evidence=["ERROR at line 42"],
            source_tool="elasticsearch",
            confidence=0.85,
            evidence_type="log",
        )
        assert len(agent.evidence_pins) == 1
        assert pin.source_agent == "test_agent"
        assert pin.confidence == 0.85
        assert isinstance(pin, EvidencePin)

    def test_add_multiple_pins(self):
        agent = ConcreteAgent("test_agent")
        agent.add_evidence_pin(claim="pin1", supporting_evidence=[], source_tool="elk", confidence=0.8, evidence_type="log")
        agent.add_evidence_pin(claim="pin2", supporting_evidence=[], source_tool="prometheus", confidence=0.9, evidence_type="metric")
        assert len(agent.evidence_pins) == 2

    def test_pin_uses_agent_name_as_source(self):
        agent = ConcreteAgent("my_custom_agent")
        pin = agent.add_evidence_pin(claim="test", supporting_evidence=[], source_tool="t", confidence=0.5, evidence_type="code")
        assert pin.source_agent == "my_custom_agent"

    def test_pin_has_timestamp(self):
        agent = ConcreteAgent("test_agent")
        pin = agent.add_evidence_pin(claim="test", supporting_evidence=[], source_tool="t", confidence=0.5, evidence_type="trace")
        assert pin.timestamp is not None

    def test_parse_final_response_baseline(self):
        agent = ConcreteAgent("test_agent")
        agent.add_evidence_pin(claim="test", supporting_evidence=["ev"], source_tool="elk", confidence=0.7, evidence_type="log")
        result = agent._parse_final_response("text")
        # Note: _parse_final_response itself doesn't add pins - run() does. This just tests baseline.
        assert result == {"test": True}

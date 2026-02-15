import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.react_base import ReActAgent
from src.models.schemas import Breadcrumb, NegativeFinding


class ConcreteTestAgent(ReActAgent):
    """Concrete implementation for testing."""

    async def _define_tools(self):
        return [{"name": "search_logs", "description": "Search logs", "input_schema": {"type": "object", "properties": {}}}]

    async def _build_system_prompt(self):
        return "You are a test agent."

    async def _build_initial_prompt(self, context):
        return f"Analyze: {context.get('query', 'test')}"

    async def _handle_tool_call(self, tool_name, tool_input):
        return "tool result"

    def _parse_final_response(self, text):
        return {"result": text}


def test_react_agent_init():
    agent = ConcreteTestAgent(agent_name="test_agent")
    assert agent.agent_name == "test_agent"
    assert agent.max_iterations == 10
    assert len(agent.breadcrumbs) == 0
    assert len(agent.negative_findings) == 0


def test_add_breadcrumb():
    agent = ConcreteTestAgent(agent_name="test_agent")
    agent.add_breadcrumb(
        action="searched_logs",
        source_type="log",
        source_reference="app-logs-2025",
        raw_evidence="ConnectionTimeout after 30s"
    )
    assert len(agent.breadcrumbs) == 1
    assert agent.breadcrumbs[0].agent_name == "test_agent"
    assert agent.breadcrumbs[0].source_type == "log"
    assert isinstance(agent.breadcrumbs[0], Breadcrumb)


def test_add_negative_finding():
    agent = ConcreteTestAgent(agent_name="test_agent")
    agent.add_negative_finding(
        what_was_checked="DB logs for trace abc-123",
        result="Zero errors found",
        implication="Issue is NOT in DB layer",
        source_reference="db-logs-2025"
    )
    assert len(agent.negative_findings) == 1
    assert agent.negative_findings[0].agent_name == "test_agent"
    assert isinstance(agent.negative_findings[0], NegativeFinding)


def test_get_token_usage():
    agent = ConcreteTestAgent(agent_name="test_agent")
    usage = agent.get_token_usage()
    assert usage.agent_name == "test_agent"
    assert usage.total_tokens == 0


def test_multiple_breadcrumbs():
    agent = ConcreteTestAgent(agent_name="test_agent")
    agent.add_breadcrumb("action1", "log", "ref1", "evidence1")
    agent.add_breadcrumb("action2", "metric", "ref2", "evidence2")
    agent.add_breadcrumb("action3", "code", "ref3", "evidence3")
    assert len(agent.breadcrumbs) == 3
    assert agent.breadcrumbs[1].source_type == "metric"

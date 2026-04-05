"""Tests for LLM client logging."""


def test_anthropic_client_accepts_session_id():
    from src.utils.llm_client import AnthropicClient
    client = AnthropicClient(agent_name="test", session_id="sess-123")
    assert client.session_id == "sess-123"


def test_anthropic_client_session_id_defaults_empty():
    from src.utils.llm_client import AnthropicClient
    client = AnthropicClient(agent_name="test")
    assert client.session_id == ""

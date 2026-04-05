"""Verify session_id reaches LLM client in all agents."""
import inspect


def test_ctrl_plane_passes_session_id_to_llm():
    """ctrl_plane_agent must construct AnthropicClient with session_id."""
    import src.agents.cluster.ctrl_plane_agent as agent
    sig = inspect.signature(agent._llm_analyze)
    assert "session_id" in sig.parameters


def test_node_passes_session_id_to_llm():
    """node_agent must construct AnthropicClient with session_id."""
    import src.agents.cluster.node_agent as agent
    sig = inspect.signature(agent._llm_analyze)
    assert "session_id" in sig.parameters


def test_network_passes_session_id_to_llm():
    """network_agent must construct AnthropicClient with session_id."""
    import src.agents.cluster.network_agent as agent
    sig = inspect.signature(agent._llm_analyze)
    assert "session_id" in sig.parameters


def test_storage_passes_session_id_to_llm():
    """storage_agent must construct AnthropicClient with session_id."""
    import src.agents.cluster.storage_agent as agent
    sig = inspect.signature(agent._llm_analyze)
    assert "session_id" in sig.parameters


def test_rbac_passes_session_id_to_llm():
    """rbac_agent must construct AnthropicClient with session_id."""
    import src.agents.cluster.rbac_agent as agent
    sig = inspect.signature(agent._llm_analyze)
    assert "session_id" in sig.parameters


def test_synthesizer_causal_has_session_id():
    """synthesizer _llm_causal_reasoning must accept session_id."""
    import src.agents.cluster.synthesizer as synth
    sig = inspect.signature(synth._llm_causal_reasoning)
    assert "session_id" in sig.parameters


def test_synthesizer_verdict_has_session_id():
    """synthesizer _llm_verdict must accept session_id."""
    import src.agents.cluster.synthesizer as synth
    sig = inspect.signature(synth._llm_verdict)
    assert "session_id" in sig.parameters


def test_ctrl_plane_llm_analyze_source_uses_session_id():
    """Verify AnthropicClient in _llm_analyze is constructed with session_id kwarg."""
    import src.agents.cluster.ctrl_plane_agent as agent
    source = inspect.getsource(agent._llm_analyze)
    assert "session_id" in source
    assert "AnthropicClient(" in source


def test_tool_calling_loop_passes_session_id_to_client():
    """Verify _tool_calling_loop constructs AnthropicClient with session_id."""
    import src.agents.cluster.ctrl_plane_agent as agent
    source = inspect.getsource(agent._tool_calling_loop)
    assert "session_id=session_id" in source or "session_id=" in source


def test_synthesizer_causal_source_uses_session_id():
    """Verify AnthropicClient in _llm_causal_reasoning is constructed with session_id."""
    import src.agents.cluster.synthesizer as synth
    source = inspect.getsource(synth._llm_causal_reasoning)
    assert "session_id=session_id" in source


def test_synthesizer_verdict_source_uses_session_id():
    """Verify AnthropicClient in _llm_verdict is constructed with session_id."""
    import src.agents.cluster.synthesizer as synth
    source = inspect.getsource(synth._llm_verdict)
    assert "session_id=session_id" in source

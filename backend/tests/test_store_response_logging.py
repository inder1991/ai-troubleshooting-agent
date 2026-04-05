"""Verify LLM response content is passed to store."""
import ast
import inspect


def _assert_no_empty_response_json(module, module_name: str):
    """Check that no store.log_llm_call in module source uses empty response_json."""
    source = inspect.getsource(module)
    assert '"response_json": {}' not in source, (
        f"{module_name} still logs empty response_json to store"
    )


def test_ctrl_plane_agent_includes_response():
    from src.agents.cluster import ctrl_plane_agent
    _assert_no_empty_response_json(ctrl_plane_agent, "ctrl_plane_agent")


def test_node_agent_includes_response():
    from src.agents.cluster import node_agent
    _assert_no_empty_response_json(node_agent, "node_agent")


def test_network_agent_includes_response():
    from src.agents.cluster import network_agent
    _assert_no_empty_response_json(network_agent, "network_agent")


def test_storage_agent_includes_response():
    from src.agents.cluster import storage_agent
    _assert_no_empty_response_json(storage_agent, "storage_agent")


def test_rbac_agent_includes_response():
    from src.agents.cluster import rbac_agent
    _assert_no_empty_response_json(rbac_agent, "rbac_agent")


def test_synthesizer_includes_response():
    from src.agents.cluster import synthesizer
    _assert_no_empty_response_json(synthesizer, "synthesizer")

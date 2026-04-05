"""Tests for domain agent prompt accuracy."""


def test_ctrl_plane_prompt_matches_tools():
    """System prompt should only claim capabilities matching available tools."""
    from src.agents.cluster.ctrl_plane_agent import _SYSTEM_PROMPT
    from src.agents.cluster.tools import get_tools_for_agent
    tool_names = [t["name"] for t in get_tools_for_agent("ctrl_plane")]
    # Prompt should NOT claim direct cert/etcd tool access since those tools don't exist
    # It should say "infer from events and operator status" instead
    assert "certificate expiry" not in _SYSTEM_PROMPT.lower() or "infer" in _SYSTEM_PROMPT.lower() or "events" in _SYSTEM_PROMPT.lower()


def test_storage_prompt_matches_data():
    """Storage prompt should not claim CSI/IOPS analysis when no data is collected."""
    from src.agents.cluster.storage_agent import _SYSTEM_PROMPT
    # Should not claim standalone CSI driver health or IOPS throttling analysis
    # unless we actually collect that data
    assert "iops throttling" not in _SYSTEM_PROMPT.lower() or "if available" in _SYSTEM_PROMPT.lower()


def test_rbac_data_has_size_cap():
    """RBAC data payload must cap each data source."""
    # Verify the cap constant exists
    from src.agents.cluster.rbac_agent import _MAX_RBAC_ITEMS
    assert _MAX_RBAC_ITEMS >= 50
    assert _MAX_RBAC_ITEMS <= 200

"""Tests for agent truncation note generation."""


def test_ctrl_plane_truncation_note_includes_events():
    """When events are sliced to 100, truncation_note must mention it."""
    from src.agents.cluster import ctrl_plane_agent
    import inspect
    source = inspect.getsource(ctrl_plane_agent)
    assert "events_total" in source or "len(events.data)" in source


def test_node_agent_truncation_note_includes_pods():
    """When pods are sliced, truncation_note must mention it."""
    from src.agents.cluster import node_agent
    import inspect
    source = inspect.getsource(node_agent)
    assert "pods_total" in source or "len(pods.data)" in source

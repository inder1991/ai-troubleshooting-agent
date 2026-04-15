"""Tests for platform-layer tool schemas and subsets."""

from src.agents.cluster.tools import CLUSTER_TOOLS, CTRL_PLANE_TOOLS, get_tools_for_agent


def _tool_names():
    return [t["name"] for t in CLUSTER_TOOLS]


def test_cluster_tools_has_get_cluster_version():
    assert "get_cluster_version" in _tool_names()


def test_cluster_tools_has_list_subscriptions():
    assert "list_subscriptions" in _tool_names()


def test_cluster_tools_has_list_csvs():
    assert "list_csvs" in _tool_names()


def test_cluster_tools_has_list_install_plans():
    assert "list_install_plans" in _tool_names()


def test_cluster_tools_has_list_machines():
    assert "list_machines" in _tool_names()


def test_cluster_tools_has_get_proxy_config():
    assert "get_proxy_config" in _tool_names()


def test_ctrl_plane_tools_includes_platform_tools():
    for tool in ("get_cluster_version", "list_subscriptions", "list_csvs",
                 "list_install_plans", "list_machines", "get_proxy_config"):
        assert tool in CTRL_PLANE_TOOLS, f"{tool} missing from CTRL_PLANE_TOOLS"


def test_get_tools_for_agent_ctrl_plane_returns_platform_tools():
    tools = get_tools_for_agent("ctrl_plane")
    names = [t["name"] for t in tools]
    for tool in ("get_cluster_version", "list_subscriptions", "list_csvs",
                 "list_install_plans", "list_machines", "get_proxy_config"):
        assert tool in names, f"{tool} missing from ctrl_plane agent tools"

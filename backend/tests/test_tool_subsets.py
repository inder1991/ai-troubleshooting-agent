"""Tests for updated agent tool subsets."""

from src.agents.cluster.tools import CTRL_PLANE_TOOLS, NETWORK_TOOLS, CLUSTER_TOOLS, get_tools_for_agent


def test_ctrl_plane_has_list_deployments():
    assert "list_deployments" in CTRL_PLANE_TOOLS


def test_ctrl_plane_has_list_pods():
    assert "list_pods" in CTRL_PLANE_TOOLS


def test_network_has_list_routes():
    assert "list_routes" in NETWORK_TOOLS


def test_network_has_list_ingresses():
    assert "list_ingresses" in NETWORK_TOOLS


def test_cluster_tools_has_list_routes_schema():
    names = [t["name"] for t in CLUSTER_TOOLS]
    assert "list_routes" in names


def test_cluster_tools_has_list_ingresses_schema():
    names = [t["name"] for t in CLUSTER_TOOLS]
    assert "list_ingresses" in names


def test_cluster_tools_has_list_webhooks_schema():
    names = [t["name"] for t in CLUSTER_TOOLS]
    assert "list_webhooks" in names


def test_get_tools_for_ctrl_plane_includes_new_tools():
    tools = get_tools_for_agent("ctrl_plane")
    tool_names = [t["name"] for t in tools]
    assert "list_deployments" in tool_names
    assert "list_pods" in tool_names

# backend/tests/test_network_tool_registry.py
import pytest
from src.agents.network.tool_registry import NetworkToolRegistry


class TestToolRegistry:
    def test_get_tools_for_observatory(self):
        tools = NetworkToolRegistry.get_tools_for_view("observatory")
        tool_names = {t["name"] for t in tools}
        # Observatory should have flow, alert, device, diagnostic, and shared tools
        assert "get_top_talkers" in tool_names
        assert "get_active_alerts" in tool_names
        assert "get_device_health" in tool_names
        assert "diagnose_path" in tool_names
        assert "summarize_context" in tool_names  # shared

    def test_get_tools_for_topology(self):
        tools = NetworkToolRegistry.get_tools_for_view("network-topology")
        tool_names = {t["name"] for t in tools}
        assert "get_topology_graph" in tool_names
        assert "evaluate_rule" in tool_names
        assert "diagnose_path" in tool_names

    def test_get_tools_for_ipam(self):
        tools = NetworkToolRegistry.get_tools_for_view("ipam")
        tool_names = {t["name"] for t in tools}
        assert "search_ip" in tool_names
        assert "get_subnet_utilization" in tool_names

    def test_get_all_tools_for_investigation(self):
        tools = NetworkToolRegistry.get_all_tools()
        tool_names = {t["name"] for t in tools}
        # Should include tools from all groups
        assert "get_top_talkers" in tool_names
        assert "get_topology_graph" in tool_names
        assert "search_ip" in tool_names
        assert "get_bgp_neighbors" in tool_names

    def test_tool_has_valid_schema(self):
        tools = NetworkToolRegistry.get_tools_for_view("observatory")
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_unknown_view_returns_shared_only(self):
        tools = NetworkToolRegistry.get_tools_for_view("unknown-view")
        tool_names = {t["name"] for t in tools}
        assert "summarize_context" in tool_names
        assert len(tool_names) == 2  # shared tools only

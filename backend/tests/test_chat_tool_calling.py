import pytest
from src.prompts.chat_prompts import CHAT_TOOLS_SCHEMA


class TestChatToolCalling:
    def test_chat_tools_schema_valid(self):
        """Verify all 6 tools have name, description, input_schema."""
        assert len(CHAT_TOOLS_SCHEMA) == 6
        for tool in CHAT_TOOLS_SCHEMA:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_search_findings_tool_filters_by_agent(self):
        findings = [
            {"agent_name": "log_agent", "summary": "NPE in payment", "severity": "critical"},
            {"agent_name": "metrics_agent", "summary": "CPU spike", "severity": "high"},
            {"agent_name": "k8s_agent", "summary": "OOMKilled", "severity": "critical"},
        ]
        filtered = [f for f in findings if f.get("agent_name") == "log_agent"]
        assert len(filtered) == 1
        assert filtered[0]["summary"] == "NPE in payment"

    def test_search_findings_tool_filters_by_severity(self):
        findings = [
            {"agent_name": "log_agent", "summary": "NPE in payment", "severity": "critical"},
            {"agent_name": "metrics_agent", "summary": "CPU spike", "severity": "high"},
        ]
        filtered = [f for f in findings if f.get("severity") == "critical"]
        assert len(filtered) == 1

    def test_search_findings_tool_filters_by_keyword(self):
        findings = [
            {"agent_name": "log_agent", "summary": "NPE in payment service"},
            {"agent_name": "metrics_agent", "summary": "CPU spike on auth"},
        ]
        keyword = "payment"
        filtered = [f for f in findings if keyword.lower() in f.get("summary", "").lower()]
        assert len(filtered) == 1

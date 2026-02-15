import pytest
from src.agents.log_agent import LogAnalysisAgent


def test_log_agent_init():
    agent = LogAnalysisAgent()
    assert agent.agent_name == "log_agent"
    assert agent.max_iterations == 8


def test_parse_patterns_groups_by_exception():
    agent = LogAnalysisAgent()
    logs = [
        {"level": "ERROR", "message": "ConnectionTimeout after 30s", "service": "order-service", "timestamp": "2025-12-26T14:00:33"},
        {"level": "ERROR", "message": "ConnectionTimeout after 25s", "service": "order-service", "timestamp": "2025-12-26T14:00:34"},
        {"level": "ERROR", "message": "ConnectionTimeout after 30s", "service": "payment-service", "timestamp": "2025-12-26T14:00:35"},
        {"level": "ERROR", "message": "NullPointerException at line 45 in UserService.java", "service": "user-service", "timestamp": "2025-12-26T14:00:36"},
    ]
    patterns = agent._parse_patterns_from_logs(logs)
    assert len(patterns) >= 2
    # ConnectionTimeout should be grouped together
    ct_pattern = next((p for p in patterns if p["exception_type"] == "ConnectionTimeout"), None)
    assert ct_pattern is not None
    assert ct_pattern["frequency"] == 3
    # NullPointerException should be separate
    npe_pattern = next((p for p in patterns if p["exception_type"] == "NullPointerException"), None)
    assert npe_pattern is not None
    assert npe_pattern["frequency"] == 1


def test_parse_patterns_sorted_by_frequency():
    agent = LogAnalysisAgent()
    logs = [
        {"level": "ERROR", "message": "NullPointerException", "service": "svc-a"},
        {"level": "ERROR", "message": "ConnectionTimeout after 30s", "service": "svc-b"},
        {"level": "ERROR", "message": "ConnectionTimeout after 25s", "service": "svc-b"},
        {"level": "ERROR", "message": "ConnectionTimeout after 30s", "service": "svc-c"},
    ]
    patterns = agent._parse_patterns_from_logs(logs)
    assert patterns[0]["frequency"] >= patterns[-1]["frequency"]


def test_extract_exception_type():
    agent = LogAnalysisAgent()
    assert agent._extract_exception_type("java.lang.NullPointerException at line 45") == "NullPointerException"
    assert agent._extract_exception_type("ConnectionTimeout after 30000ms") == "ConnectionTimeout"
    assert agent._extract_exception_type("some random error message") == "UnknownError"
    assert agent._extract_exception_type("request timeout after 5s") == "Timeout"


def test_extract_pattern_key_normalizes():
    agent = LogAnalysisAgent()
    key1 = agent._extract_pattern_key("ConnectionTimeout after 30s at 2025-12-26T14:00:33Z")
    key2 = agent._extract_pattern_key("ConnectionTimeout after 25s at 2025-12-26T15:00:00Z")
    # Both should extract "ConnectionTimeout" as the key
    assert key1 == key2 == "ConnectionTimeout"


def test_extract_pattern_key_uuid_removal():
    agent = LogAnalysisAgent()
    key1 = agent._extract_pattern_key("Failed processing request 550e8400-e29b-41d4-a716-446655440000")
    key2 = agent._extract_pattern_key("Failed processing request a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    assert key1 == key2


def test_analyze_patterns_tool_empty():
    agent = LogAnalysisAgent()
    result = agent._analyze_patterns_tool()
    import json
    data = json.loads(result)
    assert data["patterns"] == []


def test_affected_components_tracked():
    agent = LogAnalysisAgent()
    logs = [
        {"level": "ERROR", "message": "ConnectionTimeout after 30s", "service": "order-service"},
        {"level": "ERROR", "message": "ConnectionTimeout after 30s", "service": "payment-service"},
    ]
    patterns = agent._parse_patterns_from_logs(logs)
    ct_pattern = next(p for p in patterns if p["exception_type"] == "ConnectionTimeout")
    assert "order-service" in ct_pattern["affected_components"]
    assert "payment-service" in ct_pattern["affected_components"]

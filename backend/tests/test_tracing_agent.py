import pytest
from src.agents.tracing_agent import TracingAgent


def test_tracing_agent_init():
    agent = TracingAgent()
    assert agent.agent_name == "tracing_agent"


def test_should_fallback_to_elk_none():
    assert TracingAgent._should_fallback_to_elk(None) is True


def test_should_fallback_to_elk_empty_data():
    assert TracingAgent._should_fallback_to_elk({"data": []}) is True


def test_should_fallback_to_elk_empty_spans():
    assert TracingAgent._should_fallback_to_elk({"data": [{"spans": []}]}) is True


def test_should_not_fallback_with_spans():
    assert TracingAgent._should_fallback_to_elk({"data": [{"spans": [{"spanID": "s1"}]}]}) is False


def test_reconstruct_chain_from_logs():
    logs = [
        {"timestamp": "2025-12-26T14:00:01Z", "service": "api-gateway", "message": "Received request", "level": "INFO", "trace_id": "abc"},
        {"timestamp": "2025-12-26T14:00:02Z", "service": "order-service", "message": "Processing order", "level": "INFO", "trace_id": "abc"},
        {"timestamp": "2025-12-26T14:00:03Z", "service": "inventory-service", "message": "Checking stock", "level": "INFO", "trace_id": "abc"},
        {"timestamp": "2025-12-26T14:00:33Z", "service": "inventory-service", "message": "ConnectionTimeout to postgres", "level": "ERROR", "trace_id": "abc"},
    ]
    chain = TracingAgent._reconstruct_chain_from_logs(logs)
    assert len(chain) == 4
    assert chain[0]["service_name"] == "api-gateway"
    assert chain[0]["status"] == "ok"
    assert chain[-1]["status"] == "error"
    assert chain[-1]["service_name"] == "inventory-service"


def test_reconstruct_chain_empty():
    assert TracingAgent._reconstruct_chain_from_logs([]) == []


def test_reconstruct_chain_timeout_detection():
    logs = [
        {"timestamp": "2025-12-26T14:00:01Z", "service": "svc-a", "message": "Request timeout after 30s", "level": "WARN", "trace_id": "x"},
    ]
    chain = TracingAgent._reconstruct_chain_from_logs(logs)
    assert chain[0]["status"] == "timeout"


def test_parse_jaeger_spans():
    jaeger_response = {
        "data": [{
            "processes": {"p1": {"serviceName": "order-service"}, "p2": {"serviceName": "db-service"}},
            "spans": [
                {"spanID": "s1", "processID": "p1", "operationName": "processOrder", "duration": 5000000,
                 "tags": [], "references": []},
                {"spanID": "s2", "processID": "p2", "operationName": "query", "duration": 31000000,
                 "tags": [{"key": "error", "value": True}, {"key": "error.message", "value": "timeout"}],
                 "references": [{"spanID": "s1"}]},
            ],
        }]
    }
    spans = TracingAgent._parse_jaeger_spans(jaeger_response)
    assert len(spans) == 2
    assert spans[0]["service_name"] == "order-service"
    assert spans[0]["status"] == "ok"
    assert spans[1]["service_name"] == "db-service"
    assert spans[1]["status"] == "timeout"
    assert spans[1]["error_message"] == "timeout"
    assert spans[1]["parent_span_id"] == "s1"


def test_new_service_flag_in_chain():
    logs = [
        {"timestamp": "1", "service": "svc-a", "message": "msg1", "level": "INFO"},
        {"timestamp": "2", "service": "svc-b", "message": "msg2", "level": "INFO"},
        {"timestamp": "3", "service": "svc-a", "message": "msg3", "level": "INFO"},
    ]
    chain = TracingAgent._reconstruct_chain_from_logs(logs)
    assert chain[0]["is_new_service"] is True
    assert chain[1]["is_new_service"] is True
    assert chain[2]["is_new_service"] is False  # svc-a seen before

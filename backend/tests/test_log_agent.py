import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.agents.log_agent import LogAnalysisAgent


# ─── Init / basics ────────────────────────────────────────────────────────────

def test_log_agent_init():
    agent = LogAnalysisAgent()
    assert agent.agent_name == "log_agent"
    assert agent._raw_logs == []
    assert agent._patterns == []
    assert agent._service_flow == []


def test_log_agent_init_with_connection_config():
    config = MagicMock()
    config.elasticsearch_url = "http://es-custom:9200"
    config.elasticsearch_auth_method = "token"
    config.elasticsearch_credentials = "my-token"
    agent = LogAnalysisAgent(connection_config=config)
    assert agent.es_url == "http://es-custom:9200"
    assert "Authorization" in agent._es_headers
    assert agent._es_headers["Authorization"] == "Bearer my-token"


def test_log_agent_init_default_es_url():
    agent = LogAnalysisAgent()
    # Falls back to env var or default
    assert "localhost" in agent.es_url or "ELASTICSEARCH" in agent.es_url or agent.es_url


# ─── Pattern Detection (deterministic, no mocks needed) ───────────────────────

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
    ct_pattern = next((p for p in patterns if p["exception_type"] == "ConnectionTimeout"), None)
    assert ct_pattern is not None
    assert ct_pattern["frequency"] == 3
    npe_pattern = next((p for p in patterns if p["exception_type"] == "NullPointerException"), None)
    assert npe_pattern is not None
    assert npe_pattern["frequency"] == 1


def test_parse_patterns_sorted_by_severity_then_frequency():
    """Patterns sort by severity rank first (critical > high > medium > low), then frequency descending."""
    agent = LogAnalysisAgent()
    logs = [
        # 40x low-severity deprecation warnings — _extract_exception_type returns "UnknownError"
        # but _classify_pattern_severity detects "deprecated" keyword → low severity
        *[{"level": "ERROR", "message": "deprecated header format overdue migration", "service": "svc-a"} for _ in range(40)],
        # 6x critical ConnectError (low frequency, critical priority)
        *[{"level": "ERROR", "message": "ConnectError: connection refused to database", "service": "svc-b"} for _ in range(6)],
        # 21x high-severity RedisTimeout
        *[{"level": "ERROR", "message": "RedisTimeout after 5s on cache lookup", "service": "svc-c"} for _ in range(21)],
    ]
    patterns = agent._parse_patterns_from_logs(logs)
    assert len(patterns) == 3
    # Critical sorts first despite having lowest frequency
    assert patterns[0]["exception_type"] == "ConnectError"
    assert patterns[0]["severity"] == "critical"
    # High sorts second
    assert patterns[1]["exception_type"] == "RedisTimeout"
    assert patterns[1]["severity"] == "high"
    # Low sorts last despite having highest frequency (40x)
    assert patterns[2]["severity"] == "low"
    assert patterns[2]["frequency"] == 40


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
    assert key1 == key2 == "ConnectionTimeout"


def test_extract_pattern_key_uuid_removal():
    agent = LogAnalysisAgent()
    key1 = agent._extract_pattern_key("Failed processing request 550e8400-e29b-41d4-a716-446655440000")
    key2 = agent._extract_pattern_key("Failed processing request a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    assert key1 == key2


def test_classify_pattern_severity():
    """Severity classification covers known types, 5xx codes, and deprecation heuristic."""
    agent = LogAnalysisAgent()
    # Known critical type
    assert agent._classify_pattern_severity("ConnectError", "") == "critical"
    # Known high type
    assert agent._classify_pattern_severity("RedisTimeout", "") == "high"
    # Known medium type
    assert agent._classify_pattern_severity("AuthenticationError", "") == "medium"
    # Known low type
    assert agent._classify_pattern_severity("DeprecationWarning", "") == "low"
    # UnknownError with deprecation keyword → low
    assert agent._classify_pattern_severity("UnknownError", "deprecated header format") == "low"
    # 5xx in error message → critical
    assert agent._classify_pattern_severity("SomeError", "HTTP 503 Service Unavailable") == "critical"
    # Unknown type, no special keywords → medium default
    assert agent._classify_pattern_severity("SomeRandomError", "some message") == "medium"


def test_build_cross_service_correlations():
    """Traces spanning multiple services produce correlation entries."""
    agent = LogAnalysisAgent()
    raw_logs = [
        {"trace_id": "trace-1", "service": "checkout-service", "level": "INFO", "message": "processing order"},
        {"trace_id": "trace-1", "service": "inventory-service", "level": "ERROR", "message": "ConnectError to redis"},
        {"trace_id": "trace-2", "service": "api-gateway", "level": "INFO", "message": "routing request"},
    ]
    correlations = agent._build_cross_service_correlations(raw_logs)
    # Only trace-1 spans 2 services
    assert len(correlations) == 1
    assert set(correlations[0]["services"]) == {"checkout-service", "inventory-service"}
    assert correlations[0]["error_service"] == "inventory-service"
    assert correlations[0]["error_type"] == "ConnectError"


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


# ─── Flow Reconstruction (deterministic, no mocks needed) ─────────────────────

def test_reconstruct_service_flow_basic():
    agent = LogAnalysisAgent()
    trace_logs = [
        {"timestamp": "2025-12-26T14:00:01Z", "service": "api-gateway", "level": "INFO", "message": "GET /api/checkout received"},
        {"timestamp": "2025-12-26T14:00:02Z", "service": "coupon-service", "level": "WARN", "message": "validateCoupon returned 404 NOT FOUND"},
        {"timestamp": "2025-12-26T14:00:03Z", "service": "checkout-service", "level": "ERROR", "message": "processOrder failed: NullPointerException"},
    ]
    flow = agent._reconstruct_service_flow(trace_logs)
    assert len(flow) == 3
    # First step
    assert flow[0]["service"] == "api-gateway"
    assert flow[0]["status"] == "ok"
    assert flow[0]["is_new_service"] is True
    # Second step
    assert flow[1]["service"] == "coupon-service"
    assert flow[1]["status"] == "ok"
    assert flow[1]["is_new_service"] is True
    # Third step — error
    assert flow[2]["service"] == "checkout-service"
    assert flow[2]["status"] == "error"
    assert flow[2]["is_new_service"] is True


def test_reconstruct_service_flow_timeout_detection():
    agent = LogAnalysisAgent()
    trace_logs = [
        {"timestamp": "2025-12-26T14:00:01Z", "service": "svc-a", "level": "INFO", "message": "request timeout after 30s"},
    ]
    flow = agent._reconstruct_service_flow(trace_logs)
    assert flow[0]["status"] == "timeout"


def test_reconstruct_service_flow_same_service_twice():
    agent = LogAnalysisAgent()
    trace_logs = [
        {"timestamp": "2025-12-26T14:00:01Z", "service": "api-gateway", "level": "INFO", "message": "request received"},
        {"timestamp": "2025-12-26T14:00:02Z", "service": "order-service", "level": "INFO", "message": "processing"},
        {"timestamp": "2025-12-26T14:00:03Z", "service": "api-gateway", "level": "INFO", "message": "response sent"},
    ]
    flow = agent._reconstruct_service_flow(trace_logs)
    assert flow[0]["is_new_service"] is True  # first api-gateway
    assert flow[2]["is_new_service"] is False  # second api-gateway


def test_reconstruct_service_flow_sorted_by_timestamp():
    agent = LogAnalysisAgent()
    # Pass in reverse order to verify sorting
    trace_logs = [
        {"timestamp": "2025-12-26T14:00:03Z", "service": "svc-c", "level": "ERROR", "message": "failed"},
        {"timestamp": "2025-12-26T14:00:01Z", "service": "svc-a", "level": "INFO", "message": "start"},
        {"timestamp": "2025-12-26T14:00:02Z", "service": "svc-b", "level": "INFO", "message": "middle"},
    ]
    flow = agent._reconstruct_service_flow(trace_logs)
    assert flow[0]["service"] == "svc-a"
    assert flow[1]["service"] == "svc-b"
    assert flow[2]["service"] == "svc-c"


def test_reconstruct_service_flow_empty():
    agent = LogAnalysisAgent()
    flow = agent._reconstruct_service_flow([])
    assert flow == []


# ─── Extract Operation / Status Detail (deterministic) ────────────────────────

def test_extract_operation_http():
    agent = LogAnalysisAgent()
    assert agent._extract_operation("GET /api/checkout?id=123") == "GET /api/checkout?id=123"
    assert agent._extract_operation("POST /payment/process") == "POST /payment/process"


def test_extract_operation_function_call():
    agent = LogAnalysisAgent()
    assert agent._extract_operation("calling OrderService.process()") == "OrderService.process()"
    assert agent._extract_operation("Executing DatabasePool.getConnection") == "DatabasePool.getConnection"


def test_extract_operation_fallback():
    agent = LogAnalysisAgent()
    op = agent._extract_operation("some random log message about things")
    assert len(op) <= 40


def test_extract_status_detail_http_code():
    agent = LogAnalysisAgent()
    assert "200" in agent._extract_status_detail("responded with 200 OK to client", "INFO")
    assert "404" in agent._extract_status_detail("got 404 NOT FOUND from upstream", "WARN")


def test_extract_status_detail_exception():
    agent = LogAnalysisAgent()
    detail = agent._extract_status_detail("NullPointerException at line 45", "ERROR")
    assert detail == "NullPointerException"


def test_extract_status_detail_ok():
    agent = LogAnalysisAgent()
    assert agent._extract_status_detail("request completed", "INFO") == "OK"


# ─── Index Resolution (deterministic scoring) ─────────────────────────────────

def test_pick_best_index_prefers_service_match():
    agent = LogAnalysisAgent()
    indices = [
        {"index": "filebeat-2025.01", "docs.count": "1000"},
        {"index": "checkout-logs-2025.01", "docs.count": "500"},
        {"index": "system-logs", "docs.count": "2000"},
    ]
    best = agent._pick_best_index(indices, "checkout")
    assert best == "checkout-logs-2025.01"


def test_pick_best_index_prefers_log_keyword():
    agent = LogAnalysisAgent()
    indices = [
        {"index": "random-data", "docs.count": "1000"},
        {"index": "app-logs-2025.01", "docs.count": "500"},
    ]
    best = agent._pick_best_index(indices, "unknown-service")
    assert best == "app-logs-2025.01"


def test_pick_best_index_empty():
    agent = LogAnalysisAgent()
    assert agent._pick_best_index([], "anything") is None


# ─── LLM Response Parsing ─────────────────────────────────────────────────────

def test_parse_llm_response_valid_json():
    agent = LogAnalysisAgent()
    text = json.dumps({
        "primary_pattern": {
            "pattern_id": "p1",
            "exception_type": "ConnectionTimeout",
            "error_message": "Timed out after 30s",
            "frequency": 47,
            "severity": "critical",
            "affected_components": ["order-service"],
            "confidence_score": 87,
            "priority_rank": 1,
            "priority_reasoning": "High frequency timeout"
        },
        "secondary_patterns": [],
        "overall_confidence": 85,
        "root_cause_hypothesis": "Database pool exhaustion",
        "flow_analysis": ""
    })
    result = agent._parse_llm_response(text)
    assert result["primary_pattern"]["exception_type"] == "ConnectionTimeout"
    assert result["overall_confidence"] == 85
    assert result["root_cause_hypothesis"] == "Database pool exhaustion"


def test_parse_llm_response_json_in_text():
    agent = LogAnalysisAgent()
    text = 'Here is the analysis:\n{"primary_pattern": {}, "overall_confidence": 60}\nDone.'
    result = agent._parse_llm_response(text)
    assert result["overall_confidence"] == 60


def test_parse_llm_response_invalid():
    agent = LogAnalysisAgent()
    result = agent._parse_llm_response("not json at all")
    assert result["overall_confidence"] == 30
    assert result["primary_pattern"] == {}


# ─── Build Result ─────────────────────────────────────────────────────────────

def test_build_result_includes_all_fields():
    agent = LogAnalysisAgent()
    agent._raw_logs = [{"msg": "test"}]
    agent._patterns = [{"pattern_key": "k"}]

    collection = {
        "service_flow": [{"service": "svc-a", "status": "ok"}],
        "patterns": [{"pattern_key": "k", "exception_type": "TestError"}],
    }
    analysis = {
        "primary_pattern": {"exception_type": "TestError", "pattern_id": "p1"},
        "secondary_patterns": [],
        "overall_confidence": 75,
        "suggested_promql_queries": [{"metric": "cpu", "query": "rate(cpu[5m])", "rationale": "test"}],
    }
    result = agent._build_result(collection, analysis)

    assert result["primary_pattern"]["exception_type"] == "TestError"
    assert result["overall_confidence"] == 75
    assert result["raw_logs_count"] == 1
    assert result["patterns_found"] == 1
    assert result["service_flow"] == [{"service": "svc-a", "status": "ok"}]
    assert result["flow_source"] == "elasticsearch"
    assert result["flow_confidence"] == 70
    assert "breadcrumbs" in result
    assert "negative_findings" in result
    assert "tokens_used" in result
    assert "evidence_pins" in result
    assert "suggested_promql_queries" in result
    assert len(result["suggested_promql_queries"]) == 1


def test_build_result_no_flow():
    agent = LogAnalysisAgent()
    collection = {"service_flow": []}
    analysis = {"primary_pattern": {}, "secondary_patterns": [], "overall_confidence": 50}
    result = agent._build_result(collection, analysis)
    assert result["service_flow"] == []
    assert result["flow_confidence"] == 0


# ─── Breadcrumb & Negative Finding Tracking ────────────────────────────────────

def test_add_breadcrumb():
    agent = LogAnalysisAgent()
    agent.add_breadcrumb("test_action", "log", "test_ref", "test_evidence")
    assert len(agent.breadcrumbs) == 1
    assert agent.breadcrumbs[0].action == "test_action"
    assert agent.breadcrumbs[0].agent_name == "log_agent"


def test_add_negative_finding():
    agent = LogAnalysisAgent()
    agent.add_negative_finding("checked X", "nothing", "means Y", "ref")
    assert len(agent.negative_findings) == 1
    assert agent.negative_findings[0].what_was_checked == "checked X"


# ─── Analysis Prompt Building ──────────────────────────────────────────────────

def test_build_analysis_prompt_includes_patterns():
    agent = LogAnalysisAgent()
    collection = {
        "patterns": [
            {"exception_type": "TimeoutError", "frequency": 10, "severity": "high",
             "affected_components": ["svc-a"], "error_message": "Timed out", "pattern_key": "TimeoutError"},
        ],
        "raw_logs": [
            {"service": "svc-a", "level": "ERROR", "message": "Timed out"},
        ],
        "service_flow": [],
        "context_logs": [],
        "error_breadcrumbs": {},
        "cross_service_correlations": [],
        "inferred_dependencies": [],
        "index_used": "app-logs-*",
        "stats": {"total_logs": 50, "error_count": 10, "warn_count": 5},
    }
    context = {"service_name": "checkout", "timeframe": "now-1h"}
    prompt = agent._build_analysis_prompt(collection, context)
    assert "checkout" in prompt
    assert "TimeoutError" in prompt
    assert "app-logs-*" in prompt
    assert "Severity: high" in prompt
    assert "Architecture Map" in prompt
    assert "suggested_promql_queries" in prompt


def test_build_analysis_prompt_includes_flow():
    agent = LogAnalysisAgent()
    collection = {
        "patterns": [],
        "service_flow": [
            {"timestamp": "2025-01-01T00:00:00Z", "service": "gw", "operation": "GET /api", "status": "ok", "status_detail": "200 OK"},
        ],
        "context_logs": [],
        "index_used": "logs-*",
        "stats": {"total_logs": 0, "error_count": 0, "warn_count": 0},
    }
    context = {"service_name": "svc", "timeframe": "now-1h"}
    prompt = agent._build_analysis_prompt(collection, context)
    assert "Service Flow" in prompt
    assert "gw" in prompt


# ─── Full run() with mocked ES + LLM ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_full_hybrid_pipeline():
    """Test the complete run() pipeline with mocked ES and LLM."""
    agent = LogAnalysisAgent()

    # Mock ES responses
    mock_indices_response = MagicMock()
    mock_indices_response.status_code = 200
    mock_indices_response.json.return_value = [
        {"index": "app-logs-2025.01", "docs.count": "500", "store.size": "10mb", "health": "green", "status": "open"},
    ]
    mock_indices_response.raise_for_status = MagicMock()

    mock_search_response = MagicMock()
    mock_search_response.status_code = 200
    mock_search_response.json.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "1", "_index": "app-logs-2025.01",
                    "_source": {
                        "@timestamp": "2025-01-26T14:00:33Z",
                        "level": "ERROR",
                        "message": "ConnectionTimeout after 30s calling payment-service",
                        "service": "checkout-service",
                    }
                },
                {
                    "_id": "2", "_index": "app-logs-2025.01",
                    "_source": {
                        "@timestamp": "2025-01-26T14:00:34Z",
                        "level": "ERROR",
                        "message": "ConnectionTimeout after 25s calling payment-service",
                        "service": "checkout-service",
                    }
                },
            ]
        }
    }
    mock_search_response.raise_for_status = MagicMock()

    mock_context_response = MagicMock()
    mock_context_response.status_code = 200
    mock_context_response.json.return_value = {"hits": {"hits": []}}
    mock_context_response.raise_for_status = MagicMock()

    mock_head_response = MagicMock()
    mock_head_response.status_code = 200

    def mock_requests_side_effect(url, **kwargs):
        if "/_cat/indices" in url:
            return mock_indices_response
        return mock_search_response

    # Mock LLM
    mock_llm_response = MagicMock()
    mock_llm_response.text = json.dumps({
        "primary_pattern": {
            "pattern_id": "p1",
            "exception_type": "ConnectionTimeout",
            "error_message": "ConnectionTimeout after 30s calling payment-service",
            "frequency": 2,
            "severity": "high",
            "affected_components": ["checkout-service"],
            "confidence_score": 80,
            "priority_rank": 1,
            "priority_reasoning": "Repeated timeout to downstream dependency"
        },
        "secondary_patterns": [],
        "overall_confidence": 78,
        "root_cause_hypothesis": "payment-service is unresponsive",
        "flow_analysis": ""
    })

    with patch("requests.get", side_effect=mock_requests_side_effect), \
         patch("requests.post", return_value=mock_search_response), \
         patch("requests.head", return_value=mock_head_response):
        agent.llm_client.chat = AsyncMock(return_value=mock_llm_response)

        result = await agent.run(
            context={
                "service_name": "checkout-service",
                "elk_index": "app-logs-2025.01",
                "timeframe": "now-1h",
            },
            event_emitter=None,
        )

    # Verify result structure
    assert "primary_pattern" in result
    assert "secondary_patterns" in result
    assert "overall_confidence" in result
    assert "breadcrumbs" in result
    assert "negative_findings" in result
    assert "tokens_used" in result
    assert "service_flow" in result
    assert "flow_source" in result
    assert "flow_confidence" in result
    assert result["primary_pattern"]["exception_type"] == "ConnectionTimeout"
    assert result["overall_confidence"] == 78
    assert result["raw_logs_count"] == 2
    assert result["patterns_found"] >= 1


@pytest.mark.asyncio
async def test_run_emits_events():
    """Test that run() emits appropriate events."""
    agent = LogAnalysisAgent()
    emitter = AsyncMock()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"hits": {"hits": []}}
    mock_response.raise_for_status = MagicMock()

    mock_indices = MagicMock()
    mock_indices.status_code = 200
    mock_indices.json.return_value = []
    mock_indices.raise_for_status = MagicMock()

    mock_llm = MagicMock()
    mock_llm.text = '{"primary_pattern": {}, "overall_confidence": 20}'

    with patch("requests.get", return_value=mock_indices), \
         patch("requests.post", return_value=mock_response), \
         patch("requests.head", return_value=MagicMock(status_code=404)):
        agent.llm_client.chat = AsyncMock(return_value=mock_llm)
        await agent.run(
            context={"service_name": "test", "elk_index": "*", "timeframe": "now-1h"},
            event_emitter=emitter,
        )

    # Should have emitted started, tool_call(s), and success events
    event_types = [call.args[1] for call in emitter.emit.call_args_list]
    assert "started" in event_types
    assert "tool_call" in event_types
    assert "success" in event_types


@pytest.mark.asyncio
async def test_run_no_data_returns_low_confidence():
    """When ES returns no data, the result should have low confidence."""
    agent = LogAnalysisAgent()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"hits": {"hits": []}}
    mock_response.raise_for_status = MagicMock()

    mock_indices = MagicMock()
    mock_indices.status_code = 200
    mock_indices.json.return_value = []
    mock_indices.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_indices), \
         patch("requests.post", return_value=mock_response), \
         patch("requests.head", return_value=MagicMock(status_code=404)):
        # LLM should not be called if no data
        result = await agent.run(
            context={"service_name": "test", "elk_index": "*", "timeframe": "now-1h"},
            event_emitter=None,
        )

    assert result["overall_confidence"] <= 30
    assert result["service_flow"] == []
    assert result["flow_confidence"] == 0


@pytest.mark.asyncio
async def test_run_with_trace_id_reconstructs_flow():
    """When trace_id is provided and trace logs exist, flow should be reconstructed."""
    agent = LogAnalysisAgent()

    mock_head = MagicMock(status_code=200)

    mock_search = MagicMock()
    mock_search.status_code = 200
    mock_search.raise_for_status = MagicMock()
    mock_search.json.return_value = {
        "hits": {
            "hits": [
                {"_id": "1", "_index": "logs", "_source": {
                    "@timestamp": "2025-01-01T00:00:01Z", "level": "ERROR",
                    "message": "ConnectionTimeout", "service": "checkout",
                }},
            ]
        }
    }

    # Trace search returns logs from multiple services
    mock_trace_search = MagicMock()
    mock_trace_search.status_code = 200
    mock_trace_search.raise_for_status = MagicMock()
    mock_trace_search.json.return_value = {
        "hits": {
            "hits": [
                {"_id": "t1", "_index": "logs", "_source": {
                    "@timestamp": "2025-01-01T00:00:01Z", "level": "INFO",
                    "message": "GET /api/checkout", "service": "gateway",
                }},
                {"_id": "t2", "_index": "logs", "_source": {
                    "@timestamp": "2025-01-01T00:00:02Z", "level": "ERROR",
                    "message": "ConnectionTimeout calling DB", "service": "checkout",
                }},
            ]
        }
    }

    mock_context = MagicMock()
    mock_context.status_code = 200
    mock_context.raise_for_status = MagicMock()
    mock_context.json.return_value = {"hits": {"hits": []}}

    call_count = {"post": 0}

    def mock_post(url, **kwargs):
        call_count["post"] += 1
        # First post is ERROR search, subsequent are trace/context
        if call_count["post"] <= 3:
            return mock_search
        return mock_trace_search

    mock_indices = MagicMock()
    mock_indices.status_code = 200
    mock_indices.json.return_value = []
    mock_indices.raise_for_status = MagicMock()

    mock_llm = MagicMock()
    mock_llm.text = json.dumps({
        "primary_pattern": {"exception_type": "ConnectionTimeout", "error_message": "timeout", "frequency": 1,
                           "severity": "high", "affected_components": ["checkout"], "confidence_score": 70,
                           "priority_rank": 1, "priority_reasoning": "timeout"},
        "overall_confidence": 70,
    })

    # For this test, directly mock _search_by_trace_id to return trace logs
    with patch("requests.head", return_value=mock_head), \
         patch("requests.get", return_value=mock_indices), \
         patch("requests.post", return_value=mock_search):
        agent.llm_client.chat = AsyncMock(return_value=mock_llm)

        # Mock trace search specifically
        original_trace = agent._search_by_trace_id
        async def mock_trace_search_fn(params):
            return json.dumps({
                "total": 2,
                "logs": [
                    {"timestamp": "2025-01-01T00:00:01Z", "level": "INFO", "message": "GET /api/checkout", "service": "gateway"},
                    {"timestamp": "2025-01-01T00:00:02Z", "level": "ERROR", "message": "ConnectionTimeout", "service": "checkout"},
                ]
            })
        agent._search_by_trace_id = mock_trace_search_fn

        result = await agent.run(
            context={
                "service_name": "checkout",
                "elk_index": "logs",
                "timeframe": "now-1h",
                "trace_id": "abc123",
            },
            event_emitter=None,
        )

    assert len(result["service_flow"]) == 2
    assert result["service_flow"][0]["service"] == "gateway"
    assert result["service_flow"][1]["service"] == "checkout"
    assert result["service_flow"][1]["status"] == "error"
    assert result["flow_confidence"] == 70
    assert result["flow_source"] == "elasticsearch"


# ─── Stack Trace Filtering ─────────────────────────────────────────────────────

def test_filter_stack_trace_removes_framework_noise():
    """Framework frames should be replaced with a skip summary, application frames and file:line kept."""
    agent = LogAnalysisAgent()
    raw_trace = """java.lang.NullPointerException: Cannot invoke method on null
\tat com.myapp.service.OrderService.processOrder(OrderService.java:45)
\tat org.springframework.web.servlet.FrameworkServlet.service(FrameworkServlet.java:897)
\tat org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:166)
\tat org.apache.tomcat.websocket.server.WsFilter.doFilter(WsFilter.java:52)
\tat com.myapp.controller.OrderController.createOrder(OrderController.java:32)
\tat java.lang.reflect.Method.invoke(Method.java:498)
\tat io.netty.channel.AbstractChannelHandlerContext.invokeChannelRead(AbstractChannelHandlerContext.java:379)
Caused by: java.sql.SQLException: Connection refused
\tat com.myapp.db.ConnectionPool.getConnection(ConnectionPool.java:78)
\tat com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:128)"""
    filtered = agent._filter_stack_trace(raw_trace)
    # Application frames with file:line should be present
    assert "com.myapp.service.OrderService.processOrder(OrderService.java:45)" in filtered
    assert "com.myapp.controller.OrderController.createOrder(OrderController.java:32)" in filtered
    assert "com.myapp.db.ConnectionPool.getConnection(ConnectionPool.java:78)" in filtered
    # Exception/cause lines should be present
    assert "NullPointerException" in filtered
    assert "Caused by" in filtered
    assert "SQLException" in filtered
    # Framework noise should be replaced with skip summaries
    assert "org.springframework" not in filtered
    assert "org.apache.catalina" not in filtered
    assert "org.apache.tomcat" not in filtered
    assert "io.netty" not in filtered
    assert "java.lang.reflect" not in filtered
    assert "com.zaxxer.hikari" not in filtered
    # Skip summaries should appear instead
    assert "framework frames omitted" in filtered


def test_filter_stack_trace_empty():
    agent = LogAnalysisAgent()
    assert agent._filter_stack_trace("") == ""
    assert agent._filter_stack_trace(None) == ""


def test_filter_stack_trace_no_at_lines():
    """If there are no 'at' lines, non-framework lines should be kept."""
    agent = LogAnalysisAgent()
    raw_trace = "SomeError: something broke\nDetails: more info"
    filtered = agent._filter_stack_trace(raw_trace)
    assert "SomeError" in filtered
    assert "Details" in filtered


def test_filter_stack_trace_all_framework():
    """If all frames are framework, should produce a skip summary."""
    agent = LogAnalysisAgent()
    raw_trace = """at org.springframework.web.servlet.FrameworkServlet.service(FrameworkServlet.java:897)
at org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:166)
at org.apache.tomcat.websocket.server.WsFilter.doFilter(WsFilter.java:52)
at io.netty.channel.AbstractChannelHandlerContext.invokeChannelRead(AbstractChannelHandlerContext.java:379)"""
    filtered = agent._filter_stack_trace(raw_trace)
    # Should produce a skip summary for the 4 framework frames
    assert "4 framework frames omitted" in filtered


def test_filter_stack_trace_max_lines():
    """Filtered output should respect max_lines limit."""
    agent = LogAnalysisAgent()
    lines = ["SomeError: test"] + [f"at com.myapp.Svc{i}.method(Svc{i}.java:{i})" for i in range(30)]
    raw_trace = "\n".join(lines)
    filtered = agent._filter_stack_trace(raw_trace, max_lines=5)
    assert len(filtered.strip().splitlines()) <= 5


def test_filter_stack_trace_preserves_java_file_line():
    """Java file:line references like (OrderService.java:45) must be preserved."""
    agent = LogAnalysisAgent()
    raw_trace = """NullPointerException: test
\tat com.myapp.OrderService.process(OrderService.java:45)
\tat com.myapp.Controller.handle(Controller.java:12)"""
    filtered = agent._filter_stack_trace(raw_trace)
    assert "OrderService.java:45" in filtered
    assert "Controller.java:12" in filtered


def test_filter_stack_trace_preserves_python_file_line():
    """Python File '...', line N references must be preserved."""
    agent = LogAnalysisAgent()
    raw_trace = """Traceback (most recent call last):
  File "/app/services/payment.py", line 45, in process_payment
    result = db.execute(query)
  File "/app/db/pool.py", line 12, in execute
    conn = self.get_connection()
ConnectionError: Connection refused"""
    filtered = agent._filter_stack_trace(raw_trace)
    assert "/app/services/payment.py" in filtered
    assert "line 45" in filtered
    assert "/app/db/pool.py" in filtered
    assert "line 12" in filtered
    assert "ConnectionError" in filtered


def test_filter_stack_trace_preserves_ellipsis_more():
    """Lines like '... 42 more' should be preserved."""
    agent = LogAnalysisAgent()
    raw_trace = """java.lang.RuntimeException: outer
\tat com.myapp.Outer.run(Outer.java:10)
Caused by: java.io.IOException: inner
\tat com.myapp.Inner.read(Inner.java:20)
\t... 42 more"""
    filtered = agent._filter_stack_trace(raw_trace)
    assert "... 42 more" in filtered
    assert "Outer.java:10" in filtered
    assert "Inner.java:20" in filtered


def test_filter_stack_trace_framework_skip_count():
    """Consecutive framework frames should produce a single skip summary with correct count."""
    agent = LogAnalysisAgent()
    raw_trace = """NullPointerException: test
\tat com.myapp.Service.run(Service.java:10)
\tat org.springframework.web.A.a(A.java:1)
\tat org.springframework.web.B.b(B.java:2)
\tat org.springframework.web.C.c(C.java:3)
\tat com.myapp.Controller.handle(Controller.java:20)"""
    filtered = agent._filter_stack_trace(raw_trace)
    assert "Service.java:10" in filtered
    assert "Controller.java:20" in filtered
    assert "3 framework frames omitted" in filtered
    # Framework class names should not appear
    assert "org.springframework" not in filtered


# ─── Inline Preceding Context ──────────────────────────────────────────────────

def test_parse_patterns_includes_preceding_context():
    """Patterns should include preceding log lines before the first ERROR in the group.

    Note: grouping is by pattern key (exception type), so logs in the same group
    share the same error fingerprint. Preceding context comes from WARN/INFO logs
    within the same pattern group that occur before the first ERROR.
    """
    agent = LogAnalysisAgent()
    # All logs share the same pattern key "ConnectionTimeout" but vary in level
    logs = [
        {"level": "WARN", "message": "ConnectionTimeout warning: retrying attempt 1", "service": "order-svc", "timestamp": "2025-12-26T14:00:01Z"},
        {"level": "WARN", "message": "ConnectionTimeout warning: retrying attempt 2", "service": "order-svc", "timestamp": "2025-12-26T14:00:02Z"},
        {"level": "INFO", "message": "ConnectionTimeout threshold reached, escalating", "service": "order-svc", "timestamp": "2025-12-26T14:00:03Z"},
        {"level": "ERROR", "message": "ConnectionTimeout after 30s", "service": "order-svc", "timestamp": "2025-12-26T14:00:04Z"},
        {"level": "ERROR", "message": "ConnectionTimeout after 25s", "service": "order-svc", "timestamp": "2025-12-26T14:00:05Z"},
    ]
    patterns = agent._parse_patterns_from_logs(logs)
    assert len(patterns) >= 1
    ct_pattern = next((p for p in patterns if p["exception_type"] == "ConnectionTimeout"), None)
    assert ct_pattern is not None
    ctx = ct_pattern.get("preceding_context", [])
    assert len(ctx) == 3  # 3 logs before first ERROR in the same group
    assert any("retrying attempt 1" in c for c in ctx)
    assert any("retrying attempt 2" in c for c in ctx)
    assert any("threshold reached" in c for c in ctx)


def test_parse_patterns_preceding_context_empty_when_no_prior_logs():
    """If the first log is an ERROR, preceding_context should be empty."""
    agent = LogAnalysisAgent()
    logs = [
        {"level": "ERROR", "message": "ConnectionTimeout after 30s", "service": "svc-a", "timestamp": "2025-12-26T14:00:01Z"},
    ]
    patterns = agent._parse_patterns_from_logs(logs)
    ct_pattern = next((p for p in patterns if p["exception_type"] == "ConnectionTimeout"), None)
    assert ct_pattern is not None
    assert ct_pattern.get("preceding_context", []) == []


def test_parse_patterns_includes_filtered_stack_trace():
    """Patterns should include filtered_stack_trace when stack traces exist."""
    agent = LogAnalysisAgent()
    logs = [
        {
            "level": "ERROR",
            "message": "NullPointerException at processOrder",
            "service": "order-svc",
            "timestamp": "2025-12-26T14:00:01Z",
            "stack_trace": "NullPointerException\n\tat com.myapp.Order.process(Order.java:10)\n\tat org.springframework.web.Servlet.service(Servlet.java:50)",
        },
    ]
    patterns = agent._parse_patterns_from_logs(logs)
    npe = next((p for p in patterns if p["exception_type"] == "NullPointerException"), None)
    assert npe is not None
    assert npe.get("filtered_stack_trace") != ""
    assert "com.myapp.Order.process" in npe["filtered_stack_trace"]
    assert "org.springframework" not in npe["filtered_stack_trace"]


# ─── Business Impact Inference ──────────────────────────────────────────────────

def test_infer_business_impact_basic():
    """Services should map to correct business capabilities and risk levels."""
    from src.agents.impact_analyzer import ImpactAnalyzer
    analyzer = ImpactAnalyzer()
    result = analyzer.infer_business_impact(["checkout-service", "payment-gateway", "inventory-service"])
    assert len(result) >= 2
    # Revenue Generation should be critical and come first
    assert result[0]["capability"] == "Revenue Generation"
    assert result[0]["risk_level"] == "critical"
    assert "checkout-service" in result[0]["affected_services"]
    assert "payment-gateway" in result[0]["affected_services"]
    # Order Fulfillment should be high
    fulfillment = next((c for c in result if c["capability"] == "Order Fulfillment"), None)
    assert fulfillment is not None
    assert fulfillment["risk_level"] == "high"
    assert "inventory-service" in fulfillment["affected_services"]


def test_infer_business_impact_unknown_service():
    """Unknown services should map to General Operations."""
    from src.agents.impact_analyzer import ImpactAnalyzer
    analyzer = ImpactAnalyzer()
    result = analyzer.infer_business_impact(["mystery-service"])
    assert len(result) == 1
    assert result[0]["capability"] == "General Operations"
    assert result[0]["risk_level"] == "medium"


def test_infer_business_impact_empty():
    from src.agents.impact_analyzer import ImpactAnalyzer
    analyzer = ImpactAnalyzer()
    result = analyzer.infer_business_impact([])
    assert result == []


def test_infer_business_impact_sorted_by_risk():
    """Results should be sorted critical > high > medium > low."""
    from src.agents.impact_analyzer import ImpactAnalyzer
    analyzer = ImpactAnalyzer()
    result = analyzer.infer_business_impact([
        "monitoring-service", "checkout-service", "auth-service", "catalog-service",
    ])
    risk_levels = [c["risk_level"] for c in result]
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for i in range(len(risk_levels) - 1):
        assert risk_order[risk_levels[i]] <= risk_order[risk_levels[i + 1]]


def test_blast_radius_schema_has_business_impact():
    """BlastRadius model should accept business_impact field."""
    from src.models.schemas import BlastRadius
    br = BlastRadius(
        primary_service="checkout",
        scope="service_group",
        business_impact=[{"capability": "Revenue Generation", "risk_level": "critical", "affected_services": ["checkout"]}],
    )
    assert len(br.business_impact) == 1
    assert br.business_impact[0]["capability"] == "Revenue Generation"

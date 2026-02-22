import pytest
from src.agents.metrics_agent import MetricsAgent


def test_metrics_agent_init():
    agent = MetricsAgent()
    assert agent.agent_name == "metrics_agent"


def test_spike_detection_finds_spikes():
    agent = MetricsAgent()
    data_points = [
        {"timestamp": 1000, "value": 30.0},
        {"timestamp": 1060, "value": 32.0},
        {"timestamp": 1120, "value": 31.0},
        {"timestamp": 1180, "value": 95.0},  # spike
        {"timestamp": 1240, "value": 93.0},  # spike
        {"timestamp": 1300, "value": 31.0},  # normal
    ]
    spikes = agent._detect_spikes(data_points, baseline_threshold=2.0)
    assert len(spikes) >= 1
    assert spikes[0]["peak_value"] == 95.0
    # Verify confidence_score is present and within valid range
    assert "confidence_score" in spikes[0]
    assert 0 <= spikes[0]["confidence_score"] <= 95


def test_spike_detection_no_spikes():
    agent = MetricsAgent()
    data_points = [
        {"timestamp": 1000, "value": 30.0},
        {"timestamp": 1060, "value": 31.0},
        {"timestamp": 1120, "value": 30.5},
        {"timestamp": 1180, "value": 30.0},
    ]
    spikes = agent._detect_spikes(data_points, baseline_threshold=2.0)
    assert len(spikes) == 0


def test_spike_detection_too_few_points():
    agent = MetricsAgent()
    spikes = agent._detect_spikes([{"timestamp": 1, "value": 100}], baseline_threshold=2.0)
    assert spikes == []


def test_spike_detection_constant_values():
    agent = MetricsAgent()
    data_points = [{"timestamp": i, "value": 50.0} for i in range(10)]
    spikes = agent._detect_spikes(data_points)
    assert spikes == []


def test_build_default_queries():
    agent = MetricsAgent()
    queries = agent._build_default_queries(namespace="prod", service_name="order-service")
    assert len(queries) == 8
    names = [q["name"] for q in queries]
    assert "cpu_usage" in names
    assert "memory_usage" in names
    assert "error_rate" in names
    assert "latency_p99" in names
    assert "restart_count" in names
    assert "crashloop_pods" in names
    assert "oom_killed" in names
    assert "pending_pods" in names
    # Verify namespace and service are in queries
    for q in queries:
        assert "prod" in q["query"]
        assert "order-service" in q["query"]


def test_build_default_queries_custom_namespace():
    agent = MetricsAgent()
    queries = agent._build_default_queries(namespace="staging-east", service_name="payment-svc")
    for q in queries:
        assert "staging-east" in q["query"]
        assert "payment-svc" in q["query"]


def test_spike_at_end_of_data():
    agent = MetricsAgent()
    data_points = [
        {"timestamp": 1000, "value": 30.0},
        {"timestamp": 1060, "value": 31.0},
        {"timestamp": 1120, "value": 30.0},
        {"timestamp": 1180, "value": 95.0},  # spike at end
        {"timestamp": 1240, "value": 98.0},  # spike continues
    ]
    spikes = agent._detect_spikes(data_points, baseline_threshold=2.0)
    assert len(spikes) >= 1
    assert spikes[0]["peak_value"] == 98.0
    assert "confidence_score" in spikes[0]
    assert spikes[0]["confidence_score"] <= 95


def test_build_default_queries_with_metadata():
    agent = MetricsAgent()
    queries = agent._build_default_queries(
        namespace="prod", service_name="order-service",
        job="order-job", app_label="order-app",
    )
    assert len(queries) == 8
    # The first 5 queries (cpu, memory, error_rate, latency, restarts) use extra_labels
    for q in queries[:5]:
        assert 'job="order-job"' in q["query"]
        assert 'app="order-app"' in q["query"]


def test_build_default_queries_without_metadata():
    agent = MetricsAgent()
    queries = agent._build_default_queries(
        namespace="prod", service_name="order-service",
    )
    for q in queries:
        assert "job=" not in q["query"]
        assert "app=" not in q["query"]


def test_get_saturation_metrics():
    import json
    agent = MetricsAgent()
    result = json.loads(agent._get_saturation_metrics({
        "namespace": "prod",
        "service_name": "order-service",
        "error_hints": ["oom", "timeout"],
    }))
    assert "saturation_queries" in result
    query_names = [q["name"] for q in result["saturation_queries"]]
    assert "memory_saturation" in query_names
    assert "cpu_throttling" in query_names


def test_get_saturation_metrics_no_match():
    import json
    agent = MetricsAgent()
    result = json.loads(agent._get_saturation_metrics({
        "namespace": "prod",
        "service_name": "svc",
        "error_hints": ["unknown_error"],
    }))
    assert result["saturation_queries"] == []


def test_parse_final_response_includes_all_time_series():
    import json
    agent = MetricsAgent()
    # Cache some time series data
    agent._time_series_cache = {
        "cpu_query": [{"timestamp": 1000, "value": 10.0}],
        "memory_query": [{"timestamp": 1000, "value": 500.0}],
        "network_query": [{"timestamp": 1000, "value": 1.0}],
    }
    text = json.dumps({
        "anomalies": [{"metric_name": "cpu_usage"}],
        "correlated_signals": [],
        "overall_confidence": 75,
    })
    result = agent._parse_final_response(text)
    # All cached time series are included — even normal metrics provide context
    assert "cpu_query" in result["time_series_data"]
    assert "memory_query" in result["time_series_data"]
    assert "network_query" in result["time_series_data"]
    assert result["correlated_signals"] == []

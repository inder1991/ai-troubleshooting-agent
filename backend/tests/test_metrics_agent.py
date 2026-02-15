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
    assert len(queries) == 5
    names = [q["name"] for q in queries]
    assert "cpu_usage" in names
    assert "memory_usage" in names
    assert "error_rate" in names
    assert "latency_p99" in names
    assert "restart_count" in names
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

import pytest
from src.agents.k8s_agent import K8sAgent


def test_k8s_agent_init():
    agent = K8sAgent()
    assert agent.agent_name == "k8s_agent"


def test_detect_crashloopbackoff():
    result = K8sAgent._analyze_pod_statuses([
        {
            "pod_name": "order-svc-abc", "status": "Running", "restart_count": 0,
            "container_statuses": [{"state": {"running": {}}}],
        },
        {
            "pod_name": "order-svc-def", "status": "Running", "restart_count": 8,
            "container_statuses": [{"state": {"waiting": {"reason": "CrashLoopBackOff"}}}],
        },
    ])
    assert result["is_crashloop"] is True
    assert result["total_restarts"] == 8


def test_detect_oom_killed():
    result = K8sAgent._analyze_pod_statuses([
        {
            "pod_name": "order-svc-abc", "status": "Running", "restart_count": 3,
            "last_termination_reason": "OOMKilled",
            "container_statuses": [],
        },
    ])
    assert "OOMKilled" in result["termination_reasons"]


def test_healthy_pods():
    result = K8sAgent._analyze_pod_statuses([
        {
            "pod_name": "order-svc-abc", "status": "Running", "restart_count": 0,
            "container_statuses": [{"state": {"running": {}}}],
        },
        {
            "pod_name": "order-svc-def", "status": "Running", "restart_count": 0,
            "container_statuses": [{"state": {"running": {}}}],
        },
    ])
    assert result["is_crashloop"] is False
    assert result["total_restarts"] == 0
    assert result["termination_reasons"] == []


def test_multiple_restarts():
    result = K8sAgent._analyze_pod_statuses([
        {"pod_name": "p1", "status": "Running", "restart_count": 3, "container_statuses": []},
        {"pod_name": "p2", "status": "Running", "restart_count": 5, "container_statuses": []},
    ])
    assert result["total_restarts"] == 8

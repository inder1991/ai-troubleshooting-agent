import pytest
import json
from datetime import datetime, timezone

from src.agents.k8s_agent import K8sAgent
from src.models.schemas import K8sEvent, PodHealthStatus


# --- Existing tests ---


def test_k8s_agent_init():
    agent = K8sAgent()
    assert agent.agent_name == "k8s_agent"
    assert agent.max_iterations == 12


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


# --- Phase 1: K8sEvent stored fields ---


def test_k8s_event_stored_count():
    """count is now a stored field, not a hardcoded computed field."""
    event = K8sEvent(
        timestamp=datetime.now(timezone.utc),
        type="Warning",
        reason="BackOff",
        message="Back-off restarting failed container",
        source_component="kubelet",
        count=42,
        involved_object="order-svc-pod-abc",
    )
    dumped = event.model_dump()
    assert dumped["count"] == 42
    assert dumped["involved_object"] == "order-svc-pod-abc"


def test_k8s_event_default_count():
    """count defaults to 1, involved_object defaults to empty string."""
    event = K8sEvent(
        timestamp=datetime.now(timezone.utc),
        type="Normal",
        reason="Scheduled",
        message="Successfully assigned",
        source_component="default-scheduler",
    )
    dumped = event.model_dump()
    assert dumped["count"] == 1
    assert dumped["involved_object"] == ""


def test_k8s_event_computed_timestamps():
    """first_timestamp and last_timestamp still computed from timestamp."""
    ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    event = K8sEvent(
        timestamp=ts,
        type="Warning",
        reason="Unhealthy",
        message="Readiness probe failed",
        source_component="kubelet",
    )
    assert event.first_timestamp == ts.isoformat()
    assert event.last_timestamp == ts.isoformat()


# --- Phase 1: PodHealthStatus new optional fields ---


def test_pod_health_status_new_fields():
    """New optional fields have correct defaults and can be set."""
    pod = PodHealthStatus(
        pod_name="test-pod",
        status="Running",
        restart_count=0,
        init_container_failures=["init-db: CrashLoopBackOff"],
        image_pull_errors=["app: ImagePullBackOff"],
        container_count=2,
        ready_containers=1,
    )
    assert pod.init_container_failures == ["init-db: CrashLoopBackOff"]
    assert pod.image_pull_errors == ["app: ImagePullBackOff"]
    assert pod.container_count == 2
    assert pod.ready_containers == 1


def test_pod_health_status_defaults():
    """New fields default to empty/zero."""
    pod = PodHealthStatus(
        pod_name="test-pod",
        status="Running",
        restart_count=0,
    )
    assert pod.init_container_failures == []
    assert pod.image_pull_errors == []
    assert pod.container_count == 0
    assert pod.ready_containers == 0


def test_pod_health_status_computed_fields():
    """Existing computed fields still work correctly."""
    pod = PodHealthStatus(
        pod_name="test-pod",
        status="Running",
        restart_count=0,
    )
    assert pod.ready is True
    assert pod.oom_killed is False
    assert pod.crash_loop is False

    oom_pod = PodHealthStatus(
        pod_name="oom-pod",
        status="CrashLoopBackOff",
        restart_count=5,
        last_termination_reason="OOMKilled",
    )
    assert oom_pod.oom_killed is True
    assert oom_pod.crash_loop is True


# --- Phase 2: _parse_final_response ---


def test_parse_final_response_valid_json():
    agent = K8sAgent()
    text = json.dumps({
        "pod_statuses": [{"pod_name": "p1", "status": "Running", "restart_count": 0}],
        "events": [],
        "is_crashloop": False,
        "total_restarts_last_hour": 0,
        "resource_mismatch": None,
        "overall_confidence": 85,
    })
    result = agent._parse_final_response(text)
    assert result["overall_confidence"] == 85
    assert result["is_crashloop"] is False
    assert len(result["pod_statuses"]) == 1


def test_parse_final_response_json_in_text():
    agent = K8sAgent()
    text = """Based on my analysis, here are the findings:

    {
        "pod_statuses": [],
        "events": [],
        "is_crashloop": true,
        "total_restarts_last_hour": 12,
        "resource_mismatch": "memory limit too low",
        "overall_confidence": 70
    }

    This indicates a crash loop."""
    result = agent._parse_final_response(text)
    assert result["is_crashloop"] is True
    assert result["total_restarts_last_hour"] == 12
    assert result["resource_mismatch"] == "memory limit too low"


def test_parse_final_response_invalid_json():
    agent = K8sAgent()
    text = "This is not JSON at all, just some text analysis."
    result = agent._parse_final_response(text)
    assert "error" in result
    assert "raw_response" in result


def test_parse_final_response_missing_fields():
    agent = K8sAgent()
    text = json.dumps({"overall_confidence": 60})
    result = agent._parse_final_response(text)
    assert result["pod_statuses"] == []
    assert result["events"] == []
    assert result["is_crashloop"] is False
    assert result["total_restarts_last_hour"] == 0
    assert result["resource_mismatch"] is None
    assert result["overall_confidence"] == 60


# --- Phase 2: _analyze_pod_statuses edge cases ---


def test_analyze_empty_pod_list():
    result = K8sAgent._analyze_pod_statuses([])
    assert result["is_crashloop"] is False
    assert result["total_restarts"] == 0
    assert result["termination_reasons"] == []


def test_analyze_image_pull_errors():
    """Image pull errors are in container_statuses but don't trigger crashloop."""
    result = K8sAgent._analyze_pod_statuses([
        {
            "pod_name": "p1",
            "status": "Pending",
            "restart_count": 0,
            "container_statuses": [
                {"state": {"waiting": {"reason": "ImagePullBackOff"}}}
            ],
        },
    ])
    assert result["is_crashloop"] is False
    assert result["total_restarts"] == 0


def test_analyze_init_container_failures():
    """Init container failures don't affect container_statuses analysis."""
    result = K8sAgent._analyze_pod_statuses([
        {
            "pod_name": "p1",
            "status": "Init:CrashLoopBackOff",
            "restart_count": 0,
            "container_statuses": [],
            "init_container_failures": ["init-db: CrashLoopBackOff"],
        },
    ])
    assert result["is_crashloop"] is False
    assert result["total_restarts"] == 0


def test_analyze_terminated_container_last_state():
    """Terminated containers in last_state are captured."""
    result = K8sAgent._analyze_pod_statuses([
        {
            "pod_name": "p1",
            "status": "Running",
            "restart_count": 2,
            "container_statuses": [
                {
                    "state": {"running": {}},
                    "last_state": {"terminated": {"reason": "Error", "exit_code": 1}},
                }
            ],
        },
    ])
    assert "Error" in result["termination_reasons"]
    assert result["total_restarts"] == 2

"""Test the GET /session/{id}/dag endpoint returns the virtual DAG."""
import pytest

from src.workflows.investigation_types import VirtualDag, VirtualStep
from src.workflows.event_schema import StepStatus


def test_dag_endpoint_returns_virtual_dag():
    dag = VirtualDag(run_id="inv-123")
    dag.append_step(VirtualStep(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.SUCCESS,
        round=1,
    ))
    dag.append_step(VirtualStep(
        step_id="round-2-metrics-agent",
        agent="metrics_agent",
        depends_on=["round-1-log-agent"],
        status=StepStatus.RUNNING,
        round=2,
    ))

    result = dag.to_dict()
    assert result["run_id"] == "inv-123"
    assert len(result["steps"]) == 2
    assert result["steps"][0]["step_id"] == "round-1-log-agent"
    assert result["steps"][1]["depends_on"] == ["round-1-log-agent"]


def test_dag_endpoint_empty_investigation():
    dag = VirtualDag(run_id="inv-new")
    result = dag.to_dict()
    assert result["steps"] == []
    assert result["status"] == "running"

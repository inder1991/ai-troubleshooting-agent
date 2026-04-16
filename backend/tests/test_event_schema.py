# backend/tests/test_event_schema.py
import pytest
from datetime import datetime, timezone

from src.workflows.event_schema import (
    StepStatus,
    ErrorDetail,
    StepMetadata,
    StepPayload,
    RunPayload,
    ErrorPayload,
    EventEnvelope,
    make_step_event,
    make_run_event,
)


def test_step_status_values():
    assert StepStatus.PENDING == "pending"
    assert StepStatus.RUNNING == "running"
    assert StepStatus.SUCCESS == "success"
    assert StepStatus.FAILED == "failed"
    assert StepStatus.SKIPPED == "skipped"
    assert StepStatus.CANCELLED == "cancelled"


def test_make_step_event_minimal():
    env = make_step_event(
        run_id="inv-123",
        step_id="round-1-log-agent",
        parent_step_ids=[],
        status=StepStatus.RUNNING,
        sequence_number=1,
    )
    assert env.event_type == "step_update"
    assert env.run_id == "inv-123"
    assert env.sequence_number == 1
    assert isinstance(env.timestamp, str)
    assert env.payload.step_id == "round-1-log-agent"
    assert env.payload.status == StepStatus.RUNNING
    assert env.payload.parent_step_ids == []


def test_make_step_event_full_metadata():
    meta = StepMetadata(
        agent="metrics_agent",
        round=2,
        group="validation_phase",
        hypothesis_id="h1",
        reason="validate OOM suspicion",
        duration_ms=1234,
        error=ErrorDetail(message="timeout", type="TimeoutError"),
    )
    env = make_step_event(
        run_id="inv-123",
        step_id="round-2-metrics-agent",
        parent_step_ids=["round-1-log-agent"],
        status=StepStatus.FAILED,
        sequence_number=2,
        started_at="2026-04-16T10:00:00Z",
        ended_at="2026-04-16T10:00:01Z",
        metadata=meta,
    )
    assert env.payload.metadata.agent == "metrics_agent"
    assert env.payload.metadata.round == 2
    assert env.payload.metadata.error.message == "timeout"
    assert env.payload.started_at == "2026-04-16T10:00:00Z"


def test_make_run_event():
    env = make_run_event(
        run_id="inv-123",
        status="completed",
        sequence_number=10,
    )
    assert env.event_type == "run_update"
    assert env.payload.status == "completed"


def test_event_envelope_to_dict():
    env = make_step_event(
        run_id="inv-123",
        step_id="round-1-log-agent",
        parent_step_ids=[],
        status=StepStatus.RUNNING,
        sequence_number=1,
    )
    d = env.to_dict()
    assert d["event_type"] == "step_update"
    assert d["run_id"] == "inv-123"
    assert d["sequence_number"] == 1
    assert d["payload"]["step_id"] == "round-1-log-agent"
    assert d["payload"]["status"] == "running"

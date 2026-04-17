"""Task 1.14 — coverage_gaps on DiagnosticState + API response.

When an agent is skipped or fails (Prometheus unreachable, K8s token
rejected, ELK empty, tool circuit open), the supervisor used to either
silently continue or emit an event-bus `error` that the UI dropped.
That gave downstream consumers — and the confidence calibrator — no
visibility into how much of the signal space was actually explored.

``state.coverage_gaps`` is a list of one-liner strings
``"<agent_name>: <reason>"``; the supervisor appends on every skip /
error path; the API serializes the list on the investigation result;
the frontend type mirrors it.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.models.schemas import DiagnosticState, DiagnosticPhase, TimeWindow


def _state() -> DiagnosticState:
    return DiagnosticState(
        session_id="s-test",
        phase=DiagnosticPhase.COLLECTING_CONTEXT,
        service_name="svc-a",
        time_window=TimeWindow(start="now-1h", end="now"),
    )


def test_state_has_empty_coverage_gaps_by_default():
    s = _state()
    assert s.coverage_gaps == []


def test_record_coverage_gap_appends_reason():
    from src.agents.supervisor import record_coverage_gap

    s = _state()
    record_coverage_gap(s, "metrics_agent", "prometheus unreachable (connection refused)")
    assert s.coverage_gaps == [
        "metrics_agent: prometheus unreachable (connection refused)"
    ]


def test_record_coverage_gap_is_idempotent_for_same_reason():
    """Duplicate recording (e.g. retry path) should not multiply entries."""
    from src.agents.supervisor import record_coverage_gap

    s = _state()
    record_coverage_gap(s, "k8s_agent", "401 Unauthorized after token reload")
    record_coverage_gap(s, "k8s_agent", "401 Unauthorized after token reload")
    assert len(s.coverage_gaps) == 1


def test_record_coverage_gap_supports_different_reasons_same_agent():
    from src.agents.supervisor import record_coverage_gap

    s = _state()
    record_coverage_gap(s, "metrics_agent", "prometheus unreachable")
    record_coverage_gap(s, "metrics_agent", "PromQL safety middleware rejected query")
    assert len(s.coverage_gaps) == 2


def test_record_coverage_gap_truncates_long_reasons():
    """Reason strings come from exception messages that can be
    unbounded (stack traces folded into str(e))."""
    from src.agents.supervisor import record_coverage_gap, MAX_GAP_REASON_LEN

    s = _state()
    record_coverage_gap(s, "log_agent", "x" * 5000)
    entry = s.coverage_gaps[0]
    prefix = "log_agent: "
    # Reason portion capped.
    assert len(entry) <= len(prefix) + MAX_GAP_REASON_LEN + len(" …[truncated]")


def test_record_coverage_gap_rejects_empty_agent_or_reason():
    from src.agents.supervisor import record_coverage_gap

    s = _state()
    with pytest.raises(ValueError):
        record_coverage_gap(s, "", "some reason")
    with pytest.raises(ValueError):
        record_coverage_gap(s, "metrics_agent", "")


@pytest.mark.asyncio
async def test_dispatch_agent_missing_prereq_records_coverage_gap():
    """When a prerequisite check rejects dispatch (e.g. no Prometheus
    URL configured), the skip reason must land on state.coverage_gaps."""
    from unittest.mock import AsyncMock

    from src.agents.supervisor import SupervisorAgent

    supervisor = SupervisorAgent()
    state = _state()
    emitter = AsyncMock()

    # No prometheus_url on state → _check_prerequisites rejects dispatch
    # with "No Prometheus URL configured — skipping metrics analysis".
    result = await supervisor._dispatch_agent("metrics_agent", state, emitter)

    assert result is None
    assert any(
        gap.startswith("metrics_agent: ") and "Prometheus" in gap
        for gap in state.coverage_gaps
    ), state.coverage_gaps


@pytest.mark.asyncio
async def test_dispatch_agent_exception_records_coverage_gap(monkeypatch):
    """Runtime exceptions from an agent's run() must also land in
    state.coverage_gaps."""
    from unittest.mock import AsyncMock, MagicMock

    from src.agents.supervisor import SupervisorAgent

    supervisor = SupervisorAgent()

    class _BoomAgent:
        def __init__(self, *a, **kw):
            pass

        async def run(self, *a, **kw):
            raise ConnectionError("prometheus unreachable (connection refused)")

        def get_token_usage(self):
            m = MagicMock()
            m.model_dump = lambda: {
                "agent_name": "metrics_agent",
                "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            }
            return m

    supervisor._agents["metrics_agent"] = _BoomAgent  # type: ignore[assignment]
    # Bypass prereq check by stubbing the method.
    supervisor._check_prerequisites = lambda *a, **kw: None  # type: ignore[method-assign]

    state = _state()
    emitter = AsyncMock()

    result = await supervisor._dispatch_agent("metrics_agent", state, emitter)

    assert result is None
    assert any(
        gap.startswith("metrics_agent: ") and "prometheus unreachable" in gap
        for gap in state.coverage_gaps
    ), state.coverage_gaps

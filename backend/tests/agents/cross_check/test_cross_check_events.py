"""Supervisor cross-check timeline event emission tests.

Covers the ``cross_check_complete`` summary event emitted by
``_run_metrics_logs_cross_check`` once per check, regardless of
whether disagreements were found — so the Investigator timeline
has a marker for when the cross-check ran.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agents.supervisor import (
    _CROSS_CHECK_LOCKS,
    _run_metrics_logs_cross_check,
    reset_cross_check_state_for_reinvestigation,
)
from src.models.schemas import (
    DiagnosticPhase,
    DiagnosticState,
    ErrorPattern,
    LogAnalysisResult,
    MetricAnomaly,
    MetricsAnalysisResult,
    TimeWindow,
    TokenUsage,
)


# ── Fixtures ──────────────────────────────────────────────────────────


def _anomaly(promql: str) -> MetricAnomaly:
    now = datetime.now(timezone.utc)
    return MetricAnomaly(
        metric_name="m",
        promql_query=promql,
        baseline_value=10,
        peak_value=100,
        spike_start=now,
        spike_end=now,
        severity="high",
        correlation_to_incident="x",
        confidence_score=80,
    )


def _metrics(anomalies=None) -> MetricsAnalysisResult:
    return MetricsAnalysisResult(
        anomalies=anomalies or [],
        time_series_data={},
        chart_highlights=[],
        negative_findings=[],
        breadcrumbs=[],
        overall_confidence=80,
        tokens_used=TokenUsage(agent_name="m", input_tokens=0, output_tokens=0, total_tokens=0),
    )


def _logs_with_pattern(svc: str, freq: int = 10) -> LogAnalysisResult:
    pattern = ErrorPattern(
        pattern_id="p1",
        exception_type="NullPointerException",
        error_message="boom",
        frequency=freq,
        severity="high",
        affected_components=[svc],
        sample_logs=[],
        confidence_score=85,
        priority_rank=1,
        priority_reasoning="top",
    )
    return LogAnalysisResult(
        primary_pattern=pattern,
        secondary_patterns=[],
        negative_findings=[],
        breadcrumbs=[],
        overall_confidence=80,
        tokens_used=TokenUsage(agent_name="l", input_tokens=0, output_tokens=0, total_tokens=0),
    )


def _state(metrics=None, logs=None) -> DiagnosticState:
    return DiagnosticState(
        session_id="s",
        incident_id="i",
        phase=DiagnosticPhase.COLLECTING_CONTEXT,
        service_name="svc",
        time_window=TimeWindow(start="2026-04-19T00:00:00Z", end="2026-04-19T01:00:00Z"),
        namespace="ns",
        metrics_analysis=metrics,
        log_analysis=logs,
    )


def _collect_emits(emitter: AsyncMock) -> list[dict[str, Any]]:
    """Return each emit() call as a kwargs dict for easy assertion."""
    calls: list[dict[str, Any]] = []
    for args, kwargs in emitter.emit.await_args_list:
        # emit() is (agent_name, event_type, message, details=None)
        call: dict[str, Any] = {
            "agent_name": args[0] if len(args) > 0 else kwargs.get("agent_name"),
            "event_type": args[1] if len(args) > 1 else kwargs.get("event_type"),
            "message": args[2] if len(args) > 2 else kwargs.get("message"),
            "details": args[3] if len(args) > 3 else kwargs.get("details", {}),
        }
        calls.append(call)
    return calls


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emits_completion_summary_when_divergences_found():
    state = _state(
        metrics=_metrics([_anomaly('errors{service="payments-api"}')]),
        logs=_logs_with_pattern("checkout-service"),
    )
    emitter = AsyncMock()
    emitter.emit = AsyncMock()

    await _run_metrics_logs_cross_check(state, emitter)

    calls = _collect_emits(emitter)
    summaries = [c for c in calls if c["event_type"] == "summary"]
    assert len(summaries) == 1
    assert "cross-check" in summaries[0]["message"].lower()
    assert "metrics" in summaries[0]["message"].lower()
    assert "logs" in summaries[0]["message"].lower()
    assert summaries[0]["details"]["action"] == "cross_check_complete"
    assert summaries[0]["details"]["cross_check"] == "metrics_logs"
    assert summaries[0]["details"]["divergence_count"] >= 1


@pytest.mark.asyncio
async def test_emits_completion_summary_when_signals_agreed():
    """Zero divergences still gets a timeline marker — that's the whole point.

    Setup: metrics flag a service; logs also have that same service clustering
    errors. No divergence.
    """
    state = _state(
        metrics=_metrics([_anomaly('errors{service="payments-api"}')]),
        logs=_logs_with_pattern("payments-api"),
    )
    emitter = AsyncMock()
    emitter.emit = AsyncMock()

    await _run_metrics_logs_cross_check(state, emitter)

    calls = _collect_emits(emitter)
    summaries = [c for c in calls if c["event_type"] == "summary"]
    assert len(summaries) == 1
    assert "agreed" in summaries[0]["message"].lower()
    assert summaries[0]["details"]["divergence_count"] == 0


@pytest.mark.asyncio
async def test_emits_completion_summary_exactly_once():
    """Helper is called from both log_agent and metrics_agent handlers —
    summary must not fire twice."""
    state = _state(
        metrics=_metrics([_anomaly('errors{service="payments-api"}')]),
        logs=_logs_with_pattern("checkout-service"),
    )
    emitter = AsyncMock()
    emitter.emit = AsyncMock()

    await _run_metrics_logs_cross_check(state, emitter)
    await _run_metrics_logs_cross_check(state, emitter)

    calls = _collect_emits(emitter)
    summaries = [c for c in calls if c["event_type"] == "summary"]
    assert len(summaries) == 1


@pytest.mark.asyncio
async def test_cross_checks_announced_records_the_check_name():
    state = _state(
        metrics=_metrics([_anomaly('errors{service="payments-api"}')]),
        logs=_logs_with_pattern("checkout-service"),
    )
    emitter = AsyncMock()
    emitter.emit = AsyncMock()

    await _run_metrics_logs_cross_check(state, emitter)

    assert "metrics_logs" in state.cross_checks_announced


@pytest.mark.asyncio
async def test_silent_when_no_event_emitter():
    """Helper must not crash when event_emitter is None (e.g. tests)."""
    state = _state(
        metrics=_metrics([_anomaly('errors{service="payments-api"}')]),
        logs=_logs_with_pattern("checkout-service"),
    )

    # Should not raise.
    await _run_metrics_logs_cross_check(state, None)

    # divergence_findings still populated, just no events.
    assert len(state.divergence_findings) >= 1
    assert "metrics_logs" not in state.cross_checks_announced


@pytest.mark.asyncio
async def test_pluralisation():
    """1 disagreement → singular; 2+ → plural.

    To force exactly 1 divergence, we use a below-threshold log cluster
    (freq=1): D1 fires (metric service not in logs) but D2 is suppressed
    by ``_MIN_LOG_CLUSTER_FREQUENCY``.
    """
    state_one = _state(
        metrics=_metrics([_anomaly('errors{service="payments-api"}')]),
        logs=_logs_with_pattern("checkout-service", freq=1),
    )
    emitter_one = AsyncMock()
    emitter_one.emit = AsyncMock()
    await _run_metrics_logs_cross_check(state_one, emitter_one)
    one_summary = [c for c in _collect_emits(emitter_one) if c["event_type"] == "summary"][0]
    assert one_summary["details"]["divergence_count"] == 1
    assert "1 signal disagreement" in one_summary["message"]

    # Above-threshold log cluster → D1 + D2 both fire → 2 divergences.
    state_many = _state(
        metrics=_metrics([_anomaly('errors{service="payments-api"}')]),
        logs=_logs_with_pattern("checkout-service", freq=10),
    )
    emitter_many = AsyncMock()
    emitter_many.emit = AsyncMock()
    await _run_metrics_logs_cross_check(state_many, emitter_many)
    many_summary = [c for c in _collect_emits(emitter_many) if c["event_type"] == "summary"][0]
    assert many_summary["details"]["divergence_count"] >= 2
    assert "signal disagreements" in many_summary["message"]


# ── PR-C: race + re-investigation reset ───────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_invocations_emit_summary_exactly_once():
    """Both agent handlers racing to fire the cross-check must produce one summary.

    Bug #2: when log_agent and metrics_agent land results in the same
    event-loop tick, both handlers invoke the helper concurrently. Before
    the per-state lock, both could observe ``cross_checks_announced`` as
    empty and each emit the summary, doubling the timeline entry.
    """
    state = _state(
        metrics=_metrics([_anomaly('errors{service="payments-api"}')]),
        logs=_logs_with_pattern("checkout-service"),
    )
    emitter = AsyncMock()
    emitter.emit = AsyncMock()

    await asyncio.gather(
        _run_metrics_logs_cross_check(state, emitter),
        _run_metrics_logs_cross_check(state, emitter),
    )

    summaries = [c for c in _collect_emits(emitter) if c["event_type"] == "summary"]
    assert len(summaries) == 1, (
        f"Expected exactly 1 summary under concurrent invocation, got {len(summaries)}"
    )


@pytest.mark.asyncio
async def test_reset_clears_divergence_findings_and_announcement_set():
    """On re_investigating transition, stale divergences must be cleared.

    Bug #8: without reset, a second run would accumulate divergences on
    top of the first, leaving DisagreementStrip showing double-counted
    services and stale findings from the prior round.
    """
    state = _state(
        metrics=_metrics([_anomaly('errors{service="payments-api"}')]),
        logs=_logs_with_pattern("checkout-service"),
    )
    emitter = AsyncMock()
    emitter.emit = AsyncMock()

    await _run_metrics_logs_cross_check(state, emitter)
    assert len(state.divergence_findings) >= 1
    assert "metrics_logs" in state.cross_checks_announced

    reset_cross_check_state_for_reinvestigation(state)

    assert state.divergence_findings == []
    assert state.cross_checks_announced == set()
    assert id(state) not in _CROSS_CHECK_LOCKS


@pytest.mark.asyncio
async def test_reset_allows_summary_to_fire_again_on_next_run():
    """After reset, the next cross-check run must emit its own summary."""
    state = _state(
        metrics=_metrics([_anomaly('errors{service="payments-api"}')]),
        logs=_logs_with_pattern("checkout-service"),
    )
    emitter_first = AsyncMock()
    emitter_first.emit = AsyncMock()
    await _run_metrics_logs_cross_check(state, emitter_first)

    reset_cross_check_state_for_reinvestigation(state)

    emitter_second = AsyncMock()
    emitter_second.emit = AsyncMock()
    await _run_metrics_logs_cross_check(state, emitter_second)

    summaries = [c for c in _collect_emits(emitter_second) if c["event_type"] == "summary"]
    assert len(summaries) == 1
    assert summaries[0]["details"]["action"] == "cross_check_complete"

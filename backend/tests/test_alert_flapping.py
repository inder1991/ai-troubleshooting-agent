"""Tests for alert flapping detection (#26)."""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.network.alert_engine import AlertEngine, AlertRule, FlappingConfig


@pytest.fixture
def metrics():
    m = AsyncMock()
    m.query_device_metrics = AsyncMock(return_value=[])
    m.write_alert_event = AsyncMock()
    return m


@pytest.fixture
def engine(metrics):
    return AlertEngine(metrics)


def _cpu_rule():
    return AlertRule(
        id="test-cpu",
        name="High CPU",
        severity="warning",
        entity_type="device",
        entity_filter="*",
        metric="cpu_pct",
        condition="gt",
        threshold=90.0,
        duration_seconds=30,
        cooldown_seconds=0,  # no cooldown so we can fire repeatedly
    )


@pytest.mark.asyncio
async def test_flapping_suppresses_alert_after_many_transitions(engine, metrics):
    """After >5 rapid state transitions in 5 minutes, alert should be suppressed."""
    rule = _cpu_rule()
    engine.add_rule(rule)

    now = time.time()
    device_id = "switch-1"

    # Simulate 6 rapid OK->alerting->OK transitions
    for i in range(6):
        # Alerting state
        metrics.query_device_metrics.return_value = [{"value": 95.0}]
        engine._last_fired.clear()  # clear cooldown
        await engine.evaluate(device_id)

        # OK state
        metrics.query_device_metrics.return_value = [{"value": 50.0}]
        await engine.evaluate(device_id)

    # Now try to fire again — should be suppressed due to flapping
    metrics.query_device_metrics.return_value = [{"value": 95.0}]
    engine._last_fired.clear()
    fired = await engine.evaluate(device_id)

    # The alert should NOT appear in fired list (suppressed)
    assert len(fired) == 0


@pytest.mark.asyncio
async def test_normal_alert_fires_without_flapping(engine, metrics):
    """A single alert fire should not be suppressed."""
    rule = _cpu_rule()
    engine.add_rule(rule)

    metrics.query_device_metrics.return_value = [{"value": 95.0}]
    fired = await engine.evaluate("switch-2")

    assert len(fired) == 1
    assert fired[0]["rule_id"] == "test-cpu"
    assert "flapping" not in fired[0]


@pytest.mark.asyncio
async def test_flapping_state_transitions_tracked(engine, metrics):
    """Verify state transitions are recorded in _state_transitions."""
    rule = _cpu_rule()
    engine.add_rule(rule)

    device_id = "switch-3"

    # Fire once
    metrics.query_device_metrics.return_value = [{"value": 95.0}]
    await engine.evaluate(device_id)

    key = (device_id, "cpu_pct")
    assert key in engine._state_transitions
    assert len(engine._state_transitions[key]) >= 1


@pytest.mark.asyncio
async def test_flapping_transitions_pruned_outside_window(engine, metrics):
    """Old transitions outside the 5-minute window should be pruned."""
    rule = _cpu_rule()
    engine.add_rule(rule)
    device_id = "switch-4"

    # Manually add old transitions far in the past
    old_time = time.time() - FlappingConfig.FLAP_WINDOW_SECONDS - 100
    key = (device_id, "cpu_pct")
    engine._state_transitions[key] = [
        (old_time + i, "alerting" if i % 2 == 0 else "ok")
        for i in range(10)
    ]

    # Fire a new evaluation — should prune old entries and not trigger flapping
    metrics.query_device_metrics.return_value = [{"value": 95.0}]
    fired = await engine.evaluate(device_id)

    assert len(fired) == 1  # Not suppressed because old transitions are pruned


@pytest.mark.asyncio
async def test_is_flapping_check(engine):
    """Direct test of _is_flapping method."""
    now = time.time()
    device_id = "switch-5"
    metric = "cpu_pct"

    # Not flapping initially
    assert engine._is_flapping(device_id, metric, now) is False

    # Add 6 transitions (> threshold of 5)
    for i in range(6):
        engine._record_transition(device_id, metric, "alerting" if i % 2 == 0 else "ok", now + i)

    assert engine._is_flapping(device_id, metric, now + 6) is True

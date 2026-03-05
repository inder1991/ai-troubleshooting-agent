# backend/tests/test_alert_engine.py
import pytest
from unittest.mock import AsyncMock
from src.network.alert_engine import AlertEngine, AlertRule, AlertState


@pytest.fixture
def mock_metrics():
    store = AsyncMock()
    store.query_device_metrics = AsyncMock(return_value=[])
    store.write_alert_event = AsyncMock()
    return store


@pytest.fixture
def engine(mock_metrics):
    return AlertEngine(mock_metrics)


def test_add_rule(engine):
    rule = AlertRule(
        id="r1", name="High CPU", severity="warning",
        entity_type="device", entity_filter="*",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=300, cooldown_seconds=600,
    )
    engine.add_rule(rule)
    assert len(engine.rules) == 1


def test_default_rules_loaded(mock_metrics):
    engine = AlertEngine(mock_metrics, load_defaults=True)
    assert len(engine.rules) >= 5  # At least 5 default rules


@pytest.mark.asyncio
async def test_threshold_fires(engine, mock_metrics):
    rule = AlertRule(
        id="r1", name="High CPU", severity="warning",
        entity_type="device", entity_filter="dev-1",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=0, cooldown_seconds=0,
    )
    engine.add_rule(rule)
    # Metric exceeds threshold
    mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
    alerts = await engine.evaluate("dev-1")
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "warning"
    assert alerts[0]["rule_id"] == "r1"


@pytest.mark.asyncio
async def test_threshold_not_met(engine, mock_metrics):
    rule = AlertRule(
        id="r1", name="High CPU", severity="warning",
        entity_type="device", entity_filter="dev-1",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=0, cooldown_seconds=0,
    )
    engine.add_rule(rule)
    mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 50.0}]
    alerts = await engine.evaluate("dev-1")
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_cooldown_prevents_refire(engine, mock_metrics):
    rule = AlertRule(
        id="r1", name="High CPU", severity="warning",
        entity_type="device", entity_filter="dev-1",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=0, cooldown_seconds=3600,
    )
    engine.add_rule(rule)
    mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
    alerts1 = await engine.evaluate("dev-1")
    assert len(alerts1) == 1
    # Second evaluation -- should be suppressed by cooldown
    alerts2 = await engine.evaluate("dev-1")
    assert len(alerts2) == 0


@pytest.mark.asyncio
async def test_wildcard_filter(engine, mock_metrics):
    rule = AlertRule(
        id="r1", name="High CPU", severity="warning",
        entity_type="device", entity_filter="*",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=0, cooldown_seconds=0,
    )
    engine.add_rule(rule)
    mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
    alerts = await engine.evaluate("any-device-id")
    assert len(alerts) == 1

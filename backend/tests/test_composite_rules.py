"""Tests for composite (multi-condition) alert rules."""
import pytest
from unittest.mock import AsyncMock
from src.network.alert_engine import AlertEngine, AlertRule, CompositeRule


@pytest.fixture
def mock_metrics():
    m = AsyncMock()
    m.query_device_metrics = AsyncMock(return_value=[])
    m.write_alert_event = AsyncMock()
    return m


@pytest.fixture
def engine(mock_metrics):
    return AlertEngine(mock_metrics)


class TestCompositeRule:
    def test_create_and_rule(self):
        rule = CompositeRule(
            id="comp-1", name="CPU AND Memory",
            severity="critical", entity_filter="*",
            operator="AND",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 90.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 95.0},
            ],
        )
        assert rule.operator == "AND"
        assert len(rule.conditions) == 2

    def test_create_or_rule(self):
        rule = CompositeRule(
            id="comp-2", name="CPU OR Memory",
            severity="warning", entity_filter="*",
            operator="OR",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 95.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 98.0},
            ],
        )
        assert rule.operator == "OR"

    def test_add_and_list(self, engine):
        rule = CompositeRule(id="comp-1", name="Test", severity="warning",
                             conditions=[{"metric": "cpu_pct", "condition": "gt", "threshold": 90}])
        engine.add_composite_rule(rule)
        assert len(engine.get_composite_rules()) == 1

    def test_remove(self, engine):
        rule = CompositeRule(id="comp-1", name="Test", severity="warning", conditions=[])
        engine.add_composite_rule(rule)
        engine.remove_composite_rule("comp-1")
        assert len(engine.get_composite_rules()) == 0


class TestCompositeRuleEvaluation:
    @pytest.mark.asyncio
    async def test_and_rule_fires_when_both_met(self, engine, mock_metrics):
        rule = CompositeRule(
            id="comp-1", name="CPU AND Mem", severity="critical",
            entity_filter="*", operator="AND",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 90.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 95.0},
            ],
            cooldown_seconds=0,
        )
        engine.add_composite_rule(rule)

        async def mock_query(entity_id, metric, **kwargs):
            return [{"time": "now", "value": {"cpu_pct": 95.0, "mem_pct": 98.0}.get(metric, 0)}]

        mock_metrics.query_device_metrics.side_effect = mock_query
        alerts = await engine.evaluate_composites("dev-1")
        assert len(alerts) == 1
        assert alerts[0]["composite"] is True

    @pytest.mark.asyncio
    async def test_and_rule_does_not_fire_when_partial(self, engine, mock_metrics):
        rule = CompositeRule(
            id="comp-1", name="CPU AND Mem", severity="critical",
            entity_filter="*", operator="AND",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 90.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 95.0},
            ],
            cooldown_seconds=0,
        )
        engine.add_composite_rule(rule)

        async def mock_query(entity_id, metric, **kwargs):
            return [{"time": "now", "value": {"cpu_pct": 95.0, "mem_pct": 50.0}.get(metric, 0)}]

        mock_metrics.query_device_metrics.side_effect = mock_query
        alerts = await engine.evaluate_composites("dev-1")
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_or_rule_fires_when_one_met(self, engine, mock_metrics):
        rule = CompositeRule(
            id="comp-2", name="CPU OR Mem", severity="warning",
            entity_filter="*", operator="OR",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 95.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 98.0},
            ],
            cooldown_seconds=0,
        )
        engine.add_composite_rule(rule)

        async def mock_query(entity_id, metric, **kwargs):
            return [{"time": "now", "value": {"cpu_pct": 97.0, "mem_pct": 50.0}.get(metric, 0)}]

        mock_metrics.query_device_metrics.side_effect = mock_query
        alerts = await engine.evaluate_composites("dev-1")
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_or_rule_does_not_fire_when_none_met(self, engine, mock_metrics):
        rule = CompositeRule(
            id="comp-2", name="CPU OR Mem", severity="warning",
            entity_filter="*", operator="OR",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 95.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 98.0},
            ],
            cooldown_seconds=0,
        )
        engine.add_composite_rule(rule)

        async def mock_query(entity_id, metric, **kwargs):
            return [{"time": "now", "value": {"cpu_pct": 50.0, "mem_pct": 50.0}.get(metric, 0)}]

        mock_metrics.query_device_metrics.side_effect = mock_query
        alerts = await engine.evaluate_composites("dev-1")
        assert len(alerts) == 0

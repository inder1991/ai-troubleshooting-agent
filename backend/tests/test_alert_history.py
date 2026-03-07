"""Tests for alert history persistence."""
import os
import pytest
from unittest.mock import AsyncMock

from src.network.topology_store import TopologyStore
from src.network.alert_engine import AlertEngine, AlertRule


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def mock_metrics():
    m = AsyncMock()
    m.query_device_metrics = AsyncMock(return_value=[])
    m.write_alert_event = AsyncMock()
    return m


class TestAlertHistoryStore:
    def test_upsert_alert_event(self, store):
        store.upsert_alert_history(
            alert_key="r1:dev-1", rule_id="r1", rule_name="High CPU",
            entity_id="dev-1", severity="warning", metric="cpu_pct",
            value=95.0, threshold=90.0, condition="gt",
            state="firing", message="High CPU: cpu_pct=95.0",
        )
        history = store.list_alert_history()
        assert len(history) == 1
        assert history[0]["alert_key"] == "r1:dev-1"
        assert history[0]["state"] == "firing"

    def test_resolve_alert(self, store):
        store.upsert_alert_history(
            alert_key="r1:dev-1", rule_id="r1", rule_name="High CPU",
            entity_id="dev-1", severity="warning", metric="cpu_pct",
            value=95.0, threshold=90.0, condition="gt",
            state="firing", message="fired",
        )
        store.upsert_alert_history(
            alert_key="r1:dev-1", rule_id="r1", rule_name="High CPU",
            entity_id="dev-1", severity="warning", metric="cpu_pct",
            value=85.0, threshold=90.0, condition="gt",
            state="resolved", message="resolved",
        )
        history = store.list_alert_history()
        assert len(history) == 2

    def test_list_alert_history_filtered(self, store):
        store.upsert_alert_history(
            alert_key="r1:dev-1", rule_id="r1", rule_name="Rule 1",
            entity_id="dev-1", severity="critical", metric="m1",
            value=1, threshold=0, condition="gt",
            state="firing", message="",
        )
        store.upsert_alert_history(
            alert_key="r2:dev-2", rule_id="r2", rule_name="Rule 2",
            entity_id="dev-2", severity="warning", metric="m2",
            value=2, threshold=0, condition="gt",
            state="firing", message="",
        )
        critical = store.list_alert_history(severity="critical")
        assert len(critical) == 1
        assert critical[0]["severity"] == "critical"

    def test_list_alert_history_limit(self, store):
        for i in range(5):
            store.upsert_alert_history(
                alert_key=f"r{i}:dev-1", rule_id=f"r{i}", rule_name=f"Rule {i}",
                entity_id="dev-1", severity="warning", metric="m",
                value=i, threshold=0, condition="gt",
                state="firing", message="",
            )
        limited = store.list_alert_history(limit=3)
        assert len(limited) == 3

    def test_alert_history_count(self, store):
        for i in range(3):
            store.upsert_alert_history(
                alert_key=f"r{i}:dev-1", rule_id=f"r{i}", rule_name=f"Rule {i}",
                entity_id="dev-1", severity="warning", metric="m",
                value=i, threshold=0, condition="gt",
                state="firing", message="",
            )
        assert store.count_alert_history() == 3


class TestAlertEngineHistory:
    @pytest.mark.asyncio
    async def test_evaluate_persists_to_history(self, store, mock_metrics):
        engine = AlertEngine(mock_metrics)
        engine.set_store(store)
        rule = AlertRule(
            id="r1", name="CPU", severity="warning",
            entity_type="device", entity_filter="*",
            metric="cpu_pct", condition="gt", threshold=90.0,
            duration_seconds=0, cooldown_seconds=0,
        )
        engine.add_rule(rule)
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
        await engine.evaluate("dev-1")

        history = store.list_alert_history()
        assert len(history) == 1
        assert history[0]["state"] == "firing"

    @pytest.mark.asyncio
    async def test_resolve_persists_to_history(self, store, mock_metrics):
        engine = AlertEngine(mock_metrics)
        engine.set_store(store)
        rule = AlertRule(
            id="r1", name="CPU", severity="warning",
            entity_type="device", entity_filter="*",
            metric="cpu_pct", condition="gt", threshold=90.0,
            duration_seconds=0, cooldown_seconds=0,
        )
        engine.add_rule(rule)

        # Fire
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
        await engine.evaluate("dev-1")
        # Resolve
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 50.0}]
        await engine.evaluate("dev-1")

        history = store.list_alert_history()
        assert len(history) == 2
        states = [h["state"] for h in history]
        assert "firing" in states
        assert "resolved" in states

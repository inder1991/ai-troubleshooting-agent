"""Tests for maintenance window alert suppression."""
import time
import pytest
from unittest.mock import AsyncMock
from src.network.alert_engine import AlertEngine, AlertRule, MaintenanceWindow


@pytest.fixture
def mock_metrics():
    m = AsyncMock()
    m.query_device_metrics = AsyncMock(return_value=[])
    m.write_alert_event = AsyncMock()
    return m


@pytest.fixture
def engine(mock_metrics):
    return AlertEngine(mock_metrics)


class TestMaintenanceWindow:
    def test_create_window(self):
        now = time.time()
        mw = MaintenanceWindow(
            id="mw-1", name="Router Upgrade",
            start_time=now, end_time=now + 3600,
            entity_filter="router-1",
        )
        assert mw.is_active(now + 100)
        assert not mw.is_active(now + 7200)

    def test_window_wildcard(self):
        now = time.time()
        mw = MaintenanceWindow(
            id="mw-2", name="Global Maintenance",
            start_time=now, end_time=now + 3600,
            entity_filter="*",
        )
        assert mw.matches_entity("any-device")

    def test_window_specific_entity(self):
        now = time.time()
        mw = MaintenanceWindow(
            id="mw-3", name="Specific",
            start_time=now, end_time=now + 3600,
            entity_filter="dev-1",
        )
        assert mw.matches_entity("dev-1")
        assert not mw.matches_entity("dev-2")


class TestMaintenanceWindowSuppression:
    def test_add_window(self, engine):
        now = time.time()
        engine.add_maintenance_window(MaintenanceWindow(
            id="mw-1", name="Test",
            start_time=now, end_time=now + 3600,
            entity_filter="*",
        ))
        assert len(engine.list_maintenance_windows()) == 1

    def test_remove_window(self, engine):
        now = time.time()
        engine.add_maintenance_window(MaintenanceWindow(
            id="mw-1", name="Test",
            start_time=now, end_time=now + 3600,
            entity_filter="*",
        ))
        engine.remove_maintenance_window("mw-1")
        assert len(engine.list_maintenance_windows()) == 0

    @pytest.mark.asyncio
    async def test_alert_suppressed_during_window(self, engine, mock_metrics):
        now = time.time()
        engine.add_maintenance_window(MaintenanceWindow(
            id="mw-1", name="Upgrade",
            start_time=now - 60, end_time=now + 3600,
            entity_filter="dev-1",
        ))
        rule = AlertRule(
            id="r1", name="CPU", severity="warning",
            entity_type="device", entity_filter="*",
            metric="cpu_pct", condition="gt", threshold=90.0,
            duration_seconds=0, cooldown_seconds=0,
        )
        engine.add_rule(rule)
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
        alerts = await engine.evaluate("dev-1")
        assert len(alerts) == 0  # Suppressed

    @pytest.mark.asyncio
    async def test_alert_not_suppressed_for_other_entity(self, engine, mock_metrics):
        now = time.time()
        engine.add_maintenance_window(MaintenanceWindow(
            id="mw-1", name="Upgrade",
            start_time=now - 60, end_time=now + 3600,
            entity_filter="dev-1",
        ))
        rule = AlertRule(
            id="r1", name="CPU", severity="warning",
            entity_type="device", entity_filter="*",
            metric="cpu_pct", condition="gt", threshold=90.0,
            duration_seconds=0, cooldown_seconds=0,
        )
        engine.add_rule(rule)
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
        alerts = await engine.evaluate("dev-2")
        assert len(alerts) == 1  # NOT suppressed — different device

    @pytest.mark.asyncio
    async def test_expired_window_doesnt_suppress(self, engine, mock_metrics):
        now = time.time()
        engine.add_maintenance_window(MaintenanceWindow(
            id="mw-1", name="Done",
            start_time=now - 7200, end_time=now - 3600,
            entity_filter="*",
        ))
        rule = AlertRule(
            id="r1", name="CPU", severity="warning",
            entity_type="device", entity_filter="*",
            metric="cpu_pct", condition="gt", threshold=90.0,
            duration_seconds=0, cooldown_seconds=0,
        )
        engine.add_rule(rule)
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
        alerts = await engine.evaluate("dev-1")
        assert len(alerts) == 1  # Window expired, alert fires

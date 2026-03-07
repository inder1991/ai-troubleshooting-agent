"""Tests for alert rule CRUD operations."""
import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock

# Mock influxdb_client
if "influxdb_client" not in sys.modules:
    _mock_influx = types.ModuleType("influxdb_client")
    _mock_influx.Point = MagicMock()
    _mock_influx.WritePrecision = MagicMock()
    _mock_async = types.ModuleType("influxdb_client.client")
    _mock_async_mod = types.ModuleType("influxdb_client.client.influxdb_client_async")
    _mock_async_mod.InfluxDBClientAsync = MagicMock()
    sys.modules["influxdb_client"] = _mock_influx
    sys.modules["influxdb_client.client"] = _mock_async
    sys.modules["influxdb_client.client.influxdb_client_async"] = _mock_async_mod

from src.network.alert_engine import AlertEngine, AlertRule
from fastapi.testclient import TestClient
from src.api.main import app
import src.api.monitor_endpoints as monitor_mod


@pytest.fixture
def mock_metrics():
    store = AsyncMock()
    store.query_device_metrics = AsyncMock(return_value=[])
    store.write_alert_event = AsyncMock()
    return store


@pytest.fixture
def engine(mock_metrics):
    return AlertEngine(mock_metrics, load_defaults=True)


@pytest.fixture
def client(mock_metrics):
    fake_monitor = MagicMock()
    fake_monitor.alert_engine = AlertEngine(mock_metrics, load_defaults=True)
    original = monitor_mod._monitor
    monitor_mod._monitor = fake_monitor
    yield TestClient(app)
    monitor_mod._monitor = original


class TestAlertRuleEngine:
    def test_get_rule_by_id(self, engine):
        rule = engine.get_rule("default-unreachable")
        assert rule is not None
        assert rule["name"] == "Device Unreachable"

    def test_get_rule_not_found(self, engine):
        rule = engine.get_rule("nonexistent")
        assert rule is None

    def test_update_rule(self, engine):
        ok = engine.update_rule("default-unreachable", threshold=0.95, cooldown_seconds=120)
        assert ok
        rule = engine.get_rule("default-unreachable")
        assert rule["threshold"] == 0.95
        assert rule["cooldown_seconds"] == 120

    def test_update_rule_not_found(self, engine):
        ok = engine.update_rule("nonexistent", threshold=50)
        assert not ok

    def test_update_rule_enable_disable(self, engine):
        engine.update_rule("default-unreachable", enabled=False)
        rule = engine.get_rule("default-unreachable")
        assert rule["enabled"] is False

    def test_remove_rule(self, engine):
        initial = len(engine.rules)
        engine.remove_rule("default-unreachable")
        assert len(engine.rules) == initial - 1

    def test_add_custom_rule(self, engine):
        initial = len(engine.rules)
        rule = AlertRule(
            id="custom-disk", name="Disk Full", severity="critical",
            entity_type="device", entity_filter="*",
            metric="disk_pct", condition="gt", threshold=95.0,
        )
        engine.add_rule(rule)
        assert len(engine.rules) == initial + 1


class TestAlertRuleCRUDAPI:
    def test_create_rule(self, client):
        resp = client.post("/api/v4/network/monitor/alerts/rules", json={
            "id": "custom-test", "name": "Test Rule", "severity": "warning",
            "entity_type": "device", "entity_filter": "*",
            "metric": "test_metric", "condition": "gt", "threshold": 50.0,
        })
        assert resp.status_code == 200
        assert resp.json()["id"] == "custom-test"

    def test_delete_rule_api(self, client):
        client.post("/api/v4/network/monitor/alerts/rules", json={
            "id": "custom-delete", "name": "Delete Me", "severity": "info",
            "entity_type": "device", "entity_filter": "*",
            "metric": "test", "condition": "gt", "threshold": 1.0,
        })
        resp = client.delete("/api/v4/network/monitor/alerts/rules/custom-delete")
        assert resp.status_code == 200

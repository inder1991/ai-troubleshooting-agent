"""Tests for DB monitoring components."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_write_db_metric():
    from src.network.metrics_store import MetricsStore
    store = MetricsStore.__new__(MetricsStore)
    store._write_api = AsyncMock()
    store.bucket = "test"
    await store.write_db_metric("profile-1", "postgresql", "cache_hit_ratio", 0.95)
    store._write_api.write.assert_called_once()


@pytest.mark.asyncio
async def test_write_db_metrics_batch():
    from src.network.metrics_store import MetricsStore
    store = MetricsStore.__new__(MetricsStore)
    store._write_api = AsyncMock()
    store.bucket = "test"
    await store.write_db_metrics_batch("p1", "postgresql", {"cache_hit_ratio": 0.95, "deadlocks": 0.0})
    store._write_api.write.assert_called_once()


@pytest.mark.asyncio
async def test_query_db_metrics():
    from src.network.metrics_store import MetricsStore
    store = MetricsStore.__new__(MetricsStore)
    store._query_api = AsyncMock()
    store.bucket = "test"
    store.org = "testorg"
    # Mock returns empty table list
    store._query_api.query.return_value = []
    result = await store.query_db_metrics("profile-1", "cache_hit_ratio", "1h", "1m")
    assert result == []
    store._query_api.query.assert_called_once()


@pytest.mark.asyncio
async def test_db_monitor_collect_cycle():
    from src.database.db_monitor import DBMonitor
    from src.database.adapters.mock_adapter import MockDatabaseAdapter
    from src.database.adapters.registry import DatabaseAdapterRegistry

    mock_profile_store = MagicMock()
    mock_profile_store.list_all.return_value = [
        {"id": "p1", "name": "test-pg", "engine": "postgresql",
         "host": "localhost", "port": 5432, "database": "testdb",
         "username": "u", "password": "p"},
    ]

    registry = DatabaseAdapterRegistry()
    adapter = MockDatabaseAdapter(engine="postgresql", host="localhost", port=5432, database="testdb")
    await adapter.connect()
    registry.register("p1", adapter, profile_id="p1")

    mock_metrics = AsyncMock()
    mock_alert_engine = AsyncMock()
    mock_broadcast = AsyncMock()

    monitor = DBMonitor(
        profile_store=mock_profile_store,
        adapter_registry=registry,
        metrics_store=mock_metrics,
        alert_engine=mock_alert_engine,
        broadcast_callback=mock_broadcast,
    )

    await monitor._collect_cycle()

    assert mock_metrics.write_db_metrics_batch.call_count >= 1
    mock_broadcast.assert_called_once()


@pytest.mark.asyncio
async def test_db_monitor_snapshot():
    from src.database.db_monitor import DBMonitor

    mock_profile_store = MagicMock()
    mock_profile_store.list_all.return_value = []

    monitor = DBMonitor(
        profile_store=mock_profile_store,
        adapter_registry=MagicMock(),
        metrics_store=None,
        alert_engine=None,
        broadcast_callback=AsyncMock(),
    )

    snapshot = monitor.get_snapshot()
    assert snapshot["running"] is False
    assert snapshot["profiles"] == []


def test_default_db_alert_rules():
    from src.database.db_alert_rules import DEFAULT_DB_ALERT_RULES
    assert len(DEFAULT_DB_ALERT_RULES) >= 5
    rule_ids = [r.id for r in DEFAULT_DB_ALERT_RULES]
    assert "db-conn-pool-warning" in rule_ids
    assert "db-cache-hit-low" in rule_ids
    for rule in DEFAULT_DB_ALERT_RULES:
        assert rule.entity_type == "database"

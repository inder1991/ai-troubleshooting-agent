"""Integration tests for NetworkMonitor with SNMP, alerts, and InfluxDB."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_monitor_accepts_metrics_store():
    """Monitor should accept optional metrics_store and create sub-components."""
    from src.network.monitor import NetworkMonitor

    store = MagicMock()
    store.list_devices = MagicMock(return_value=[])
    store.list_device_statuses = MagicMock(return_value=[])
    store.list_link_metrics = MagicMock(return_value=[])
    store.list_active_drift_events = MagicMock(return_value=[])
    store.list_discovery_candidates = MagicMock(return_value=[])

    kg = MagicMock()
    kg.graph = MagicMock()
    kg.graph.nodes = MagicMock(return_value=[])

    adapters = MagicMock()
    adapters.device_bindings = MagicMock(return_value={})
    adapters.all_instances = MagicMock(return_value={})

    metrics_store = AsyncMock()

    monitor = NetworkMonitor(store, kg, adapters, metrics_store=metrics_store)
    assert monitor.snmp_collector is not None
    assert monitor.alert_engine is not None
    assert monitor.metrics_store is metrics_store


@pytest.mark.asyncio
async def test_monitor_without_metrics_store():
    """Monitor should work without metrics_store (SNMP/alerts disabled)."""
    from src.network.monitor import NetworkMonitor

    store = MagicMock()
    kg = MagicMock()
    adapters = MagicMock()

    monitor = NetworkMonitor(store, kg, adapters)
    assert monitor.snmp_collector is None
    assert monitor.alert_engine is None
    assert monitor.metrics_store is None


@pytest.mark.asyncio
async def test_snapshot_includes_alerts():
    """Snapshot should include alerts field."""
    from src.network.monitor import NetworkMonitor

    store = MagicMock()
    store.list_device_statuses = MagicMock(return_value=[])
    store.list_link_metrics = MagicMock(return_value=[])
    store.list_active_drift_events = MagicMock(return_value=[])
    store.list_discovery_candidates = MagicMock(return_value=[])

    kg = MagicMock()
    adapters = MagicMock()
    metrics_store = AsyncMock()

    monitor = NetworkMonitor(store, kg, adapters, metrics_store=metrics_store)
    snap = monitor.get_snapshot()
    assert "alerts" in snap
    assert isinstance(snap["alerts"], list)

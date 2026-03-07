"""Tests for monitor WebSocket broadcast integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMonitorBroadcast:
    def test_monitor_accepts_broadcast_callback(self):
        from src.network.monitor import NetworkMonitor
        store = MagicMock()
        store.list_devices.return_value = []
        store.list_device_statuses.return_value = []
        store.list_active_drift_events.return_value = []
        store.list_discovery_candidates.return_value = []
        store.list_link_metrics.return_value = []
        callback = AsyncMock()
        monitor = NetworkMonitor(store, MagicMock(), MagicMock(), broadcast_callback=callback)
        assert monitor._broadcast_callback is callback

    @pytest.mark.asyncio
    async def test_broadcast_called_after_cycle(self):
        from src.network.monitor import NetworkMonitor
        store = MagicMock()
        store.list_devices.return_value = []
        store.list_device_statuses.return_value = []
        store.list_active_drift_events.return_value = []
        store.list_discovery_candidates.return_value = []
        store.list_link_metrics.return_value = []
        store.prune_metric_history = MagicMock()
        callback = AsyncMock()
        monitor = NetworkMonitor(store, MagicMock(), MagicMock(), broadcast_callback=callback)
        monitor.adapters = MagicMock()
        monitor.adapters.all_instances.return_value = {}
        monitor.adapters.device_bindings.return_value = {}
        with patch("src.network.monitor.async_ping", new=None):
            await monitor._collect_cycle()
        callback.assert_awaited_once()
        msg = callback.call_args[0][0]
        assert msg["type"] == "monitor_update"
        assert "data" in msg

    @pytest.mark.asyncio
    async def test_broadcast_includes_alert_count(self):
        from src.network.monitor import NetworkMonitor
        store = MagicMock()
        store.list_devices.return_value = []
        store.list_device_statuses.return_value = []
        store.list_active_drift_events.return_value = []
        store.list_discovery_candidates.return_value = []
        store.list_link_metrics.return_value = []
        store.prune_metric_history = MagicMock()
        callback = AsyncMock()
        monitor = NetworkMonitor(store, MagicMock(), MagicMock(), broadcast_callback=callback)
        monitor.adapters = MagicMock()
        monitor.adapters.all_instances.return_value = {}
        monitor.adapters.device_bindings.return_value = {}
        monitor._latest_alerts = [{"key": "a1"}, {"key": "a2"}]
        with patch("src.network.monitor.async_ping", new=None):
            await monitor._collect_cycle()
        msg = callback.call_args[0][0]
        assert msg["data"]["active_alerts"] == 2

    @pytest.mark.asyncio
    async def test_no_broadcast_when_no_callback(self):
        from src.network.monitor import NetworkMonitor
        store = MagicMock()
        store.list_devices.return_value = []
        store.list_device_statuses.return_value = []
        store.list_active_drift_events.return_value = []
        store.list_discovery_candidates.return_value = []
        store.list_link_metrics.return_value = []
        store.prune_metric_history = MagicMock()
        monitor = NetworkMonitor(store, MagicMock(), MagicMock())
        monitor.adapters = MagicMock()
        monitor.adapters.all_instances.return_value = {}
        monitor.adapters.device_bindings.return_value = {}
        with patch("src.network.monitor.async_ping", new=None):
            await monitor._collect_cycle()
        # Should not raise — just no broadcast

    @pytest.mark.asyncio
    async def test_broadcast_failure_does_not_crash_cycle(self):
        from src.network.monitor import NetworkMonitor
        store = MagicMock()
        store.list_devices.return_value = []
        store.list_device_statuses.return_value = []
        store.list_active_drift_events.return_value = []
        store.list_discovery_candidates.return_value = []
        store.list_link_metrics.return_value = []
        store.prune_metric_history = MagicMock()
        callback = AsyncMock(side_effect=Exception("ws error"))
        monitor = NetworkMonitor(store, MagicMock(), MagicMock(), broadcast_callback=callback)
        monitor.adapters = MagicMock()
        monitor.adapters.all_instances.return_value = {}
        monitor.adapters.device_bindings.return_value = {}
        with patch("src.network.monitor.async_ping", new=None):
            await monitor._collect_cycle()
        # Should not raise

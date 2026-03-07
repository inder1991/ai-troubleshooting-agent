"""Tests for alert escalation integration in monitor cycle."""
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.notification_dispatcher import NotificationDispatcher, EscalationPolicy
from src.network.models import NotificationChannel, ChannelType


class TestEscalationCheck:
    @pytest.mark.asyncio
    async def test_check_escalations_sends_to_target(self):
        dispatcher = NotificationDispatcher()
        ch_email = NotificationChannel(
            id="ch-email", name="Email", channel_type=ChannelType.EMAIL,
            enabled=True, config={"smtp_host": "localhost", "to_addrs": ["a@b.com"]},
        )
        dispatcher.add_channel(ch_email)
        policy = EscalationPolicy(
            id="esc-1", name="Crit Escalation",
            escalate_after_seconds=60,
            source_channel_ids=["ch-slack"],
            target_channel_ids=["ch-email"],
            severity_filter=["critical"],
        )
        dispatcher.add_escalation(policy)
        dispatcher._send = AsyncMock()

        alerts = [
            {"key": "alert-1", "severity": "critical", "fired_at": time.time() - 120, "acknowledged": False},
        ]
        escalated = await dispatcher.check_escalations(alerts)
        assert len(escalated) == 1
        assert escalated[0]["key"] == "alert-1"
        dispatcher._send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acknowledged_alert_not_escalated(self):
        dispatcher = NotificationDispatcher()
        policy = EscalationPolicy(
            id="esc-1", name="P", escalate_after_seconds=60,
            target_channel_ids=["ch-1"], severity_filter=["critical"],
        )
        dispatcher.add_escalation(policy)
        alerts = [{"key": "a1", "severity": "critical", "fired_at": time.time() - 120, "acknowledged": True}]
        escalated = await dispatcher.check_escalations(alerts)
        assert len(escalated) == 0

    @pytest.mark.asyncio
    async def test_not_escalated_before_threshold(self):
        dispatcher = NotificationDispatcher()
        policy = EscalationPolicy(
            id="esc-1", name="P", escalate_after_seconds=300,
            target_channel_ids=["ch-1"], severity_filter=["critical"],
        )
        dispatcher.add_escalation(policy)
        alerts = [{"key": "a1", "severity": "critical", "fired_at": time.time() - 60, "acknowledged": False}]
        escalated = await dispatcher.check_escalations(alerts)
        assert len(escalated) == 0

    @pytest.mark.asyncio
    async def test_same_alert_not_escalated_twice(self):
        dispatcher = NotificationDispatcher()
        ch = NotificationChannel(id="ch-1", name="CH", channel_type=ChannelType.WEBHOOK, enabled=True, config={"url": "http://x"})
        dispatcher.add_channel(ch)
        policy = EscalationPolicy(
            id="esc-1", name="P", escalate_after_seconds=60,
            target_channel_ids=["ch-1"], severity_filter=["critical"],
        )
        dispatcher.add_escalation(policy)
        dispatcher._send = AsyncMock()
        alerts = [{"key": "a1", "severity": "critical", "fired_at": time.time() - 120, "acknowledged": False}]
        await dispatcher.check_escalations(alerts)
        result = await dispatcher.check_escalations(alerts)
        assert len(result) == 0  # Already escalated


class TestEscalationInMonitorCycle:
    @pytest.mark.asyncio
    async def test_escalation_runs_after_alert_pass(self):
        from src.network.monitor import NetworkMonitor
        store = MagicMock()
        store.list_devices.return_value = []
        store.list_device_statuses.return_value = []
        store.list_active_drift_events.return_value = []
        store.list_discovery_candidates.return_value = []
        store.list_link_metrics.return_value = []
        store.prune_metric_history = MagicMock()

        mock_metrics = MagicMock()
        monitor = NetworkMonitor(store, MagicMock(), MagicMock(), metrics_store=mock_metrics)
        monitor.adapters = MagicMock()
        monitor.adapters.all_instances.return_value = {}
        monitor.adapters.device_bindings.return_value = {}
        monitor.alert_engine = MagicMock()
        monitor.alert_engine.evaluate_all = AsyncMock(return_value=[])
        monitor.alert_engine.get_active_alerts.return_value = [
            {"key": "a1", "severity": "critical", "fired_at": 0, "acknowledged": False}
        ]
        mock_dispatcher = MagicMock()
        mock_dispatcher.check_escalations = AsyncMock(return_value=[])
        monitor.alert_engine._dispatcher = mock_dispatcher

        with patch("src.network.monitor.async_ping", new=None):
            await monitor._collect_cycle()
        mock_dispatcher.check_escalations.assert_awaited_once()

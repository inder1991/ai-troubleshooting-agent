"""Tests for alert escalation policies."""
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.network.notification_dispatcher import NotificationDispatcher, EscalationPolicy
from src.network.models import NotificationChannel, ChannelType


@pytest.fixture
def dispatcher():
    return NotificationDispatcher()


class TestEscalationPolicy:
    def test_create_policy(self):
        policy = EscalationPolicy(
            id="esc-1", name="On-Call Escalation",
            escalate_after_seconds=300,
            source_channel_ids=["slack-oncall"],
            target_channel_ids=["pagerduty-oncall"],
            severity_filter=["critical"],
        )
        assert policy.escalate_after_seconds == 300

    def test_add_policy(self, dispatcher):
        policy = EscalationPolicy(
            id="esc-1", name="Test",
            escalate_after_seconds=300,
            source_channel_ids=["ch-1"],
            target_channel_ids=["ch-2"],
        )
        dispatcher.add_escalation(policy)
        assert len(dispatcher.list_escalations()) == 1

    def test_remove_policy(self, dispatcher):
        policy = EscalationPolicy(
            id="esc-1", name="Test",
            escalate_after_seconds=300,
            source_channel_ids=["ch-1"],
            target_channel_ids=["ch-2"],
        )
        dispatcher.add_escalation(policy)
        dispatcher.remove_escalation("esc-1")
        assert len(dispatcher.list_escalations()) == 0


class TestEscalationExecution:
    @pytest.mark.asyncio
    async def test_escalation_fires_for_unacked_alert(self, dispatcher):
        ch = NotificationChannel(id="ch-target", name="PD", channel_type=ChannelType.WEBHOOK,
                                 config={"url": "http://example.com"})
        dispatcher.add_channel(ch)

        policy = EscalationPolicy(
            id="esc-1", name="Test",
            escalate_after_seconds=0,  # Immediate for testing
            source_channel_ids=["ch-1"],
            target_channel_ids=["ch-target"],
            severity_filter=["critical"],
        )
        dispatcher.add_escalation(policy)

        alert = {
            "key": "r1:dev-1", "severity": "critical",
            "fired_at": time.time() - 600, "acknowledged": False,
            "rule_name": "Test", "message": "test",
        }

        with patch.object(dispatcher, '_send', new_callable=AsyncMock) as mock_send:
            escalated = await dispatcher.check_escalations([alert])
            assert len(escalated) == 1
            assert escalated[0]["key"] == "r1:dev-1"
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_acknowledged_alerts_not_escalated(self, dispatcher):
        policy = EscalationPolicy(
            id="esc-1", name="Test",
            escalate_after_seconds=0,
            source_channel_ids=["ch-1"],
            target_channel_ids=["ch-2"],
            severity_filter=["critical"],
        )
        dispatcher.add_escalation(policy)

        alert = {
            "key": "r1:dev-1", "severity": "critical",
            "fired_at": time.time() - 600, "acknowledged": True,
            "rule_name": "Test", "message": "test",
        }
        escalated = await dispatcher.check_escalations([alert])
        assert len(escalated) == 0

    @pytest.mark.asyncio
    async def test_already_escalated_not_repeated(self, dispatcher):
        ch = NotificationChannel(id="ch-target", name="PD", channel_type=ChannelType.WEBHOOK,
                                 config={"url": "http://example.com"})
        dispatcher.add_channel(ch)

        policy = EscalationPolicy(
            id="esc-1", name="Test",
            escalate_after_seconds=0,
            source_channel_ids=["ch-1"],
            target_channel_ids=["ch-target"],
            severity_filter=["critical"],
        )
        dispatcher.add_escalation(policy)

        alert = {
            "key": "r1:dev-1", "severity": "critical",
            "fired_at": time.time() - 600, "acknowledged": False,
            "rule_name": "Test", "message": "test",
        }

        with patch.object(dispatcher, '_send', new_callable=AsyncMock):
            await dispatcher.check_escalations([alert])
            # Second call should not re-escalate
            escalated2 = await dispatcher.check_escalations([alert])
            assert len(escalated2) == 0

    @pytest.mark.asyncio
    async def test_severity_filter(self, dispatcher):
        policy = EscalationPolicy(
            id="esc-1", name="Test",
            escalate_after_seconds=0,
            source_channel_ids=["ch-1"],
            target_channel_ids=["ch-2"],
            severity_filter=["critical"],  # Only critical
        )
        dispatcher.add_escalation(policy)

        alert = {
            "key": "r1:dev-1", "severity": "warning",  # warning, not critical
            "fired_at": time.time() - 600, "acknowledged": False,
            "rule_name": "Test", "message": "test",
        }
        escalated = await dispatcher.check_escalations([alert])
        assert len(escalated) == 0  # Not escalated — wrong severity

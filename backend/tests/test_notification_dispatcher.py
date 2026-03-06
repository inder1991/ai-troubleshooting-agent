"""Tests for notification dispatcher."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.network.models import (
    NotificationChannel,
    NotificationRouting,
    ChannelType,
)
from src.network.notification_dispatcher import NotificationDispatcher


@pytest.fixture
def dispatcher():
    d = NotificationDispatcher()
    d.add_channel(NotificationChannel(
        id="wh-1", name="Test Webhook",
        channel_type=ChannelType.WEBHOOK,
        config={"url": "https://hooks.example.com/alert"},
    ))
    d.add_channel(NotificationChannel(
        id="sl-1", name="Test Slack",
        channel_type=ChannelType.SLACK,
        config={"webhook_url": "https://hooks.slack.com/services/T/B/x"},
    ))
    d.add_routing(NotificationRouting(
        id="rt-1",
        severity_filter=["critical"],
        channel_ids=["wh-1", "sl-1"],
    ))
    d.add_routing(NotificationRouting(
        id="rt-2",
        severity_filter=["warning"],
        channel_ids=["wh-1"],
    ))
    return d


def _make_alert(severity="critical"):
    return {
        "key": "rule-1:device-1",
        "rule_id": "rule-1",
        "rule_name": "Device Unreachable",
        "entity_id": "device-1",
        "severity": severity,
        "metric": "packet_loss",
        "value": 1.0,
        "threshold": 0.99,
        "condition": "gt",
        "fired_at": 1709740800.0,
        "acknowledged": False,
        "message": "device-1: packet_loss 1.0 > 0.99",
    }


@pytest.mark.asyncio
async def test_dispatch_critical_hits_both_channels(dispatcher):
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("critical"))
        wh.assert_called_once()
        sl.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_warning_hits_webhook_only(dispatcher):
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("warning"))
        wh.assert_called_once()
        sl.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_info_hits_nothing(dispatcher):
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("info"))
        wh.assert_not_called()
        sl.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_skips_disabled_channel(dispatcher):
    dispatcher._channels["wh-1"].enabled = False
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("critical"))
        wh.assert_not_called()
        sl.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_skips_disabled_routing(dispatcher):
    dispatcher._routings[0].enabled = False
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("critical"))
        wh.assert_not_called()
        sl.assert_not_called()


@pytest.mark.asyncio
async def test_sender_error_does_not_propagate(dispatcher):
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock,
                      side_effect=Exception("network error")) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("critical"))
        sl.assert_called_once()


def test_remove_channel(dispatcher):
    dispatcher.remove_channel("wh-1")
    assert "wh-1" not in dispatcher._channels


def test_remove_routing(dispatcher):
    dispatcher.remove_routing("rt-1")
    assert len(dispatcher._routings) == 1


def test_list_channels(dispatcher):
    channels = dispatcher.list_channels()
    assert len(channels) == 2


def test_list_routings(dispatcher):
    routings = dispatcher.list_routings()
    assert len(routings) == 2

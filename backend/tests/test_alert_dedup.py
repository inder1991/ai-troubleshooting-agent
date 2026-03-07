"""Tests for alert deduplication in NotificationDispatcher."""
import time
import pytest
from unittest.mock import AsyncMock, patch

from src.network.models import (
    NotificationChannel,
    NotificationRouting,
    ChannelType,
)
from src.network.notification_dispatcher import NotificationDispatcher


def _make_dispatcher(dedup_window_seconds: int = 300) -> NotificationDispatcher:
    d = NotificationDispatcher(dedup_window_seconds=dedup_window_seconds)
    d.add_channel(NotificationChannel(
        id="ch-1", name="Webhook",
        channel_type=ChannelType.WEBHOOK,
        config={"url": "https://hooks.example.com/alert"},
    ))
    d.add_routing(NotificationRouting(
        id="rt-1",
        severity_filter=["critical"],
        channel_ids=["ch-1"],
    ))
    return d


def _make_alert(key: str = "rule-1:dev-1", **overrides) -> dict:
    alert = {
        "key": key,
        "rule_id": "rule-1",
        "rule_name": "High Packet Loss",
        "entity_id": "dev-1",
        "severity": "critical",
        "metric": "packet_loss",
        "value": 1.0,
        "threshold": 0.99,
        "condition": "gt",
        "fired_at": time.time(),
        "acknowledged": False,
        "message": "dev-1: packet_loss 1.0 > 0.99",
    }
    alert.update(overrides)
    return alert


@pytest.mark.asyncio
async def test_first_dispatch_sends():
    """First dispatch of an alert key should send the notification."""
    d = _make_dispatcher()
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert())
        assert mock_send.call_count == 1


@pytest.mark.asyncio
async def test_duplicate_suppressed():
    """Second dispatch of the same alert key should be suppressed."""
    d = _make_dispatcher()
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert("rule-1:dev-1"))
        await d.dispatch(_make_alert("rule-1:dev-1"))
        assert mock_send.call_count == 1


@pytest.mark.asyncio
async def test_different_keys_both_send():
    """Different alert keys should each send independently."""
    d = _make_dispatcher()
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert("rule-1:dev-1"))
        await d.dispatch(_make_alert("rule-2:dev-2"))
        assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_resolved_bypasses_dedup():
    """Resolved alerts should always send, even if the key was seen before."""
    d = _make_dispatcher()
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert("rule-1:dev-1"))
        await d.dispatch(_make_alert("rule-1:dev-1", resolved=True))
        assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_escalated_bypasses_dedup():
    """Escalated alerts should always send, even if the key was seen before."""
    d = _make_dispatcher()
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert("rule-1:dev-1"))
        await d.dispatch(_make_alert("rule-1:dev-1", escalated=True))
        assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_dedup_window_zero_disables_suppression():
    """With dedup_window_seconds=0, duplicates are NOT suppressed."""
    d = _make_dispatcher(dedup_window_seconds=0)
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert("rule-1:dev-1"))
        await d.dispatch(_make_alert("rule-1:dev-1"))
        assert mock_send.call_count == 2

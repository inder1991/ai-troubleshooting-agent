"""Tests for MS Teams notification channel with Adaptive Card support."""
import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.network.models import (
    NotificationChannel,
    ChannelType,
)
from src.network.notification_dispatcher import NotificationDispatcher


TEAMS_WEBHOOK_URL = "https://outlook.office.com/webhook/test-teams-hook"

SAMPLE_ALERT = {
    "key": "rule-1:switch-core-01",
    "rule_id": "rule-1",
    "rule_name": "High Packet Loss",
    "entity_id": "switch-core-01",
    "severity": "critical",
    "metric": "packet_loss",
    "value": 0.95,
    "threshold": 0.5,
    "condition": "gt",
    "fired_at": 1709740800.0,
    "acknowledged": False,
    "message": "switch-core-01: packet_loss 0.95 > 0.5",
}


# ── Enum & model tests ──────────────────────────────────────────────


def test_channel_type_teams_enum_value():
    """ChannelType.TEAMS enum value equals 'teams'."""
    assert ChannelType.TEAMS.value == "teams"


def test_create_notification_channel_with_teams_type():
    """Creating a NotificationChannel with channel_type=ChannelType.TEAMS works."""
    ch = NotificationChannel(
        id="teams-1",
        name="Ops Teams Channel",
        channel_type=ChannelType.TEAMS,
        config={"webhook_url": TEAMS_WEBHOOK_URL},
    )
    assert ch.channel_type == ChannelType.TEAMS
    assert ch.config["webhook_url"] == TEAMS_WEBHOOK_URL


# ── _send() dispatch tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_teams_calls_httpx_post():
    """_send() with a Teams channel calls httpx.AsyncClient.post with the webhook URL."""
    dispatcher = NotificationDispatcher()
    ch = NotificationChannel(
        id="teams-1",
        name="Ops Teams Channel",
        channel_type=ChannelType.TEAMS,
        config={"webhook_url": TEAMS_WEBHOOK_URL},
    )
    dispatcher.add_channel(ch)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_response)
    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.network.notification_dispatcher.httpx") as mock_httpx, \
         patch("src.network.notification_dispatcher.HAS_HTTPX", True):
        mock_httpx.AsyncClient.return_value = mock_client
        await dispatcher._send(ch, SAMPLE_ALERT)

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args.args[0] == TEAMS_WEBHOOK_URL or call_args.kwargs.get("url") == TEAMS_WEBHOOK_URL


@pytest.mark.asyncio
async def test_send_teams_adaptive_card_payload():
    """The payload sent contains an Adaptive Card structure."""
    dispatcher = NotificationDispatcher()
    ch = NotificationChannel(
        id="teams-1",
        name="Ops Teams Channel",
        channel_type=ChannelType.TEAMS,
        config={"webhook_url": TEAMS_WEBHOOK_URL},
    )
    dispatcher.add_channel(ch)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_response)
    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.network.notification_dispatcher.httpx") as mock_httpx, \
         patch("src.network.notification_dispatcher.HAS_HTTPX", True):
        mock_httpx.AsyncClient.return_value = mock_client
        await dispatcher._send(ch, SAMPLE_ALERT)

    call_args = mock_post.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")

    # Top-level structure
    assert payload["type"] == "message"
    assert len(payload["attachments"]) == 1

    attachment = payload["attachments"][0]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"

    card = attachment["content"]
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"
    assert card["$schema"] == "http://adaptivecards.io/schemas/adaptive-card.json"

    # Body: title text block
    body = card["body"]
    title_block = body[0]
    assert title_block["type"] == "TextBlock"
    assert "[CRITICAL]" in title_block["text"]
    assert "High Packet Loss" in title_block["text"]
    assert title_block["color"] == "attention"  # critical maps to attention

    # Body: fact set
    fact_set = body[1]
    assert fact_set["type"] == "FactSet"
    facts = {f["title"]: f["value"] for f in fact_set["facts"]}
    assert facts["Entity"] == "switch-core-01"
    assert "packet_loss" in facts["Metric"]
    assert "0.95" in facts["Metric"]
    assert facts["Message"] == "switch-core-01: packet_loss 0.95 > 0.5"


@pytest.mark.asyncio
async def test_send_teams_warning_severity_color():
    """Warning severity maps to 'warning' color in the Adaptive Card."""
    dispatcher = NotificationDispatcher()
    ch = NotificationChannel(
        id="teams-1",
        name="Ops Teams Channel",
        channel_type=ChannelType.TEAMS,
        config={"webhook_url": TEAMS_WEBHOOK_URL},
    )
    dispatcher.add_channel(ch)

    warning_alert = {**SAMPLE_ALERT, "severity": "warning"}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_response)
    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.network.notification_dispatcher.httpx") as mock_httpx, \
         patch("src.network.notification_dispatcher.HAS_HTTPX", True):
        mock_httpx.AsyncClient.return_value = mock_client
        await dispatcher._send(ch, warning_alert)

    call_args = mock_post.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")
    title_block = payload["attachments"][0]["content"]["body"][0]
    assert title_block["color"] == "warning"


@pytest.mark.asyncio
async def test_send_teams_no_httpx_logs_warning(caplog):
    """Gracefully handles missing httpx: logs warning, doesn't raise."""
    dispatcher = NotificationDispatcher()
    ch = NotificationChannel(
        id="teams-1",
        name="Ops Teams Channel",
        channel_type=ChannelType.TEAMS,
        config={"webhook_url": TEAMS_WEBHOOK_URL},
    )
    dispatcher.add_channel(ch)

    with patch("src.network.notification_dispatcher.HAS_HTTPX", False), \
         caplog.at_level(logging.WARNING):
        # Should not raise
        await dispatcher._send_teams(ch, SAMPLE_ALERT)

    assert any("httpx" in record.message.lower() and "teams" in record.message.lower()
               for record in caplog.records), \
        f"Expected warning about httpx/Teams, got: {[r.message for r in caplog.records]}"

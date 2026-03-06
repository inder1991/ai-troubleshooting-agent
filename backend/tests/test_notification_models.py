"""Tests for notification channel and routing models."""
import pytest
from pydantic import ValidationError

from src.network.models import (
    NotificationChannel,
    NotificationRouting,
    ChannelType,
)


def test_webhook_channel_valid():
    ch = NotificationChannel(
        id="wh-1",
        name="Ops Webhook",
        channel_type=ChannelType.WEBHOOK,
        config={"url": "https://hooks.example.com/alert"},
    )
    assert ch.channel_type == ChannelType.WEBHOOK
    assert ch.enabled is True


def test_slack_channel_valid():
    ch = NotificationChannel(
        id="sl-1",
        name="Ops Slack",
        channel_type=ChannelType.SLACK,
        config={"webhook_url": "https://hooks.slack.com/services/T/B/x"},
    )
    assert ch.channel_type == ChannelType.SLACK


def test_email_channel_valid():
    ch = NotificationChannel(
        id="em-1",
        name="Ops Email",
        channel_type=ChannelType.EMAIL,
        config={
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "from_addr": "alerts@example.com",
            "to_addrs": ["oncall@example.com"],
        },
    )
    assert ch.config["smtp_port"] == 587


def test_pagerduty_channel_valid():
    ch = NotificationChannel(
        id="pd-1",
        name="Ops PagerDuty",
        channel_type=ChannelType.PAGERDUTY,
        config={"routing_key": "abc123"},
    )
    assert ch.channel_type == ChannelType.PAGERDUTY


def test_channel_type_invalid():
    with pytest.raises(ValidationError):
        NotificationChannel(
            id="bad", name="Bad", channel_type="sms", config={}
        )


def test_routing_rule_valid():
    rule = NotificationRouting(
        id="rt-1",
        severity_filter=["critical", "warning"],
        channel_ids=["wh-1", "sl-1"],
    )
    assert len(rule.severity_filter) == 2
    assert rule.enabled is True


def test_routing_rule_empty_channels():
    with pytest.raises(ValidationError):
        NotificationRouting(
            id="rt-bad",
            severity_filter=["critical"],
            channel_ids=[],
        )

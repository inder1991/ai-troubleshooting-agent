"""Notification dispatcher — routes alerts to configured channels."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .models import ChannelType, NotificationChannel, NotificationRouting

logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import smtplib
    from email.mime.text import MIMEText
    HAS_SMTP = True
except ImportError:
    HAS_SMTP = False


@dataclass
class EscalationPolicy:
    id: str
    name: str
    escalate_after_seconds: int = 300
    source_channel_ids: list[str] = field(default_factory=list)
    target_channel_ids: list[str] = field(default_factory=list)
    severity_filter: list[str] = field(default_factory=lambda: ["critical"])
    enabled: bool = True


class NotificationDispatcher:
    """Routes fired alerts to notification channels based on routing rules."""

    def __init__(self) -> None:
        self._channels: dict[str, NotificationChannel] = {}
        self._routings: list[NotificationRouting] = []
        self._escalations: list[EscalationPolicy] = []
        self._escalated_keys: set[str] = set()

    def add_channel(self, channel: NotificationChannel) -> None:
        self._channels[channel.id] = channel

    def remove_channel(self, channel_id: str) -> None:
        self._channels.pop(channel_id, None)

    def list_channels(self) -> list[dict]:
        return [ch.model_dump() for ch in self._channels.values()]

    def add_routing(self, routing: NotificationRouting) -> None:
        self._routings.append(routing)

    def remove_routing(self, routing_id: str) -> None:
        self._routings = [r for r in self._routings if r.id != routing_id]

    def list_routings(self) -> list[dict]:
        return [r.model_dump() for r in self._routings]

    async def dispatch(self, alert: dict) -> None:
        severity = alert.get("severity", "")
        target_channel_ids: set[str] = set()

        for routing in self._routings:
            if not routing.enabled:
                continue
            if severity in routing.severity_filter:
                target_channel_ids.update(routing.channel_ids)

        tasks = []
        for ch_id in target_channel_ids:
            channel = self._channels.get(ch_id)
            if not channel or not channel.enabled:
                continue
            tasks.append(self._send(channel, alert))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def dispatch_batch(self, alerts: list[dict]) -> None:
        for alert in alerts:
            await self.dispatch(alert)

    def add_escalation(self, policy: EscalationPolicy) -> None:
        self._escalations.append(policy)

    def remove_escalation(self, policy_id: str) -> None:
        self._escalations = [p for p in self._escalations if p.id != policy_id]

    def list_escalations(self) -> list[dict]:
        return [
            {"id": p.id, "name": p.name,
             "escalate_after_seconds": p.escalate_after_seconds,
             "source_channel_ids": p.source_channel_ids,
             "target_channel_ids": p.target_channel_ids,
             "severity_filter": p.severity_filter, "enabled": p.enabled}
            for p in self._escalations
        ]

    async def check_escalations(self, active_alerts: list[dict]) -> list[dict]:
        """Check if any unacknowledged alerts need escalation."""
        escalated = []
        now = time.time()
        for alert in active_alerts:
            if alert.get("acknowledged"):
                continue
            key = alert.get("key", "")
            if key in self._escalated_keys:
                continue
            severity = alert.get("severity", "")
            fired_at = alert.get("fired_at", now)

            for policy in self._escalations:
                if not policy.enabled:
                    continue
                if severity not in policy.severity_filter:
                    continue
                if now - fired_at < policy.escalate_after_seconds:
                    continue

                # Escalate: send to target channels
                for ch_id in policy.target_channel_ids:
                    channel = self._channels.get(ch_id)
                    if channel and channel.enabled:
                        escalation_alert = {
                            **alert,
                            "escalated": True,
                            "escalation_policy": policy.name,
                        }
                        try:
                            await self._send(channel, escalation_alert)
                        except Exception:
                            logger.exception("Escalation send failed for %s", ch_id)

                self._escalated_keys.add(key)
                escalated.append({"key": key, "policy": policy.id})

        return escalated

    async def _send(self, channel: NotificationChannel, alert: dict) -> None:
        try:
            if channel.channel_type == ChannelType.WEBHOOK:
                await self._send_webhook(channel, alert)
            elif channel.channel_type == ChannelType.SLACK:
                await self._send_slack(channel, alert)
            elif channel.channel_type == ChannelType.EMAIL:
                await self._send_email(channel, alert)
            elif channel.channel_type == ChannelType.PAGERDUTY:
                await self._send_pagerduty(channel, alert)
            elif channel.channel_type == ChannelType.TEAMS:
                await self._send_teams(channel, alert)
        except Exception:
            logger.exception("Failed to send alert to channel %s", channel.id)

    async def _send_webhook(self, channel: NotificationChannel, alert: dict) -> None:
        if not HAS_HTTPX:
            logger.warning("httpx not installed — cannot send webhook")
            return
        url = channel.config.get("url", "")
        headers = channel.config.get("headers", {})
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=alert, headers=headers)
            resp.raise_for_status()
        logger.info("Webhook sent to %s (status %d)", url, resp.status_code)

    async def _send_slack(self, channel: NotificationChannel, alert: dict) -> None:
        if not HAS_HTTPX:
            logger.warning("httpx not installed — cannot send Slack message")
            return
        webhook_url = channel.config.get("webhook_url", "")
        severity = alert.get("severity", "info")
        color = {"critical": "#ef4444", "warning": "#f59e0b"}.get(severity, "#07b6d5")
        payload = {
            "attachments": [{
                "color": color,
                "title": f"[{severity.upper()}] {alert.get('rule_name', 'Alert')}",
                "text": alert.get("message", ""),
                "fields": [
                    {"title": "Entity", "value": alert.get("entity_id", ""), "short": True},
                    {"title": "Metric", "value": f"{alert.get('metric', '')} = {alert.get('value', '')}", "short": True},
                ],
                "footer": "DebugDuck Network Observatory",
            }],
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
        logger.info("Slack message sent (status %d)", resp.status_code)

    async def _send_email(self, channel: NotificationChannel, alert: dict) -> None:
        if not HAS_SMTP:
            logger.warning("smtplib not available — cannot send email")
            return
        cfg = channel.config
        severity = alert.get("severity", "info")
        subject = f"[{severity.upper()}] {alert.get('rule_name', 'Alert')} — {alert.get('entity_id', '')}"
        body = (
            f"Alert: {alert.get('rule_name', '')}\n"
            f"Entity: {alert.get('entity_id', '')}\n"
            f"Metric: {alert.get('metric', '')} = {alert.get('value', '')}\n"
            f"Threshold: {alert.get('condition', '')} {alert.get('threshold', '')}\n"
            f"Message: {alert.get('message', '')}\n"
        )
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = cfg.get("from_addr", "alerts@debugduck.local")
        to_addrs = cfg.get("to_addrs", [])
        msg["To"] = ", ".join(to_addrs)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._smtp_send, cfg, msg, to_addrs)
        logger.info("Email sent to %s", to_addrs)

    @staticmethod
    def _smtp_send(cfg: dict, msg: MIMEText, to_addrs: list[str]) -> None:
        host = cfg.get("smtp_host", "localhost")
        port = cfg.get("smtp_port", 587)
        username = cfg.get("username", "")
        password = cfg.get("password", "")
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.ehlo()
            if port == 587:
                server.starttls()
            if username:
                server.login(username, password)
            server.sendmail(msg["From"], to_addrs, msg.as_string())

    async def _send_pagerduty(self, channel: NotificationChannel, alert: dict) -> None:
        if not HAS_HTTPX:
            logger.warning("httpx not installed — cannot send PagerDuty event")
            return
        routing_key = channel.config.get("routing_key", "")
        severity_map = {"critical": "critical", "warning": "warning"}
        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": alert.get("message", "DebugDuck Alert"),
                "source": alert.get("entity_id", "debugduck"),
                "severity": severity_map.get(alert.get("severity", ""), "info"),
                "custom_details": {
                    "metric": alert.get("metric", ""),
                    "value": alert.get("value", ""),
                    "threshold": alert.get("threshold", ""),
                    "rule": alert.get("rule_name", ""),
                },
            },
            "dedup_key": alert.get("key", ""),
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
            )
            resp.raise_for_status()
        logger.info("PagerDuty event sent (dedup_key=%s)", alert.get("key"))

    async def _send_teams(self, channel: NotificationChannel, alert: dict) -> None:
        if not HAS_HTTPX:
            logger.warning("httpx not installed — cannot send Teams message")
            return
        webhook_url = channel.config.get("webhook_url", "")
        severity = alert.get("severity", "info")
        rule_name = alert.get("rule_name", "Alert")
        entity_id = alert.get("entity_id", "")
        metric = alert.get("metric", "")
        value = alert.get("value", "")
        message = alert.get("message", "")

        color = {"critical": "attention", "warning": "warning"}.get(severity, "accent")

        payload = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "medium",
                            "weight": "bolder",
                            "text": f"[{severity.upper()}] {rule_name}",
                            "color": color,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Entity", "value": entity_id},
                                {"title": "Metric", "value": f"{metric} = {value}"},
                                {"title": "Message", "value": message},
                            ],
                        },
                    ],
                },
            }],
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
        logger.info("Teams message sent (status %d)", resp.status_code)

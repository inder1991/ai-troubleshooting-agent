# Phase 1: Network Monitoring Foundation — Notifications, SNMP, Flow Protocols, Traceroute

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the four most critical network monitoring gaps: alert notifications that go somewhere, SNMP that works on modern links, flow protocols that modern equipment actually exports, and traceroute that works through firewalls.

**Architecture:** Four independent backend modules. Task 1 extends the existing alert engine with a pluggable notification dispatcher and channel registry. Task 2 adds SNMP WALK + 64-bit HC counters to the existing collector. Task 3 adds NetFlow v9 template-based parsing and IPFIX support to the existing flow receiver. Task 4 adds TCP/UDP fallback to the existing traceroute probe.

**Tech Stack:** Python 3.12, FastAPI, pysnmp-lextudio, icmplib, asyncio, Pydantic v2, httpx (for webhooks/Slack), struct (for binary parsing)

---

### Task 1: Notification Channel Models

**Files:**
- Modify: `backend/src/network/models.py`
- Test: `backend/tests/test_notification_models.py`

**What:** Add Pydantic models for notification channels (webhook, Slack, email, PagerDuty) and notification routing rules. These models will be used by the dispatcher in Task 2 and the API in Task 3.

**Step 1: Write the failing test**

Create `backend/tests/test_notification_models.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_notification_models.py -v`
Expected: FAIL with ImportError (models not defined yet)

**Step 3: Write the models**

Add to the end of `backend/src/network/models.py`:

```python
# ── Notification Channels ─────────────────────────────────────────────

class ChannelType(str, Enum):
    WEBHOOK = "webhook"
    SLACK = "slack"
    EMAIL = "email"
    PAGERDUTY = "pagerduty"


class NotificationChannel(BaseModel):
    """A configured notification destination."""
    id: str
    name: str
    channel_type: ChannelType
    config: dict = Field(default_factory=dict)
    enabled: bool = True


class NotificationRouting(BaseModel):
    """Routes alerts of given severities to specific channels."""
    id: str
    severity_filter: list[str] = Field(default_factory=lambda: ["critical", "warning"])
    channel_ids: list[str] = Field(..., min_length=1)
    enabled: bool = True
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_notification_models.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add backend/src/network/models.py backend/tests/test_notification_models.py
git commit -m "feat(notifications): add NotificationChannel and NotificationRouting models"
```

---

### Task 2: Notification Dispatcher

**Files:**
- Create: `backend/src/network/notification_dispatcher.py`
- Test: `backend/tests/test_notification_dispatcher.py`

**What:** A pluggable dispatcher that sends alerts to configured channels. Supports webhook (generic HTTP POST), Slack (incoming webhook), email (SMTP), and PagerDuty (Events API v2). Each sender is an async function. The dispatcher looks up routing rules to decide which channels get which alerts.

**Step 1: Write the failing test**

Create `backend/tests/test_notification_dispatcher.py`:

```python
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
    """Critical alert should route to both webhook and slack."""
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("critical"))
        wh.assert_called_once()
        sl.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_warning_hits_webhook_only(dispatcher):
    """Warning alert should route to webhook only."""
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("warning"))
        wh.assert_called_once()
        sl.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_info_hits_nothing(dispatcher):
    """Info alert with no matching routing should send nothing."""
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("info"))
        wh.assert_not_called()
        sl.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_skips_disabled_channel(dispatcher):
    """Disabled channel should be skipped."""
    dispatcher._channels["wh-1"].enabled = False
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("critical"))
        wh.assert_not_called()
        sl.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_skips_disabled_routing(dispatcher):
    """Disabled routing rule should be skipped."""
    dispatcher._routings[0].enabled = False  # rt-1 (critical -> wh+sl)
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        await dispatcher.dispatch(_make_alert("critical"))
        wh.assert_not_called()
        sl.assert_not_called()


@pytest.mark.asyncio
async def test_sender_error_does_not_propagate(dispatcher):
    """If one sender throws, dispatch still completes."""
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock,
                      side_effect=Exception("network error")) as wh, \
         patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as sl:
        # Should not raise
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_notification_dispatcher.py -v`
Expected: FAIL with ImportError

**Step 3: Write the implementation**

Create `backend/src/network/notification_dispatcher.py`:

```python
"""Notification dispatcher — routes alerts to configured channels."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .models import ChannelType, NotificationChannel, NotificationRouting

logger = logging.getLogger(__name__)

# Optional HTTP client — graceful fallback
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# Optional SMTP
try:
    import smtplib
    from email.mime.text import MIMEText
    HAS_SMTP = True
except ImportError:
    HAS_SMTP = False


class NotificationDispatcher:
    """Routes fired alerts to notification channels based on routing rules."""

    def __init__(self) -> None:
        self._channels: dict[str, NotificationChannel] = {}
        self._routings: list[NotificationRouting] = []

    # ── Channel management ─────────────────────────────────────────

    def add_channel(self, channel: NotificationChannel) -> None:
        self._channels[channel.id] = channel

    def remove_channel(self, channel_id: str) -> None:
        self._channels.pop(channel_id, None)

    def list_channels(self) -> list[dict]:
        return [ch.model_dump() for ch in self._channels.values()]

    # ── Routing management ─────────────────────────────────────────

    def add_routing(self, routing: NotificationRouting) -> None:
        self._routings.append(routing)

    def remove_routing(self, routing_id: str) -> None:
        self._routings = [r for r in self._routings if r.id != routing_id]

    def list_routings(self) -> list[dict]:
        return [r.model_dump() for r in self._routings]

    # ── Dispatch ───────────────────────────────────────────────────

    async def dispatch(self, alert: dict) -> None:
        """Send an alert to all matching channels based on routing rules."""
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
        """Dispatch multiple alerts."""
        for alert in alerts:
            await self.dispatch(alert)

    # ── Sender routing ─────────────────────────────────────────────

    async def _send(self, channel: NotificationChannel, alert: dict) -> None:
        """Route to the correct sender based on channel type."""
        try:
            if channel.channel_type == ChannelType.WEBHOOK:
                await self._send_webhook(channel, alert)
            elif channel.channel_type == ChannelType.SLACK:
                await self._send_slack(channel, alert)
            elif channel.channel_type == ChannelType.EMAIL:
                await self._send_email(channel, alert)
            elif channel.channel_type == ChannelType.PAGERDUTY:
                await self._send_pagerduty(channel, alert)
        except Exception:
            logger.exception("Failed to send alert to channel %s", channel.id)

    # ── Individual senders ─────────────────────────────────────────

    async def _send_webhook(self, channel: NotificationChannel, alert: dict) -> None:
        """Send alert as JSON POST to a webhook URL."""
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
        """Send alert as a Slack incoming webhook message."""
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
        """Send alert via SMTP email."""
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
        """Blocking SMTP send, run in executor."""
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
        """Send alert to PagerDuty Events API v2."""
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_notification_dispatcher.py -v`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add backend/src/network/notification_dispatcher.py backend/tests/test_notification_dispatcher.py
git commit -m "feat(notifications): add NotificationDispatcher with webhook/slack/email/pagerduty senders"
```

---

### Task 3: Wire Dispatcher into Alert Engine + API Endpoints

**Files:**
- Modify: `backend/src/network/alert_engine.py`
- Modify: `backend/src/network/monitor.py`
- Modify: `backend/src/api/monitor_endpoints.py`
- Test: `backend/tests/test_alert_notification_integration.py`

**What:** Connect the dispatcher to the alert engine so fired alerts trigger notifications. Add API endpoints for CRUD on channels and routing rules. Wire up on monitor startup.

**Step 1: Write the failing test**

Create `backend/tests/test_alert_notification_integration.py`:

```python
"""Integration test: alert fires -> dispatcher receives it."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.network.alert_engine import AlertEngine
from src.network.notification_dispatcher import NotificationDispatcher
from src.network.models import (
    NotificationChannel,
    NotificationRouting,
    ChannelType,
)


@pytest.fixture
def engine_with_dispatcher():
    metrics = MagicMock()
    # Return a metric value that triggers default-unreachable rule (packet_loss > 0.99)
    async def fake_query(device_id, metric, **kw):
        if metric == "packet_loss":
            return [{"value": 1.0, "time": "2026-03-06T00:00:00Z"}]
        return []
    metrics.query_device_metrics = fake_query
    metrics.write_alert_event = AsyncMock()

    engine = AlertEngine(metrics, load_defaults=True)
    dispatcher = NotificationDispatcher()
    dispatcher.add_channel(NotificationChannel(
        id="wh-test", name="Test", channel_type=ChannelType.WEBHOOK,
        config={"url": "https://example.com/hook"},
    ))
    dispatcher.add_routing(NotificationRouting(
        id="rt-test", severity_filter=["critical"], channel_ids=["wh-test"],
    ))
    engine.set_dispatcher(dispatcher)
    return engine, dispatcher


@pytest.mark.asyncio
async def test_fired_alert_triggers_dispatch(engine_with_dispatcher):
    engine, dispatcher = engine_with_dispatcher
    with patch.object(dispatcher, "_send_webhook", new_callable=AsyncMock) as mock_send:
        alerts = await engine.evaluate_all(["device-1"])
        assert len(alerts) > 0
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_no_dispatch_when_no_dispatcher():
    metrics = MagicMock()
    async def fake_query(device_id, metric, **kw):
        if metric == "packet_loss":
            return [{"value": 1.0, "time": "2026-03-06T00:00:00Z"}]
        return []
    metrics.query_device_metrics = fake_query
    metrics.write_alert_event = AsyncMock()

    engine = AlertEngine(metrics, load_defaults=True)
    # No dispatcher set — should not raise
    alerts = await engine.evaluate_all(["device-1"])
    assert len(alerts) > 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_alert_notification_integration.py -v`
Expected: FAIL with `AttributeError: 'AlertEngine' object has no attribute 'set_dispatcher'`

**Step 3: Modify AlertEngine**

In `backend/src/network/alert_engine.py`, add dispatcher support:

1. Add `self._dispatcher = None` in `__init__` (after line 85).

2. Add method after `__init__`:
```python
def set_dispatcher(self, dispatcher) -> None:
    """Attach a NotificationDispatcher to receive fired alerts."""
    self._dispatcher = dispatcher
```

3. In `evaluate_all` method (after the `self.metrics.write_alert_event(...)` call at ~line 207), add:
```python
        # Dispatch notifications for newly fired alerts
        if self._dispatcher and fired:
            try:
                await self._dispatcher.dispatch_batch(fired)
            except Exception:
                logger.exception("Notification dispatch failed")
```

**Step 4: Add notification API endpoints**

In `backend/src/api/monitor_endpoints.py`, add these endpoints after the existing alert endpoints:

```python
# ── Notification Channels ──────────────────────────────────────────

@monitor_router.get("/notifications/channels")
async def list_notification_channels():
    mon = _require_monitor()
    if not mon.alert_engine or not mon.alert_engine._dispatcher:
        return []
    return mon.alert_engine._dispatcher.list_channels()


@monitor_router.post("/notifications/channels")
async def create_notification_channel(body: dict):
    from src.network.models import NotificationChannel
    mon = _require_monitor()
    if not mon.alert_engine:
        raise HTTPException(503, "Alert engine not initialized")
    if not mon.alert_engine._dispatcher:
        from src.network.notification_dispatcher import NotificationDispatcher
        mon.alert_engine.set_dispatcher(NotificationDispatcher())
    channel = NotificationChannel(**body)
    mon.alert_engine._dispatcher.add_channel(channel)
    return {"status": "created", "id": channel.id}


@monitor_router.delete("/notifications/channels/{channel_id}")
async def delete_notification_channel(channel_id: str):
    mon = _require_monitor()
    if mon.alert_engine and mon.alert_engine._dispatcher:
        mon.alert_engine._dispatcher.remove_channel(channel_id)
    return {"status": "deleted"}


@monitor_router.get("/notifications/routings")
async def list_notification_routings():
    mon = _require_monitor()
    if not mon.alert_engine or not mon.alert_engine._dispatcher:
        return []
    return mon.alert_engine._dispatcher.list_routings()


@monitor_router.post("/notifications/routings")
async def create_notification_routing(body: dict):
    from src.network.models import NotificationRouting
    mon = _require_monitor()
    if not mon.alert_engine:
        raise HTTPException(503, "Alert engine not initialized")
    if not mon.alert_engine._dispatcher:
        from src.network.notification_dispatcher import NotificationDispatcher
        mon.alert_engine.set_dispatcher(NotificationDispatcher())
    routing = NotificationRouting(**body)
    mon.alert_engine._dispatcher.add_routing(routing)
    return {"status": "created", "id": routing.id}


@monitor_router.delete("/notifications/routings/{routing_id}")
async def delete_notification_routing(routing_id: str):
    mon = _require_monitor()
    if mon.alert_engine and mon.alert_engine._dispatcher:
        mon.alert_engine._dispatcher.remove_routing(routing_id)
    return {"status": "deleted"}
```

**Step 5: Wire dispatcher on monitor startup**

In `backend/src/network/monitor.py` `__init__`, after the `AlertEngine` creation (line ~38), add:

```python
        if self.alert_engine:
            from .notification_dispatcher import NotificationDispatcher
            self.alert_engine.set_dispatcher(NotificationDispatcher())
```

**Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_alert_notification_integration.py tests/test_notification_dispatcher.py tests/test_notification_models.py tests/test_alert_engine.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add backend/src/network/alert_engine.py backend/src/network/monitor.py backend/src/api/monitor_endpoints.py backend/tests/test_alert_notification_integration.py
git commit -m "feat(notifications): wire dispatcher into alert engine + add notification CRUD endpoints"
```

---

### Task 4: SNMP 64-bit HC Counters

**Files:**
- Modify: `backend/src/network/snmp_collector.py`
- Modify: `backend/tests/test_snmp_collector.py`

**What:** Add 64-bit high-capacity counter OIDs (`ifHCInOctets`, `ifHCOutOctets`) to fix wildly inaccurate bandwidth metrics on links > 100Mbps. 32-bit counters wrap at 4.29GB — on a 10Gbps link that's every ~3.4 seconds, making rate calculation impossible.

**Step 1: Write the failing test**

Add to `backend/tests/test_snmp_collector.py`:

```python
def test_64bit_counter_oids_exist():
    """HC counter OIDs must be defined for high-speed interfaces."""
    from src.network.snmp_collector import STANDARD_OIDS
    assert "ifHCInOctets" in STANDARD_OIDS
    assert "ifHCOutOctets" in STANDARD_OIDS


def test_compute_rates_64bit_no_wrap():
    """64-bit counters should not wrap for reasonable deltas."""
    from src.network.snmp_collector import SNMPCollector
    collector = SNMPCollector(metrics_store=None)
    device_id = "dev-hc"
    if_index = 1
    # First poll — baseline
    counters_1 = {
        "ifHCInOctets": 10_000_000_000,   # 10GB
        "ifHCOutOctets": 5_000_000_000,    # 5GB
        "ifInErrors": 0,
        "ifOutErrors": 0,
        "ifSpeed": 10_000_000_000,         # 10Gbps
    }
    result1 = collector._compute_rates(device_id, if_index, counters_1)
    assert result1 is None  # first poll

    # Second poll — 30s later with realistic increments
    import time
    collector._prev_counters[(device_id, if_index)] = (counters_1, time.time() - 30)
    counters_2 = {
        "ifHCInOctets": 10_375_000_000,    # +375MB in 30s = 100Mbps
        "ifHCOutOctets": 5_187_500_000,     # +187.5MB = 50Mbps
        "ifInErrors": 0,
        "ifOutErrors": 0,
        "ifSpeed": 10_000_000_000,
    }
    result2 = collector._compute_rates(device_id, if_index, counters_2)
    assert result2 is not None
    # 375_000_000 bytes * 8 / 30 = 100_000_000 bps = 100Mbps
    assert abs(result2["bps_in"] - 100_000_000) < 1_000_000  # within 1Mbps
    assert result2["utilization"] < 0.02  # 100Mbps / 10Gbps = 1%


def test_compute_rates_prefers_hc_counters():
    """When HC counters are present, they should be used over 32-bit counters."""
    from src.network.snmp_collector import SNMPCollector
    import time
    collector = SNMPCollector(metrics_store=None)
    device_id = "dev-hc-pref"
    if_index = 1
    # First poll with both 32-bit and 64-bit
    counters_1 = {
        "ifInOctets": 1_000_000,         # 32-bit (will wrap on high-speed)
        "ifOutOctets": 500_000,
        "ifHCInOctets": 50_000_000_000,  # 64-bit (won't wrap)
        "ifHCOutOctets": 25_000_000_000,
        "ifInErrors": 0,
        "ifOutErrors": 0,
        "ifSpeed": 10_000_000_000,
    }
    collector._prev_counters[(device_id, if_index)] = (counters_1, time.time() - 30)
    counters_2 = {
        "ifInOctets": 2_000_000,          # 32-bit delta: 1MB
        "ifOutOctets": 1_000_000,
        "ifHCInOctets": 50_100_000_000,   # 64-bit delta: 100MB
        "ifHCOutOctets": 25_050_000_000,
        "ifInErrors": 0,
        "ifOutErrors": 0,
        "ifSpeed": 10_000_000_000,
    }
    result = collector._compute_rates(device_id, if_index, counters_2)
    assert result is not None
    # Should use HC: 100_000_000 bytes * 8 / 30s ≈ 26.67 Mbps
    assert result["bps_in"] > 20_000_000  # HC value, not 32-bit's 266kbps
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_snmp_collector.py::test_64bit_counter_oids_exist -v`
Expected: FAIL with AssertionError

**Step 3: Modify SNMP collector**

In `backend/src/network/snmp_collector.py`:

1. Add HC counter OIDs to `STANDARD_OIDS` dict:
```python
    # 64-bit high-capacity counters (required for links > 100Mbps)
    "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",
    "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
```

2. Modify `_compute_rates` to prefer HC counters when available. Replace the in/out octet delta lines:

```python
        # Prefer 64-bit HC counters over 32-bit when available
        if "ifHCInOctets" in counters and "ifHCInOctets" in prev:
            delta_in = counters["ifHCInOctets"] - prev["ifHCInOctets"]
            delta_out = counters["ifHCOutOctets"] - prev["ifHCOutOctets"]
            wrap_threshold = 2 ** 64
        else:
            delta_in = counters.get("ifInOctets", 0) - prev.get("ifInOctets", 0)
            delta_out = counters.get("ifOutOctets", 0) - prev.get("ifOutOctets", 0)
            wrap_threshold = 2 ** 32

        if delta_in < 0:
            delta_in += wrap_threshold
        if delta_out < 0:
            delta_out += wrap_threshold
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_snmp_collector.py -v`
Expected: All tests PASS (existing + 3 new)

**Step 5: Commit**

```bash
git add backend/src/network/snmp_collector.py backend/tests/test_snmp_collector.py
git commit -m "feat(snmp): add 64-bit HC counter OIDs and prefer them over 32-bit"
```

---

### Task 5: SNMP Interface Table WALK

**Files:**
- Modify: `backend/src/network/snmp_collector.py`
- Modify: `backend/tests/test_snmp_collector.py`

**What:** The current `_snmp_get` fetches scalar OIDs only — it never walks the interface table, so `result["interfaces"]` is always `{}`. Add an SNMP BULKWALK that enumerates all interfaces with their counters (including HC), descriptions, speeds, and operational status. This is what makes per-interface bandwidth monitoring actually work.

**Step 1: Write the failing test**

Add to `backend/tests/test_snmp_collector.py`:

```python
@pytest.mark.asyncio
async def test_snmp_get_populates_interfaces(monkeypatch):
    """_snmp_get should return populated interfaces dict via SNMP walk."""
    from src.network.snmp_collector import SNMPCollector, SNMPDeviceConfig

    # Mock the pysnmp bulk_cmd to return fake interface data
    async def mock_walk_interfaces(self, cfg):
        return {
            1: {
                "ifDescr": "GigabitEthernet0/0",
                "ifOperStatus": 1,
                "ifSpeed": 1_000_000_000,
                "ifInOctets": 1000,
                "ifOutOctets": 2000,
                "ifHCInOctets": 100000,
                "ifHCOutOctets": 200000,
                "ifInErrors": 0,
                "ifOutErrors": 0,
            },
            2: {
                "ifDescr": "GigabitEthernet0/1",
                "ifOperStatus": 1,
                "ifSpeed": 10_000_000_000,
                "ifInOctets": 5000,
                "ifOutOctets": 6000,
                "ifHCInOctets": 500000,
                "ifHCOutOctets": 600000,
                "ifInErrors": 1,
                "ifOutErrors": 0,
            },
        }

    collector = SNMPCollector(metrics_store=None)
    monkeypatch.setattr(collector, "_walk_interfaces", mock_walk_interfaces)

    cfg = SNMPDeviceConfig(device_id="dev-walk", ip="10.0.0.1")
    result = await collector._snmp_get(cfg)
    assert len(result["interfaces"]) == 2
    assert result["interfaces"][1]["ifDescr"] == "GigabitEthernet0/0"
    assert result["interfaces"][2]["ifHCInOctets"] == 500000
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_snmp_collector.py::test_snmp_get_populates_interfaces -v`
Expected: FAIL with `AttributeError: '_walk_interfaces'`

**Step 3: Add interface walk method**

In `backend/src/network/snmp_collector.py`, add method to `SNMPCollector`:

```python
    async def _walk_interfaces(self, cfg: SNMPDeviceConfig) -> dict[int, dict]:
        """SNMP BULKWALK of interface table — returns {if_index: {counters}}."""
        try:
            from pysnmp.hlapi.v3arch.asyncio import (
                bulk_cmd, SnmpEngine, CommunityData, UdpTransportTarget,
                ContextData, ObjectType, ObjectIdentity, UsmUserData,
            )
        except ImportError:
            logger.error("pysnmp-lextudio not installed")
            return {}

        engine = SnmpEngine()
        target = UdpTransportTarget((cfg.ip, cfg.port), timeout=5, retries=1)
        if cfg.version == "v3":
            auth = UsmUserData(cfg.v3_user, cfg.v3_auth_key, cfg.v3_priv_key)
        else:
            auth = CommunityData(cfg.community, mpModel=1)

        # OIDs to walk (interface table columns)
        walk_oids = {
            "ifDescr": "1.3.6.1.2.1.2.2.1.2",
            "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
            "ifSpeed": "1.3.6.1.2.1.2.2.1.5",
            "ifInOctets": "1.3.6.1.2.1.2.2.1.10",
            "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
            "ifInErrors": "1.3.6.1.2.1.2.2.1.14",
            "ifOutErrors": "1.3.6.1.2.1.2.2.1.20",
            "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",
            "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
        }

        interfaces: dict[int, dict] = {}

        for name, base_oid in walk_oids.items():
            base = ObjectIdentity(base_oid)
            marker = base_oid

            while True:
                try:
                    err_indication, err_status, err_index, var_binds = await bulk_cmd(
                        engine, auth, target, ContextData(),
                        0, 25,  # non-repeaters=0, max-repetitions=25
                        ObjectType(ObjectIdentity(marker)),
                    )
                except Exception:
                    break

                if err_indication or err_status:
                    break

                for var_bind_row in var_binds:
                    for oid, val in var_bind_row:
                        oid_str = str(oid)
                        if not oid_str.startswith(base_oid):
                            break
                        # Extract interface index from OID suffix
                        if_index = int(oid_str.split(".")[-1])
                        if if_index not in interfaces:
                            interfaces[if_index] = {}
                        interfaces[if_index][name] = int(val) if name != "ifDescr" else str(val)
                        marker = oid_str
                    else:
                        continue
                    break  # out-of-subtree
                else:
                    continue
                break

        return interfaces
```

Then modify `_snmp_get` to call `_walk_interfaces`:

After the scalar OID fetching (CPU/mem), add before the return:

```python
        # Walk interface table for per-interface counters
        result["interfaces"] = await self._walk_interfaces(cfg)
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_snmp_collector.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/network/snmp_collector.py backend/tests/test_snmp_collector.py
git commit -m "feat(snmp): add SNMP BULKWALK for interface table enumeration"
```

---

### Task 6: NetFlow v9 Template-Based Parser

**Files:**
- Modify: `backend/src/network/flow_receiver.py`
- Modify: `backend/tests/test_flow_receiver.py`

**What:** Add NetFlow v9 template-based parsing. v9 uses a template-data paradigm: the exporter first sends Template FlowSets defining field layouts, then sends Data FlowSets referencing those templates. Our parser must cache templates per exporter and decode data records using the cached template. This is the format used by Cisco IOS, IOS-XE, and NX-OS.

**Step 1: Write the failing test**

Add to `backend/tests/test_flow_receiver.py`:

```python
def _build_v9_template_packet(template_id=256):
    """Build a NetFlow v9 packet containing a template flowset."""
    import struct, socket
    # v9 header: version(2) count(2) uptime(4) unix_secs(4) sequence(4) source_id(4)
    header = struct.pack("!HHIIII", 9, 1, 1000, 1709740800, 1, 100)
    # Template FlowSet: flowset_id=0, length, template_id, field_count
    fields = [
        (8, 4),   # IN_BYTES (field 8, 4 bytes)
        (12, 4),  # IN_PKTS (field 12, 4 bytes)
        (7, 2),   # L4_SRC_PORT (field 7, 2 bytes)
        (11, 2),  # L4_DST_PORT (field 11, 2 bytes)
        (4, 1),   # PROTOCOL (field 4, 1 byte)
        (8, 4),   # SRC_ADDR — actually field type 8 is IN_BYTES, let's use correct ones
    ]
    # Correct NetFlow v9 field types:
    # 1=IN_BYTES(4), 2=IN_PKTS(4), 7=L4_SRC_PORT(2), 11=L4_DST_PORT(2),
    # 4=PROTOCOL(1), 8=IPV4_SRC_ADDR(4), 12=IPV4_DST_ADDR(4)
    fields = [
        (1, 4),   # IN_BYTES
        (2, 4),   # IN_PKTS
        (7, 2),   # L4_SRC_PORT
        (11, 2),  # L4_DST_PORT
        (4, 1),   # PROTOCOL
        (8, 4),   # IPV4_SRC_ADDR
        (12, 4),  # IPV4_DST_ADDR
    ]
    field_count = len(fields)
    # Template record: template_id(2) + field_count(2) + fields(4 each)
    template_record = struct.pack("!HH", template_id, field_count)
    for ftype, flen in fields:
        template_record += struct.pack("!HH", ftype, flen)
    # Template FlowSet: id=0, length = 4 (header) + len(template_record)
    flowset_length = 4 + len(template_record)
    # Pad to 4-byte boundary
    pad = (4 - flowset_length % 4) % 4
    flowset = struct.pack("!HH", 0, flowset_length + pad) + template_record + b"\x00" * pad
    return header + flowset


def _build_v9_data_packet(template_id=256):
    """Build a NetFlow v9 data packet referencing a template."""
    import struct, socket
    header = struct.pack("!HHIIII", 9, 1, 2000, 1709740830, 2, 100)
    # Data record matching the template above:
    # IN_BYTES(4) + IN_PKTS(4) + SRC_PORT(2) + DST_PORT(2) + PROTO(1) + SRC_IP(4) + DST_IP(4)
    src_ip = socket.inet_aton("10.0.0.1")
    dst_ip = socket.inet_aton("10.0.0.2")
    data_record = struct.pack("!IIHHB", 1500, 10, 12345, 443, 6) + src_ip + dst_ip
    record_size = len(data_record)  # 21 bytes
    flowset_length = 4 + record_size
    pad = (4 - flowset_length % 4) % 4
    flowset = struct.pack("!HH", template_id, flowset_length + pad) + data_record + b"\x00" * pad
    return header + flowset


def test_parse_v9_template_then_data():
    """Parser should cache v9 template and decode subsequent data records."""
    from src.network.flow_receiver import FlowParser
    parser = FlowParser()

    # First: send template packet
    template_pkt = _build_v9_template_packet(template_id=256)
    records = parser.detect_and_parse(template_pkt, "10.0.0.254")
    assert records == []  # Template packets produce no flow records

    # Second: send data packet referencing the template
    data_pkt = _build_v9_data_packet(template_id=256)
    records = parser.detect_and_parse(data_pkt, "10.0.0.254")
    assert len(records) == 1
    assert records[0].src_ip == "10.0.0.1"
    assert records[0].dst_ip == "10.0.0.2"
    assert records[0].src_port == 12345
    assert records[0].dst_port == 443
    assert records[0].protocol == 6
    assert records[0].bytes == 1500
    assert records[0].packets == 10


def test_parse_v9_data_without_template():
    """Data packet with unknown template should be skipped gracefully."""
    from src.network.flow_receiver import FlowParser
    parser = FlowParser()
    data_pkt = _build_v9_data_packet(template_id=999)
    records = parser.detect_and_parse(data_pkt, "10.0.0.254")
    assert records == []


def test_parse_v9_multiple_exporters():
    """Templates are cached per exporter IP."""
    from src.network.flow_receiver import FlowParser
    parser = FlowParser()

    # Exporter A sends template
    tpl = _build_v9_template_packet(template_id=256)
    parser.detect_and_parse(tpl, "10.0.0.1")

    # Exporter B tries to send data with same template_id — should fail (no template cached for B)
    data = _build_v9_data_packet(template_id=256)
    records = parser.detect_and_parse(data, "10.0.0.2")
    assert records == []

    # Exporter A sends data — should work
    records = parser.detect_and_parse(data, "10.0.0.1")
    assert len(records) == 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_flow_receiver.py::test_parse_v9_template_then_data -v`
Expected: FAIL (v9 not handled, returns `[]`)

**Step 3: Implement v9 parser**

In `backend/src/network/flow_receiver.py`, modify `FlowParser`:

1. Add to `__init__`:
```python
    def __init__(self):
        # Template cache: {(exporter_ip, source_id): {template_id: [(field_type, field_len), ...]}}
        self._v9_templates: dict[tuple[str, int], dict[int, list[tuple[int, int]]]] = {}
```

2. Add NetFlow v9 field type constants:
```python
# NetFlow v9 field type IDs (RFC 3954)
_V9_FIELD_TYPES = {
    1: "IN_BYTES",
    2: "IN_PKTS",
    4: "PROTOCOL",
    7: "L4_SRC_PORT",
    8: "IPV4_SRC_ADDR",
    10: "INPUT_SNMP",
    11: "L4_DST_PORT",
    12: "IPV4_DST_ADDR",
    14: "OUTPUT_SNMP",
    6: "TCP_FLAGS",
    5: "TOS",
    16: "SRC_AS",
    17: "DST_AS",
    15: "IPV4_NEXT_HOP",
    21: "LAST_SWITCHED",
    22: "FIRST_SWITCHED",
}
```

3. Add `parse_v9` method:
```python
    def parse_v9(self, data: bytes, exporter_ip: str) -> list[FlowRecord]:
        """Parse NetFlow v9 packet — handles both template and data flowsets."""
        if len(data) < 20:
            return []
        version, count, sys_uptime, unix_secs, sequence, source_id = struct.unpack_from("!HHIIII", data)
        if version != 9:
            return []

        base_time = datetime.fromtimestamp(unix_secs, tz=timezone.utc)
        cache_key = (exporter_ip, source_id)
        offset = 20  # past the header
        records = []

        while offset < len(data) - 3:
            flowset_id, flowset_length = struct.unpack_from("!HH", data, offset)
            if flowset_length < 4:
                break
            flowset_end = offset + flowset_length

            if flowset_id == 0:
                # Template FlowSet
                self._parse_v9_templates(data, offset + 4, flowset_end, cache_key)
            elif flowset_id == 1:
                # Options Template FlowSet — skip for now
                pass
            elif flowset_id >= 256:
                # Data FlowSet
                new_records = self._parse_v9_data(data, offset + 4, flowset_end,
                                                   flowset_id, cache_key, base_time, exporter_ip)
                records.extend(new_records)

            offset = flowset_end
            # Align to 4-byte boundary
            offset += (4 - offset % 4) % 4

        return records

    def _parse_v9_templates(self, data: bytes, start: int, end: int,
                            cache_key: tuple[str, int]) -> None:
        """Parse and cache template records from a template flowset."""
        offset = start
        if cache_key not in self._v9_templates:
            self._v9_templates[cache_key] = {}

        while offset < end - 3:
            template_id, field_count = struct.unpack_from("!HH", data, offset)
            offset += 4
            fields = []
            for _ in range(field_count):
                if offset + 4 > end:
                    break
                ftype, flen = struct.unpack_from("!HH", data, offset)
                fields.append((ftype, flen))
                offset += 4
            self._v9_templates[cache_key][template_id] = fields

    def _parse_v9_data(self, data: bytes, start: int, end: int,
                       template_id: int, cache_key: tuple[str, int],
                       base_time: datetime, exporter_ip: str) -> list[FlowRecord]:
        """Parse data records using a cached template."""
        templates = self._v9_templates.get(cache_key, {})
        template = templates.get(template_id)
        if not template:
            logger.debug("No template %d for exporter %s — skipping data flowset", template_id, cache_key[0])
            return []

        record_size = sum(flen for _, flen in template)
        if record_size == 0:
            return []

        records = []
        offset = start

        while offset + record_size <= end:
            field_values: dict[int, Any] = {}
            pos = offset
            for ftype, flen in template:
                if pos + flen > end:
                    break
                raw = data[pos:pos + flen]
                if flen == 1:
                    field_values[ftype] = raw[0]
                elif flen == 2:
                    field_values[ftype] = struct.unpack_from("!H", raw)[0]
                elif flen == 4:
                    field_values[ftype] = struct.unpack_from("!I", raw)[0]
                elif flen == 8:
                    field_values[ftype] = struct.unpack_from("!Q", raw)[0]
                else:
                    field_values[ftype] = raw
                pos += flen

            # Extract known fields
            src_ip_int = field_values.get(8, 0)  # IPV4_SRC_ADDR
            dst_ip_int = field_values.get(12, 0)  # IPV4_DST_ADDR
            src_ip = socket.inet_ntoa(struct.pack("!I", src_ip_int)) if isinstance(src_ip_int, int) else "0.0.0.0"
            dst_ip = socket.inet_ntoa(struct.pack("!I", dst_ip_int)) if isinstance(dst_ip_int, int) else "0.0.0.0"

            records.append(FlowRecord(
                src_ip=src_ip,
                dst_ip=dst_ip,
                src_port=field_values.get(7, 0),
                dst_port=field_values.get(11, 0),
                protocol=field_values.get(4, 0),
                bytes=field_values.get(1, 0),
                packets=field_values.get(2, 0),
                start_time=base_time,
                end_time=base_time,
                tcp_flags=field_values.get(6, 0),
                tos=field_values.get(5, 0),
                input_snmp=field_values.get(10, 0),
                output_snmp=field_values.get(14, 0),
                src_as=field_values.get(16, 0),
                dst_as=field_values.get(17, 0),
                exporter_ip=exporter_ip,
            ))
            offset += record_size

        return records
```

4. Modify `detect_and_parse` to route v9:
```python
    def detect_and_parse(self, data: bytes, exporter_ip: str) -> list[FlowRecord]:
        if len(data) < 4:
            return []
        version = struct.unpack_from("!H", data)[0]
        if version == 5:
            return self.parse_v5(data, exporter_ip)
        elif version == 9:
            return self.parse_v9(data, exporter_ip)
        elif version == 10:
            return self.parse_ipfix(data, exporter_ip)
        else:
            logger.debug("Unsupported flow version: %d", version)
            return []
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_flow_receiver.py -v`
Expected: All tests PASS (existing v5 tests + 3 new v9 tests). The `parse_ipfix` call will need a stub — add an empty method:

```python
    def parse_ipfix(self, data: bytes, exporter_ip: str) -> list[FlowRecord]:
        """Parse IPFIX (NetFlow v10) packet. Uses same template logic as v9."""
        # IPFIX is structurally similar to v9 but with a different header
        # Header: version(2)=10, length(2), export_time(4), sequence(4), domain_id(4)
        if len(data) < 16:
            return []
        version, length, export_time, sequence, domain_id = struct.unpack_from("!HHIII", data)
        if version != 10:
            return []

        base_time = datetime.fromtimestamp(export_time, tz=timezone.utc)
        cache_key = (exporter_ip, domain_id)
        offset = 16
        records = []

        while offset < len(data) - 3:
            if offset + 4 > len(data):
                break
            set_id, set_length = struct.unpack_from("!HH", data, offset)
            if set_length < 4:
                break
            set_end = offset + set_length

            if set_id == 2:
                # Template Set
                self._parse_v9_templates(data, offset + 4, set_end, cache_key)
            elif set_id == 3:
                # Options Template Set — skip
                pass
            elif set_id >= 256:
                # Data Set
                new_records = self._parse_v9_data(data, offset + 4, set_end,
                                                   set_id, cache_key, base_time, exporter_ip)
                records.extend(new_records)

            offset = set_end

        return records
```

**Step 5: Commit**

```bash
git add backend/src/network/flow_receiver.py backend/tests/test_flow_receiver.py
git commit -m "feat(flows): add NetFlow v9 template-based parser and IPFIX support"
```

---

### Task 7: IPFIX Parser Tests

**Files:**
- Modify: `backend/tests/test_flow_receiver.py`

**What:** Add tests for IPFIX (version 10) parsing since the parser was added in Task 6 but not tested.

**Step 1: Write the tests**

Add to `backend/tests/test_flow_receiver.py`:

```python
def _build_ipfix_template_packet(template_id=256):
    """Build an IPFIX packet containing a template set."""
    import struct, socket
    # IPFIX header: version(2)=10, length(2), export_time(4), sequence(4), domain_id(4)
    # Fields: same as v9 test template
    fields = [
        (1, 4),   # IN_BYTES
        (2, 4),   # IN_PKTS
        (7, 2),   # L4_SRC_PORT
        (11, 2),  # L4_DST_PORT
        (4, 1),   # PROTOCOL
        (8, 4),   # IPV4_SRC_ADDR
        (12, 4),  # IPV4_DST_ADDR
    ]
    field_count = len(fields)
    template_record = struct.pack("!HH", template_id, field_count)
    for ftype, flen in fields:
        template_record += struct.pack("!HH", ftype, flen)
    # Template Set: set_id=2, length
    set_length = 4 + len(template_record)
    pad = (4 - set_length % 4) % 4
    template_set = struct.pack("!HH", 2, set_length + pad) + template_record + b"\x00" * pad

    total_length = 16 + len(template_set)
    header = struct.pack("!HHIII", 10, total_length, 1709740800, 1, 200)
    return header + template_set


def _build_ipfix_data_packet(template_id=256):
    """Build an IPFIX data packet referencing a template."""
    import struct, socket
    src_ip = socket.inet_aton("192.168.1.1")
    dst_ip = socket.inet_aton("192.168.1.2")
    data_record = struct.pack("!IIHHB", 2500, 15, 54321, 80, 6) + src_ip + dst_ip
    set_length = 4 + len(data_record)
    pad = (4 - set_length % 4) % 4
    data_set = struct.pack("!HH", template_id, set_length + pad) + data_record + b"\x00" * pad

    total_length = 16 + len(data_set)
    header = struct.pack("!HHIII", 10, total_length, 1709740830, 2, 200)
    return header + data_set


def test_parse_ipfix_template_then_data():
    """IPFIX parser should cache templates and decode data records."""
    from src.network.flow_receiver import FlowParser
    parser = FlowParser()

    tpl = _build_ipfix_template_packet(template_id=300)
    records = parser.detect_and_parse(tpl, "10.0.0.100")
    assert records == []

    data = _build_ipfix_data_packet(template_id=300)
    records = parser.detect_and_parse(data, "10.0.0.100")
    assert len(records) == 1
    assert records[0].src_ip == "192.168.1.1"
    assert records[0].dst_ip == "192.168.1.2"
    assert records[0].bytes == 2500
    assert records[0].protocol == 6
```

**Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_flow_receiver.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add backend/tests/test_flow_receiver.py
git commit -m "test(flows): add IPFIX parser tests"
```

---

### Task 8: TCP/UDP Traceroute Fallback

**Files:**
- Modify: `backend/src/agents/network/traceroute_probe.py`
- Modify: `backend/tests/test_traceroute_hop.py`

**What:** Many enterprise firewalls block ICMP. Our traceroute probe currently uses ICMP-only (`icmplib.traceroute`), which silently fails against ICMP-blocking firewalls. Add TCP SYN and UDP fallback using Python's `socket` module. Try ICMP first, fall back to TCP if all hops timeout, then UDP.

**Step 1: Write the failing test**

Add to `backend/tests/test_traceroute_hop.py`:

```python
class TestTracerouteProtocolFallback:
    """Tests for TCP/UDP traceroute fallback."""

    def test_tcp_traceroute_called_on_icmp_failure(self, monkeypatch):
        """When ICMP returns all-timeout hops, should try TCP."""
        from src.agents.network import traceroute_probe

        # Make ICMP return only timeout hops
        class FakeHop:
            address = None
            avg_rtt = 0
            is_alive = False

        def mock_icmp_traceroute(dst, max_hops=30, timeout=2):
            return [FakeHop() for _ in range(5)]

        monkeypatch.setattr(traceroute_probe, "icmp_traceroute", mock_icmp_traceroute)
        monkeypatch.setattr(traceroute_probe, "HAS_ICMPLIB", True)

        # Mock TCP traceroute to return one real hop
        def mock_tcp_trace(dst_ip, port=443, max_hops=30, timeout=2):
            return [{"hop": 1, "ip": "10.0.0.1", "rtt_ms": 5.0, "status": "responded"}]

        monkeypatch.setattr(traceroute_probe, "_tcp_traceroute", mock_tcp_trace)

        state = {"dst_ip": "8.8.8.8"}
        result = traceroute_probe.traceroute_probe(state)
        assert result["trace_method"] in ("TCP", "tcp")
        assert len(result["trace_hops"]) >= 1


    def test_trace_method_reflects_protocol_used(self, monkeypatch):
        """trace_method field should show which protocol succeeded."""
        from src.agents.network import traceroute_probe

        class FakeHop:
            address = "10.0.0.1"
            avg_rtt = 5.0
            is_alive = True

        def mock_icmp(dst, max_hops=30, timeout=2):
            return [FakeHop()]

        monkeypatch.setattr(traceroute_probe, "icmp_traceroute", mock_icmp)
        monkeypatch.setattr(traceroute_probe, "HAS_ICMPLIB", True)

        state = {"dst_ip": "8.8.8.8"}
        result = traceroute_probe.traceroute_probe(state)
        assert result["trace_method"] == "ICMP"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_traceroute_hop.py::TestTracerouteProtocolFallback -v`
Expected: FAIL with AttributeError `_tcp_traceroute`

**Step 3: Implement TCP/UDP traceroute and fallback logic**

In `backend/src/agents/network/traceroute_probe.py`:

1. Add imports:
```python
import socket
import time as time_mod
```

2. Add TCP traceroute function:
```python
def _tcp_traceroute(dst_ip: str, port: int = 443, max_hops: int = 30, timeout: float = 2.0) -> list[dict]:
    """TCP SYN traceroute — works through ICMP-blocking firewalls."""
    hops = []
    for ttl in range(1, max_hops + 1):
        try:
            # Create raw socket for receiving ICMP TTL exceeded
            recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            recv_sock.settimeout(timeout)

            # Create TCP socket with specific TTL
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
            send_sock.settimeout(timeout)

            start = time_mod.monotonic()
            try:
                send_sock.connect_ex((dst_ip, port))
                # Try to receive ICMP time-exceeded from intermediate router
                data, addr = recv_sock.recvfrom(512)
                rtt = (time_mod.monotonic() - start) * 1000
                hops.append({
                    "hop": ttl, "ip": addr[0], "rtt_ms": round(rtt, 2), "status": "responded",
                })
                if addr[0] == dst_ip:
                    break
            except socket.timeout:
                hops.append({"hop": ttl, "ip": None, "rtt_ms": 0, "status": "timeout"})
            finally:
                send_sock.close()
                recv_sock.close()
        except OSError:
            hops.append({"hop": ttl, "ip": None, "rtt_ms": 0, "status": "timeout"})
    return hops


def _udp_traceroute(dst_ip: str, port: int = 33434, max_hops: int = 30, timeout: float = 2.0) -> list[dict]:
    """UDP traceroute — fallback when both ICMP and TCP fail."""
    hops = []
    for ttl in range(1, max_hops + 1):
        try:
            recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            recv_sock.settimeout(timeout)

            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)

            start = time_mod.monotonic()
            send_sock.sendto(b"", (dst_ip, port + ttl))
            try:
                data, addr = recv_sock.recvfrom(512)
                rtt = (time_mod.monotonic() - start) * 1000
                hops.append({
                    "hop": ttl, "ip": addr[0], "rtt_ms": round(rtt, 2), "status": "responded",
                })
                if addr[0] == dst_ip:
                    break
            except socket.timeout:
                hops.append({"hop": ttl, "ip": None, "rtt_ms": 0, "status": "timeout"})
            finally:
                send_sock.close()
                recv_sock.close()
        except OSError:
            hops.append({"hop": ttl, "ip": None, "rtt_ms": 0, "status": "timeout"})
    return hops
```

3. Modify the main `traceroute_probe` function to add fallback logic. After the ICMP traceroute call and hop building, add:

```python
        # Check if ICMP got any real responses
        responded_hops = [h for h in hops if h.get("status") == "responded" or (h.get("ip") and h["ip"] != "")]
        trace_method = "ICMP"

        if not responded_hops:
            # ICMP failed — try TCP
            tcp_hops = _tcp_traceroute(dst_ip)
            tcp_responded = [h for h in tcp_hops if h.get("ip")]
            if tcp_responded:
                hops = []
                for h in tcp_hops:
                    hops.append({
                        "id": f"{trace_id}-{h['hop']}",
                        "trace_id": trace_id,
                        "hop_number": h["hop"],
                        "ip": h["ip"] or "",
                        "rtt_ms": h["rtt_ms"],
                        "status": h["status"],
                    })
                trace_method = "TCP"
            else:
                # TCP also failed — try UDP
                udp_hops = _udp_traceroute(dst_ip)
                udp_responded = [h for h in udp_hops if h.get("ip")]
                if udp_responded:
                    hops = []
                    for h in udp_hops:
                        hops.append({
                            "id": f"{trace_id}-{h['hop']}",
                            "trace_id": trace_id,
                            "hop_number": h["hop"],
                            "ip": h["ip"] or "",
                            "rtt_ms": h["rtt_ms"],
                            "status": h["status"],
                        })
                    trace_method = "UDP"
```

4. Set `trace_method` in the return dict:
```python
        return {
            ...
            "trace_method": trace_method,
            ...
        }
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_traceroute_hop.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/network/traceroute_probe.py backend/tests/test_traceroute_hop.py
git commit -m "feat(traceroute): add TCP/UDP fallback for ICMP-blocking firewalls"
```

---

### Task 9: Add httpx Dependency

**Files:**
- Modify: `backend/requirements.txt`

**What:** The notification dispatcher uses `httpx` for webhook, Slack, and PagerDuty HTTP calls. Also add `icmplib` which was used but never declared.

**Step 1: Add dependencies**

Add to `backend/requirements.txt`:

```
httpx>=0.27.0
icmplib>=3.0.4
```

**Step 2: Install**

Run: `cd backend && pip install -r requirements.txt`
Expected: Both packages install successfully

**Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add httpx and icmplib to requirements"
```

---

### Task 10: Final Verification

**Files:** All modified files

**Step 1: Run all affected tests**

```bash
cd backend && python -m pytest tests/test_notification_models.py tests/test_notification_dispatcher.py tests/test_alert_notification_integration.py tests/test_snmp_collector.py tests/test_flow_receiver.py tests/test_traceroute_hop.py tests/test_alert_engine.py -v
```
Expected: All tests PASS

**Step 2: TypeScript check (frontend unchanged)**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 3: Verify no import errors**

```bash
cd backend && python -c "
from src.network.notification_dispatcher import NotificationDispatcher
from src.network.models import NotificationChannel, NotificationRouting, ChannelType
from src.network.alert_engine import AlertEngine
from src.network.snmp_collector import SNMPCollector, STANDARD_OIDS
from src.network.flow_receiver import FlowParser, FlowReceiver
from src.agents.network.traceroute_probe import traceroute_probe, _tcp_traceroute, _udp_traceroute
print('All imports OK')
print('HC OIDs present:', 'ifHCInOctets' in STANDARD_OIDS and 'ifHCOutOctets' in STANDARD_OIDS)
print('FlowParser has v9:', hasattr(FlowParser, 'parse_v9'))
print('FlowParser has IPFIX:', hasattr(FlowParser, 'parse_ipfix'))
"
```
Expected: All imports OK, HC OIDs present: True, FlowParser has v9: True, FlowParser has IPFIX: True

**Step 4: Commit if any cleanup needed**

---

## Execution Order

```
Task 1:  Notification models              (models.py — new types)
Task 2:  Notification dispatcher           (new file — senders)
Task 3:  Wire dispatcher + API endpoints   (alert_engine, monitor, endpoints)
Task 4:  SNMP 64-bit HC counters           (snmp_collector.py)
Task 5:  SNMP interface table WALK         (snmp_collector.py)
Task 6:  NetFlow v9 + IPFIX parser         (flow_receiver.py)
Task 7:  IPFIX parser tests                (test only)
Task 8:  TCP/UDP traceroute fallback       (traceroute_probe.py)
Task 9:  Add httpx + icmplib deps          (requirements.txt)
Task 10: Final verification                (all files)
```

Dependencies:
- Tasks 1 → 2 → 3 (sequential — models, then dispatcher, then wiring)
- Tasks 4 → 5 (sequential — HC counters first, then WALK uses them)
- Tasks 6 → 7 (sequential — parser first, then additional tests)
- Task 8 is independent
- Task 9 should run before Task 3 (httpx needed) but can run anytime

Recommended: 1 → 2 → 9 → 3 → (4+5 parallel with 6+7) → 8 → 10

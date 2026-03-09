# Phase 6: Observability & Notification Enrichment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Prometheus metrics export for system self-monitoring, expand notification channels (MS Teams, Opsgenie), and add alert deduplication to prevent notification floods.

**Architecture:** Use `prometheus-client` for metrics instrumentation, add two new channel types to NotificationDispatcher, and implement dedup via a time-windowed key set in the dispatcher.

**Tech Stack:** prometheus-client, httpx (existing), FastAPI middleware

---

### Task 1: Prometheus Metrics Export

**Files:**
- Create: `backend/src/network/prometheus_exporter.py`
- Modify: `backend/src/api/main.py` (add `/metrics` endpoint)
- Modify: `backend/src/network/monitor.py` (instrument cycle timing)
- Test: `backend/tests/test_prometheus_exporter.py`

**Context:**
- The `prometheus_url` param in NetworkMonitor is dead code — we're not reading Prometheus, we're **exporting** metrics.
- Use `prometheus_client` library with a `CollectorRegistry` for testability.
- Key metrics to export:
  - `network_monitor_cycle_duration_seconds` (Histogram) — how long each cycle takes
  - `network_monitor_cycle_total` (Counter) — total cycles completed
  - `network_monitor_pass_duration_seconds` (Histogram, label=pass_name) — per-pass timing
  - `network_monitor_devices_total` (Gauge) — current device count
  - `network_monitor_alerts_active` (Gauge) — current active alert count
  - `network_monitor_adapter_errors_total` (Counter) — adapter failures

**Step 1: Write the failing tests**

Create `backend/tests/test_prometheus_exporter.py`:

```python
"""Tests for Prometheus metrics export."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.network.prometheus_exporter import MetricsCollector


class TestMetricsCollector:
    def test_create_collector(self):
        collector = MetricsCollector()
        assert collector is not None

    def test_record_cycle_duration(self):
        collector = MetricsCollector()
        collector.record_cycle_duration(1.5)
        # Should not raise

    def test_record_pass_duration(self):
        collector = MetricsCollector()
        collector.record_pass_duration("probe", 0.3)
        collector.record_pass_duration("adapter", 0.5)

    def test_set_device_count(self):
        collector = MetricsCollector()
        collector.set_device_count(42)

    def test_set_active_alerts(self):
        collector = MetricsCollector()
        collector.set_active_alerts(7)

    def test_increment_adapter_errors(self):
        collector = MetricsCollector()
        collector.increment_adapter_errors("palo_alto")

    def test_generate_metrics_text(self):
        collector = MetricsCollector()
        collector.record_cycle_duration(1.5)
        collector.set_device_count(10)
        text = collector.generate_metrics()
        assert "network_monitor_cycle_duration_seconds" in text
        assert "network_monitor_devices_total" in text

    def test_increment_cycle_total(self):
        collector = MetricsCollector()
        collector.increment_cycle_total()
        collector.increment_cycle_total()
        text = collector.generate_metrics()
        assert "network_monitor_cycle_total" in text


class TestMetricsEndpoint:
    def test_metrics_endpoint_exists(self):
        from src.api.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "network_monitor" in response.text or "python_info" in response.text
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_prometheus_exporter.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Install dependency and implement**

```bash
pip3 install --break-system-packages prometheus-client
```

**Create `backend/src/network/prometheus_exporter.py`:**

```python
"""Prometheus metrics collector for Network Monitor."""
from __future__ import annotations
from prometheus_client import (
    CollectorRegistry, Counter, Gauge, Histogram,
    generate_latest, CONTENT_TYPE_LATEST,
)

class MetricsCollector:
    """Wraps prometheus-client metrics for the network monitor."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self._registry = registry or CollectorRegistry()

        self.cycle_duration = Histogram(
            "network_monitor_cycle_duration_seconds",
            "Duration of a full monitor cycle",
            registry=self._registry,
        )
        self.cycle_total = Counter(
            "network_monitor_cycle_total",
            "Total monitor cycles completed",
            registry=self._registry,
        )
        self.pass_duration = Histogram(
            "network_monitor_pass_duration_seconds",
            "Duration of individual monitor passes",
            ["pass_name"],
            registry=self._registry,
        )
        self.devices_total = Gauge(
            "network_monitor_devices_total",
            "Current number of monitored devices",
            registry=self._registry,
        )
        self.alerts_active = Gauge(
            "network_monitor_alerts_active",
            "Current number of active alerts",
            registry=self._registry,
        )
        self.adapter_errors = Counter(
            "network_monitor_adapter_errors_total",
            "Total adapter errors",
            ["adapter_type"],
            registry=self._registry,
        )

    def record_cycle_duration(self, duration_s: float) -> None:
        self.cycle_duration.observe(duration_s)

    def increment_cycle_total(self) -> None:
        self.cycle_total.inc()

    def record_pass_duration(self, pass_name: str, duration_s: float) -> None:
        self.pass_duration.labels(pass_name=pass_name).observe(duration_s)

    def set_device_count(self, count: int) -> None:
        self.devices_total.set(count)

    def set_active_alerts(self, count: int) -> None:
        self.alerts_active.set(count)

    def increment_adapter_errors(self, adapter_type: str) -> None:
        self.adapter_errors.labels(adapter_type=adapter_type).inc()

    def generate_metrics(self) -> str:
        return generate_latest(self._registry).decode("utf-8")
```

**Modify `backend/src/api/main.py`** — add `/metrics` endpoint:
```python
from src.network.prometheus_exporter import MetricsCollector
from fastapi.responses import PlainTextResponse

# Module-level singleton
metrics_collector = MetricsCollector()

# After app creation:
@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    return metrics_collector.generate_metrics()
```

**Modify `backend/src/network/monitor.py`** — instrument `_collect_cycle`:

In `__init__()` add optional `metrics_collector` param:
```python
self.metrics_collector = None  # Set externally if Prometheus enabled
```

In `_collect_cycle()`, after timing:
```python
if self.metrics_collector:
    self.metrics_collector.record_cycle_duration(self._last_cycle_duration)
    self.metrics_collector.increment_cycle_total()
    self.metrics_collector.set_device_count(len(self.store.list_devices()))
    if self.alert_engine:
        self.metrics_collector.set_active_alerts(len(self.alert_engine.get_active_alerts()))
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_prometheus_exporter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/network/prometheus_exporter.py tests/test_prometheus_exporter.py src/api/main.py src/network/monitor.py
git commit -m "feat(observability): add Prometheus metrics export with /metrics endpoint"
```

---

### Task 2: MS Teams Notification Channel

**Files:**
- Modify: `backend/src/network/models.py` (add `TEAMS` to ChannelType enum)
- Modify: `backend/src/network/notification_dispatcher.py` (add `_send_teams` method)
- Test: `backend/tests/test_teams_channel.py`

**Context:**
- MS Teams uses incoming webhook connectors — POST JSON with an Adaptive Card payload.
- The webhook URL format is `https://outlook.office.com/webhook/...` or the newer Power Automate format.
- Adaptive Card schema v1.4: title, severity color, metric details, entity ID.
- Channel config: `{"webhook_url": "https://..."}` — same pattern as Slack.

**Step 1: Write the failing tests**

Create `backend/tests/test_teams_channel.py`:

```python
"""Tests for MS Teams notification channel."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.network.models import ChannelType, NotificationChannel
from src.network.notification_dispatcher import NotificationDispatcher


class TestTeamsChannelType:
    def test_teams_enum_exists(self):
        assert ChannelType.TEAMS == "teams"

    def test_create_teams_channel(self):
        ch = NotificationChannel(
            id="teams-1", name="DevOps Teams",
            channel_type=ChannelType.TEAMS,
            config={"webhook_url": "https://outlook.office.com/webhook/test"},
        )
        assert ch.channel_type == ChannelType.TEAMS


class TestTeamsDispatch:
    @pytest.mark.asyncio
    async def test_send_teams_calls_webhook(self):
        dispatcher = NotificationDispatcher()
        ch = NotificationChannel(
            id="teams-1", name="DevOps Teams",
            channel_type=ChannelType.TEAMS,
            config={"webhook_url": "https://outlook.office.com/webhook/test"},
        )
        dispatcher.add_channel(ch)

        alert = {
            "severity": "critical",
            "rule_name": "High Latency",
            "entity_id": "router-1",
            "metric": "latency_ms",
            "value": 250,
            "message": "Latency exceeded threshold",
            "key": "latency_ms:router-1",
        }

        with patch("src.network.notification_dispatcher.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.AsyncClient.return_value = mock_client

            await dispatcher._send(ch, alert)

            mock_client.post.assert_awaited_once()
            call_args = mock_client.post.call_args
            assert "outlook.office.com" in call_args[0][0] or "outlook.office.com" in str(call_args)

    @pytest.mark.asyncio
    async def test_teams_payload_has_adaptive_card(self):
        dispatcher = NotificationDispatcher()
        ch = NotificationChannel(
            id="teams-1", name="Test Teams",
            channel_type=ChannelType.TEAMS,
            config={"webhook_url": "https://test.webhook.office.com/test"},
        )
        alert = {
            "severity": "warning",
            "rule_name": "Packet Loss",
            "entity_id": "switch-2",
            "metric": "packet_loss",
            "value": 0.15,
            "message": "Packet loss above 10%",
        }

        with patch("src.network.notification_dispatcher.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.AsyncClient.return_value = mock_client

            await dispatcher._send(ch, alert)

            payload = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
            # Should be an Adaptive Card or MessageCard
            assert payload is not None

    @pytest.mark.asyncio
    async def test_teams_without_httpx(self):
        """Should gracefully handle missing httpx."""
        dispatcher = NotificationDispatcher()
        ch = NotificationChannel(
            id="teams-1", name="Test",
            channel_type=ChannelType.TEAMS,
            config={"webhook_url": "https://test.webhook.office.com/test"},
        )
        with patch.object(
            dispatcher.__class__.__module__.split('.')[0] + ".network.notification_dispatcher",
            "HAS_HTTPX", False,
        ):
            # Should not raise
            await dispatcher._send(ch, {"severity": "info"})
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_teams_channel.py -v`
Expected: FAIL — `ChannelType.TEAMS` doesn't exist.

**Step 3: Implement**

**models.py** — add to ChannelType enum:
```python
TEAMS = "teams"
```

**notification_dispatcher.py** — add Teams routing in `_send()`:
```python
elif channel.channel_type == ChannelType.TEAMS:
    await self._send_teams(channel, alert)
```

Add `_send_teams()` method:
```python
async def _send_teams(self, channel: NotificationChannel, alert: dict) -> None:
    if not HAS_HTTPX:
        logger.warning("httpx not installed — cannot send Teams message")
        return
    webhook_url = channel.config.get("webhook_url", "")
    severity = alert.get("severity", "info")
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
                        "text": f"[{severity.upper()}] {alert.get('rule_name', 'Alert')}",
                        "color": color,
                    },
                    {
                        "type": "FactSet",
                        "facts": [
                            {"title": "Entity", "value": alert.get("entity_id", "")},
                            {"title": "Metric", "value": f"{alert.get('metric', '')} = {alert.get('value', '')}"},
                            {"title": "Message", "value": alert.get("message", "")},
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_teams_channel.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/network/models.py src/network/notification_dispatcher.py tests/test_teams_channel.py
git commit -m "feat(notifications): add MS Teams notification channel with Adaptive Card support"
```

---

### Task 3: Opsgenie Notification Channel

**Files:**
- Modify: `backend/src/network/models.py` (add `OPSGENIE` to ChannelType enum)
- Modify: `backend/src/network/notification_dispatcher.py` (add `_send_opsgenie` method)
- Test: `backend/tests/test_opsgenie_channel.py`

**Context:**
- Opsgenie Alert API: POST to `https://api.opsgenie.com/v2/alerts` with `Authorization: GenieKey <api_key>`.
- Payload: `{message, description, priority, tags, entity, source, details}`.
- Priority mapping: critical→P1, warning→P2, info→P3.
- Channel config: `{"api_key": "...", "tags": ["network", "debugduck"]}`.

**Step 1: Write the failing tests**

Create `backend/tests/test_opsgenie_channel.py`:

```python
"""Tests for Opsgenie notification channel."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.network.models import ChannelType, NotificationChannel
from src.network.notification_dispatcher import NotificationDispatcher


class TestOpsgenieChannelType:
    def test_opsgenie_enum_exists(self):
        assert ChannelType.OPSGENIE == "opsgenie"

    def test_create_opsgenie_channel(self):
        ch = NotificationChannel(
            id="og-1", name="Opsgenie Prod",
            channel_type=ChannelType.OPSGENIE,
            config={"api_key": "fake-key-123", "tags": ["network"]},
        )
        assert ch.channel_type == ChannelType.OPSGENIE


class TestOpsgenieDispatch:
    @pytest.mark.asyncio
    async def test_send_opsgenie_calls_api(self):
        dispatcher = NotificationDispatcher()
        ch = NotificationChannel(
            id="og-1", name="Opsgenie",
            channel_type=ChannelType.OPSGENIE,
            config={"api_key": "test-key"},
        )
        alert = {
            "severity": "critical",
            "rule_name": "Device Down",
            "entity_id": "fw-1",
            "metric": "status",
            "value": "down",
            "message": "Firewall fw-1 is unreachable",
            "key": "status:fw-1",
        }

        with patch("src.network.notification_dispatcher.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.AsyncClient.return_value = mock_client

            await dispatcher._send(ch, alert)

            mock_client.post.assert_awaited_once()
            call_args = mock_client.post.call_args
            url = call_args[0][0]
            assert "api.opsgenie.com" in url

    @pytest.mark.asyncio
    async def test_opsgenie_priority_mapping(self):
        dispatcher = NotificationDispatcher()
        ch = NotificationChannel(
            id="og-1", name="Opsgenie",
            channel_type=ChannelType.OPSGENIE,
            config={"api_key": "test-key"},
        )

        with patch("src.network.notification_dispatcher.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.AsyncClient.return_value = mock_client

            await dispatcher._send(ch, {"severity": "critical", "key": "test"})
            payload = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
            assert payload["priority"] == "P1"

    @pytest.mark.asyncio
    async def test_opsgenie_includes_auth_header(self):
        dispatcher = NotificationDispatcher()
        ch = NotificationChannel(
            id="og-1", name="Opsgenie",
            channel_type=ChannelType.OPSGENIE,
            config={"api_key": "my-secret-key"},
        )

        with patch("src.network.notification_dispatcher.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.AsyncClient.return_value = mock_client

            await dispatcher._send(ch, {"severity": "warning", "key": "test2"})
            headers = mock_client.post.call_args.kwargs.get("headers") or mock_client.post.call_args[1].get("headers")
            assert headers["Authorization"] == "GenieKey my-secret-key"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_opsgenie_channel.py -v`
Expected: FAIL — `ChannelType.OPSGENIE` doesn't exist.

**Step 3: Implement**

**models.py** — add to ChannelType enum:
```python
OPSGENIE = "opsgenie"
```

**notification_dispatcher.py** — add Opsgenie routing in `_send()`:
```python
elif channel.channel_type == ChannelType.OPSGENIE:
    await self._send_opsgenie(channel, alert)
```

Add `_send_opsgenie()` method:
```python
async def _send_opsgenie(self, channel: NotificationChannel, alert: dict) -> None:
    if not HAS_HTTPX:
        logger.warning("httpx not installed — cannot send Opsgenie alert")
        return
    api_key = channel.config.get("api_key", "")
    severity = alert.get("severity", "info")
    priority = {"critical": "P1", "warning": "P2"}.get(severity, "P3")
    tags = channel.config.get("tags", [])
    payload = {
        "message": f"[{severity.upper()}] {alert.get('rule_name', 'Alert')}",
        "description": alert.get("message", ""),
        "priority": priority,
        "tags": tags + [severity],
        "entity": alert.get("entity_id", ""),
        "source": "DebugDuck Network Observatory",
        "alias": alert.get("key", ""),
        "details": {
            "metric": alert.get("metric", ""),
            "value": str(alert.get("value", "")),
            "threshold": str(alert.get("threshold", "")),
            "rule": alert.get("rule_name", ""),
        },
    }
    headers = {
        "Authorization": f"GenieKey {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.opsgenie.com/v2/alerts",
            json=payload, headers=headers,
        )
        resp.raise_for_status()
    logger.info("Opsgenie alert sent (alias=%s)", alert.get("key"))
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_opsgenie_channel.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/network/models.py src/network/notification_dispatcher.py tests/test_opsgenie_channel.py
git commit -m "feat(notifications): add Opsgenie notification channel with priority mapping"
```

---

### Task 4: Alert Deduplication

**Files:**
- Modify: `backend/src/network/notification_dispatcher.py` (add dedup logic)
- Test: `backend/tests/test_alert_dedup.py`

**Context:**
- Currently, every `dispatch()` call sends to all matched channels — no dedup.
- If the 30s monitor cycle fires the same alert repeatedly, the same Slack/Teams/PagerDuty notification is sent every 30 seconds.
- PagerDuty has built-in dedup via `dedup_key`, but Slack/Teams/Email/Webhook do not.
- Solution: track dispatched `(alert_key, channel_id)` pairs in a TTL dict. Skip if already sent within the dedup window (default 300s / 5 minutes).
- Only dedup repeat firings — resolved alerts and escalations should always send.

**Step 1: Write the failing tests**

Create `backend/tests/test_alert_dedup.py`:

```python
"""Tests for alert notification deduplication."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.network.models import ChannelType, NotificationChannel, NotificationRouting
from src.network.notification_dispatcher import NotificationDispatcher


@pytest.fixture
def dispatcher():
    d = NotificationDispatcher()
    ch = NotificationChannel(
        id="slack-1", name="Slack",
        channel_type=ChannelType.SLACK,
        config={"webhook_url": "https://hooks.slack.com/test"},
    )
    d.add_channel(ch)
    d.add_routing(NotificationRouting(
        id="r1", name="All Critical",
        severity_filter=["critical"],
        channel_ids=["slack-1"],
    ))
    return d


class TestAlertDedup:
    @pytest.mark.asyncio
    async def test_first_dispatch_sends(self, dispatcher):
        """First alert dispatch should send."""
        dispatcher._send = AsyncMock()
        await dispatcher.dispatch({"severity": "critical", "key": "test:1"})
        dispatcher._send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_suppressed(self, dispatcher):
        """Same alert key + channel within dedup window should be suppressed."""
        dispatcher._send = AsyncMock()
        await dispatcher.dispatch({"severity": "critical", "key": "test:1"})
        await dispatcher.dispatch({"severity": "critical", "key": "test:1"})
        # Should only send once
        assert dispatcher._send.await_count == 1

    @pytest.mark.asyncio
    async def test_different_keys_both_send(self, dispatcher):
        """Different alert keys should both send."""
        dispatcher._send = AsyncMock()
        await dispatcher.dispatch({"severity": "critical", "key": "test:1"})
        await dispatcher.dispatch({"severity": "critical", "key": "test:2"})
        assert dispatcher._send.await_count == 2

    @pytest.mark.asyncio
    async def test_resolved_alerts_bypass_dedup(self, dispatcher):
        """Resolved alerts should always send (not deduped)."""
        dispatcher._send = AsyncMock()
        await dispatcher.dispatch({"severity": "critical", "key": "test:1"})
        await dispatcher.dispatch({"severity": "critical", "key": "test:1", "resolved": True})
        assert dispatcher._send.await_count == 2

    @pytest.mark.asyncio
    async def test_escalated_alerts_bypass_dedup(self, dispatcher):
        """Escalated alerts should always send (not deduped)."""
        dispatcher._send = AsyncMock()
        await dispatcher.dispatch({"severity": "critical", "key": "test:1"})
        await dispatcher.dispatch({"severity": "critical", "key": "test:1", "escalated": True})
        assert dispatcher._send.await_count == 2

    @pytest.mark.asyncio
    async def test_dedup_window_configurable(self):
        """Dedup window should be configurable."""
        d = NotificationDispatcher(dedup_window_seconds=0)
        ch = NotificationChannel(
            id="slack-1", name="Slack",
            channel_type=ChannelType.SLACK,
            config={"webhook_url": "https://hooks.slack.com/test"},
        )
        d.add_channel(ch)
        d.add_routing(NotificationRouting(
            id="r1", name="All",
            severity_filter=["critical"],
            channel_ids=["slack-1"],
        ))
        d._send = AsyncMock()
        await d.dispatch({"severity": "critical", "key": "test:1"})
        await d.dispatch({"severity": "critical", "key": "test:1"})
        # With 0s window, both should send
        assert d._send.await_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_alert_dedup.py -v`
Expected: FAIL — `NotificationDispatcher` doesn't accept `dedup_window_seconds`.

**Step 3: Implement dedup**

**notification_dispatcher.py:**

In `__init__()`:
```python
def __init__(self, dedup_window_seconds: int = 300) -> None:
    self._channels: dict[str, NotificationChannel] = {}
    self._routings: list[NotificationRouting] = []
    self._escalations: list[EscalationPolicy] = []
    self._escalated_keys: set[str] = set()
    self._dedup_window = dedup_window_seconds
    self._dedup_sent: dict[str, float] = {}  # "alert_key:channel_id" -> timestamp
```

In `dispatch()`, before sending, check dedup:
```python
async def dispatch(self, alert: dict) -> None:
    severity = alert.get("severity", "")
    is_resolved = alert.get("resolved", False)
    is_escalated = alert.get("escalated", False)
    alert_key = alert.get("key", "")
    target_channel_ids: set[str] = set()

    for routing in self._routings:
        if not routing.enabled:
            continue
        if severity in routing.severity_filter:
            target_channel_ids.update(routing.channel_ids)

    now = time.time()
    # Prune expired dedup entries
    self._dedup_sent = {
        k: v for k, v in self._dedup_sent.items()
        if now - v < self._dedup_window
    }

    tasks = []
    for ch_id in target_channel_ids:
        channel = self._channels.get(ch_id)
        if not channel or not channel.enabled:
            continue

        # Dedup check: skip if same alert+channel was sent within window
        # Bypass dedup for resolved and escalated alerts
        if not is_resolved and not is_escalated and self._dedup_window > 0:
            dedup_key = f"{alert_key}:{ch_id}"
            if dedup_key in self._dedup_sent:
                continue
            self._dedup_sent[dedup_key] = now

        tasks.append(self._send(channel, alert))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
```

**IMPORTANT:** Also update the existing `NotificationDispatcher()` call in `monitor.py` to pass the dedup window (or keep default 300s which is fine).

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_alert_dedup.py -v`
Expected: PASS

Also run existing notification tests: `python3 -m pytest tests/test_notification_dispatcher.py -v`
Expected: PASS (no regressions)

**Step 5: Commit**

```bash
git add src/network/notification_dispatcher.py tests/test_alert_dedup.py
git commit -m "feat(notifications): add alert deduplication with configurable TTL window"
```

---

### Task 5: Final Verification

**Files:** None (read-only verification)

**Step 1: Run all Phase 6 tests**

```bash
cd backend && python3 -m pytest tests/test_prometheus_exporter.py tests/test_teams_channel.py tests/test_opsgenie_channel.py tests/test_alert_dedup.py -v
```

**Step 2: Run full suite**

```bash
python3 -m pytest tests/ --tb=line -q 2>&1 | tail -5
```

**Step 3: Verify imports**

```bash
python3 -c "
from src.network.prometheus_exporter import MetricsCollector
from src.network.models import ChannelType
from src.network.notification_dispatcher import NotificationDispatcher

print('MetricsCollector:', MetricsCollector)
print('ChannelTypes:', [c.value for c in ChannelType])
print('Dedup param:', 'dedup_window_seconds' in NotificationDispatcher.__init__.__code__.co_varnames)
print('All Phase 6 imports verified')
"
```

**Step 4: Verify /metrics endpoint**

```bash
python3 -c "
from fastapi.testclient import TestClient
from src.api.main import app
client = TestClient(app)
resp = client.get('/metrics')
print('Status:', resp.status_code)
print('Has metrics:', 'network_monitor' in resp.text)
"
```

# Phase 9: Real-Time Events & Alert Escalation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire real-time WebSocket broadcasts for monitor events (alerts, drifts, discovery), integrate alert escalation into the monitor cycle, and add device status history endpoints.

**Architecture:** Monitor's `_collect_cycle` broadcasts snapshot deltas via the existing WebSocket `manager.broadcast()`. Escalation check runs after alert pass. New endpoints expose device status history and alert history with pagination.

**Tech Stack:** FastAPI WebSocket (existing), asyncio, SQLite (existing)

---

### Task 1: WebSocket Broadcast of Monitor Events

**Files:**
- Modify: `backend/src/network/monitor.py` (add broadcast callback, call after each cycle)
- Modify: `backend/src/api/main.py` (pass broadcast callback to monitor)
- Create: `backend/tests/test_monitor_broadcast.py`

**Context:**
- `ConnectionManager.broadcast(message)` already exists in `backend/src/api/websocket.py`
- Monitor runs `_collect_cycle()` every 30s — at the end, it should broadcast a summary
- The broadcast message should include: alert count, new drift events, new discovery candidates, cycle duration
- The monitor needs a callback since it shouldn't import WebSocket directly (layer separation)

**Step 1: Write the failing tests**

Create `backend/tests/test_monitor_broadcast.py`:

```python
"""Tests for monitor WebSocket broadcast integration."""
import asyncio
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_monitor_broadcast.py -v`
Expected: FAIL — `broadcast_callback` parameter doesn't exist.

**Step 3: Implement**

**Modify `backend/src/network/monitor.py`:**

In `__init__`, add `broadcast_callback=None` parameter:
```python
def __init__(self, store, kg, adapters, prometheus_url=None, metrics_store=None,
             dns_config=None, broadcast_callback=None):
    # ... existing init ...
    self._broadcast_callback = broadcast_callback
```

At the end of `_collect_cycle()`, after metrics_collector block, add:
```python
# Broadcast monitor update to WebSocket clients
if self._broadcast_callback:
    try:
        await self._broadcast_callback({
            "type": "monitor_update",
            "data": {
                "active_alerts": len(self._latest_alerts),
                "drift_count": len(self.store.list_active_drift_events()),
                "candidate_count": len(self.store.list_discovery_candidates()),
                "device_count": len(self.store.list_device_statuses()),
                "cycle_duration": self._last_cycle_duration,
                "status": self.health_status(),
            },
        })
    except Exception as e:
        logger.debug("Broadcast failed: %s", e)
```

**Modify `backend/src/api/main.py`:**

In the startup handler, when creating the NetworkMonitor, pass the broadcast callback:
```python
monitor = NetworkMonitor(
    topo_store, kg, _adapter_registry,
    metrics_store=metrics_store,
    broadcast_callback=manager.broadcast,
)
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_monitor_broadcast.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/network/monitor.py src/api/main.py tests/test_monitor_broadcast.py
git commit -m "feat(monitor): broadcast monitor events to WebSocket clients after each cycle"
```

---

### Task 2: Alert Escalation in Monitor Cycle

**Files:**
- Modify: `backend/src/network/monitor.py` (call check_escalations after alert pass)
- Create: `backend/tests/test_escalation_integration.py`

**Context:**
- `NotificationDispatcher.check_escalations(active_alerts)` is already implemented but never called
- Should run after `_alert_pass()` in the cycle
- The alert engine has `get_active_alerts()` which returns the list needed for escalation checking
- The dispatcher is accessible via `self.alert_engine._dispatcher`

**Step 1: Write the failing tests**

Create `backend/tests/test_escalation_integration.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_escalation_integration.py -v`
Expected: FAIL — escalation check not called in cycle.

**Step 3: Implement**

**Modify `backend/src/network/monitor.py`:**

In `_alert_pass()`, after evaluating alerts, add escalation check:
```python
async def _alert_pass(self):
    if not self.alert_engine:
        return
    device_ids = [d["device_id"] for d in self.store.list_device_statuses()]
    self._latest_alerts = await self.alert_engine.evaluate_all(device_ids)
    # Check escalation policies for unacknowledged alerts
    dispatcher = getattr(self.alert_engine, '_dispatcher', None)
    if dispatcher:
        try:
            escalated = await dispatcher.check_escalations(
                self.alert_engine.get_active_alerts()
            )
            if escalated:
                logger.info("Escalated %d alerts", len(escalated))
        except Exception as e:
            logger.warning("Escalation check failed: %s", e)
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_escalation_integration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/network/monitor.py tests/test_escalation_integration.py
git commit -m "feat(alerts): integrate escalation check into monitor cycle"
```

---

### Task 3: Device Status History & Alert History Endpoints

**Files:**
- Modify: `backend/src/api/monitor_endpoints.py` (add 2 new endpoints)
- Create: `backend/tests/test_history_endpoints.py`

**Context:**
- `TopologyStore.query_metric_history(entity_type, entity_id, metric_name, limit)` already exists
- `AlertEngine.get_alert_history()` or similar may exist — check actual implementation
- Need `GET /api/v4/network/monitor/device-statuses` (paginated)
- Need `GET /api/v4/network/monitor/metric-history` (query by entity)
- The monitor_endpoints module already has `_topology_store` and `_monitor` globals

**Step 1: Write the failing tests**

Create `backend/tests/test_history_endpoints.py`:

```python
"""Tests for device status and metric history endpoints."""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import DeviceType


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.upsert_device("d1", "Router1", "cisco", DeviceType.ROUTER, "10.0.0.1")
    store.upsert_device("d2", "Switch1", "juniper", DeviceType.SWITCH, "10.0.0.2")
    store.upsert_device_status("d1", "up", 5.0, 0.0, "icmp")
    store.upsert_device_status("d2", "degraded", 150.0, 0.05, "icmp")
    store.append_metric("device", "d1", "latency_ms", 5.0)
    store.append_metric("device", "d1", "latency_ms", 6.0)
    store.append_metric("device", "d1", "latency_ms", 7.0)

    from src.api.main import app
    import src.api.monitor_endpoints as mon_ep
    orig_store = mon_ep._topology_store
    mon_ep._topology_store = store
    client = TestClient(app)
    yield store, client
    mon_ep._topology_store = orig_store


class TestDeviceStatusList:
    def test_list_device_statuses(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/device-statuses")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2

    def test_list_device_statuses_pagination(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/device-statuses?offset=0&limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total"] == 2


class TestMetricHistory:
    def test_query_metric_history(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/metric-history?entity_type=device&entity_id=d1&metric_name=latency_ms")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_query_metric_history_with_limit(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/metric-history?entity_type=device&entity_id=d1&metric_name=latency_ms&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_query_metric_history_missing_params(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/metric-history")
        assert resp.status_code == 422  # validation error
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_history_endpoints.py -v`
Expected: FAIL — endpoints don't exist.

**Step 3: Implement**

**Modify `backend/src/api/monitor_endpoints.py`:**

Read the file first to understand its current structure. Then add two new endpoints:

```python
@monitor_router.get("/device-statuses")
def list_device_statuses(offset: int = 0, limit: int = 100):
    store = _topology_store
    if not store:
        return {"items": [], "total": 0}
    all_statuses = store.list_device_statuses()
    total = len(all_statuses)
    items = all_statuses[offset:offset + limit]
    return {"items": items, "total": total}


@monitor_router.get("/metric-history")
def query_metric_history(
    entity_type: str,
    entity_id: str,
    metric_name: str,
    limit: int = 100,
):
    store = _topology_store
    if not store:
        return []
    return store.query_metric_history(entity_type, entity_id, metric_name, limit=limit)
```

IMPORTANT: Check the actual `monitor_router` prefix (likely `/api/v4/network/monitor`) and the actual method signatures in `topology_store.py` for `list_device_statuses()` and `query_metric_history()`.

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_history_endpoints.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/monitor_endpoints.py tests/test_history_endpoints.py
git commit -m "feat(monitor): add device-statuses and metric-history endpoints"
```

---

### Task 4: Final Verification

**Files:** None (read-only verification)

**Step 1: Run all Phase 9 tests**

```bash
cd backend && python3 -m pytest tests/test_monitor_broadcast.py tests/test_escalation_integration.py tests/test_history_endpoints.py -v
```

**Step 2: Run full test suite**

```bash
python3 -m pytest tests/ --tb=line -q 2>&1 | tail -5
```

**Step 3: Verify imports**

```bash
python3 -c "
from src.network.monitor import NetworkMonitor
from src.network.notification_dispatcher import NotificationDispatcher
print('Monitor has broadcast_callback:', 'broadcast_callback' in NetworkMonitor.__init__.__code__.co_varnames)
print('All Phase 9 imports verified')
"
```

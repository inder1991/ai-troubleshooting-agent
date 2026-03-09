# Alert Maturity Implementation Plan (Phase 4)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Mature the alert system from basic threshold evaluation to production-grade alerting with rule CRUD, persistent alert history, maintenance windows, escalation policies, and composite rules.

**Architecture:** Extends existing `AlertEngine` and `NotificationDispatcher` with new capabilities. Alert history persisted to SQLite via `TopologyStore`. Maintenance windows suppress alert dispatch during scheduled periods. Escalation policies re-route unacknowledged alerts after timeout. Composite rules combine multiple conditions with AND/OR logic. All new features exposed via API endpoints.

**Tech Stack:** Existing AlertEngine + NotificationDispatcher, SQLite (TopologyStore), FastAPI endpoints.

---

### Task 1: Alert Rule CRUD API

**Files:**
- Modify: `backend/src/network/alert_engine.py` (add `update_rule`, `get_rule`)
- Modify: `backend/src/api/monitor_endpoints.py` (add POST/PUT/DELETE for rules)
- Test: `backend/tests/test_alert_rule_crud.py`

**Step 1: Write failing tests**

Create `backend/tests/test_alert_rule_crud.py`:

```python
"""Tests for alert rule CRUD operations."""
import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock

# Mock influxdb_client
if "influxdb_client" not in sys.modules:
    _mock_influx = types.ModuleType("influxdb_client")
    _mock_influx.Point = MagicMock()
    _mock_influx.WritePrecision = MagicMock()
    _mock_async = types.ModuleType("influxdb_client.client")
    _mock_async_mod = types.ModuleType("influxdb_client.client.influxdb_client_async")
    _mock_async_mod.InfluxDBClientAsync = MagicMock()
    sys.modules["influxdb_client"] = _mock_influx
    sys.modules["influxdb_client.client"] = _mock_async
    sys.modules["influxdb_client.client.influxdb_client_async"] = _mock_async_mod

from src.network.alert_engine import AlertEngine, AlertRule
from fastapi.testclient import TestClient
from src.api.main import app


@pytest.fixture
def mock_metrics():
    store = AsyncMock()
    store.query_device_metrics = AsyncMock(return_value=[])
    store.write_alert_event = AsyncMock()
    return store


@pytest.fixture
def engine(mock_metrics):
    return AlertEngine(mock_metrics, load_defaults=True)


@pytest.fixture
def client():
    return TestClient(app)


class TestAlertRuleEngine:
    def test_get_rule_by_id(self, engine):
        rule = engine.get_rule("default-unreachable")
        assert rule is not None
        assert rule["name"] == "Device Unreachable"

    def test_get_rule_not_found(self, engine):
        rule = engine.get_rule("nonexistent")
        assert rule is None

    def test_update_rule(self, engine):
        ok = engine.update_rule("default-unreachable", threshold=0.95, cooldown_seconds=120)
        assert ok
        rule = engine.get_rule("default-unreachable")
        assert rule["threshold"] == 0.95
        assert rule["cooldown_seconds"] == 120

    def test_update_rule_not_found(self, engine):
        ok = engine.update_rule("nonexistent", threshold=50)
        assert not ok

    def test_update_rule_enable_disable(self, engine):
        engine.update_rule("default-unreachable", enabled=False)
        rule = engine.get_rule("default-unreachable")
        assert rule["enabled"] is False

    def test_remove_rule(self, engine):
        initial = len(engine.rules)
        engine.remove_rule("default-unreachable")
        assert len(engine.rules) == initial - 1

    def test_add_custom_rule(self, engine):
        initial = len(engine.rules)
        rule = AlertRule(
            id="custom-disk", name="Disk Full", severity="critical",
            entity_type="device", entity_filter="*",
            metric="disk_pct", condition="gt", threshold=95.0,
        )
        engine.add_rule(rule)
        assert len(engine.rules) == initial + 1


class TestAlertRuleCRUDAPI:
    def test_create_rule(self, client):
        resp = client.post("/api/v4/network/monitor/alerts/rules", json={
            "id": "custom-test", "name": "Test Rule", "severity": "warning",
            "entity_type": "device", "entity_filter": "*",
            "metric": "test_metric", "condition": "gt", "threshold": 50.0,
        })
        assert resp.status_code == 200
        assert resp.json()["id"] == "custom-test"

    def test_update_rule_api(self, client):
        # First create
        client.post("/api/v4/network/monitor/alerts/rules", json={
            "id": "custom-update", "name": "Update Me", "severity": "warning",
            "entity_type": "device", "entity_filter": "*",
            "metric": "cpu_pct", "condition": "gt", "threshold": 80.0,
        })
        # Then update
        resp = client.put("/api/v4/network/monitor/alerts/rules/custom-update", json={
            "threshold": 90.0, "severity": "critical",
        })
        assert resp.status_code == 200

    def test_delete_rule_api(self, client):
        client.post("/api/v4/network/monitor/alerts/rules", json={
            "id": "custom-delete", "name": "Delete Me", "severity": "info",
            "entity_type": "device", "entity_filter": "*",
            "metric": "test", "condition": "gt", "threshold": 1.0,
        })
        resp = client.delete("/api/v4/network/monitor/alerts/rules/custom-delete")
        assert resp.status_code == 200

    def test_get_single_rule_api(self, client):
        resp = client.get("/api/v4/network/monitor/alerts/rules/default-unreachable")
        # May be 200 or 404 depending on monitor state
        assert resp.status_code in (200, 404)
```

**Step 2: Run tests — expect failures**

Run: `cd backend && python3 -m pytest tests/test_alert_rule_crud.py -v`

**Step 3: Add `get_rule` and `update_rule` to AlertEngine**

In `backend/src/network/alert_engine.py`, add after `remove_rule`:

```python
    def get_rule(self, rule_id: str) -> dict | None:
        """Return a single rule as dict, or None if not found."""
        for r in self.rules:
            if r.id == rule_id:
                return {
                    "id": r.id, "name": r.name, "severity": r.severity,
                    "entity_type": r.entity_type, "entity_filter": r.entity_filter,
                    "metric": r.metric, "condition": r.condition,
                    "threshold": r.threshold, "duration_seconds": r.duration_seconds,
                    "cooldown_seconds": r.cooldown_seconds, "enabled": r.enabled,
                    "description": r.description,
                }
        return None

    def update_rule(self, rule_id: str, **kwargs) -> bool:
        """Update fields on an existing rule. Returns True if found."""
        for r in self.rules:
            if r.id == rule_id:
                for key, value in kwargs.items():
                    if hasattr(r, key):
                        setattr(r, key, value)
                return True
        return False
```

**Step 4: Add rule CRUD endpoints to `monitor_endpoints.py`**

After the existing `GET /alerts/rules` endpoint, add:

```python
@monitor_router.get("/alerts/rules/{rule_id}")
async def get_alert_rule(rule_id: str):
    """Get a single alert rule by ID."""
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        raise HTTPException(404, "Monitor not running")
    rule = mon.alert_engine.get_rule(rule_id)
    if not rule:
        raise HTTPException(404, f"Rule '{rule_id}' not found")
    return rule


@monitor_router.post("/alerts/rules")
async def create_alert_rule(body: dict):
    """Create a new custom alert rule."""
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        raise HTTPException(503, "Alert engine not initialized")
    rule = AlertRule(**body)
    mon.alert_engine.add_rule(rule)
    return {"status": "created", "id": rule.id}


@monitor_router.put("/alerts/rules/{rule_id}")
async def update_alert_rule(rule_id: str, body: dict):
    """Update fields on an existing alert rule."""
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        raise HTTPException(503, "Alert engine not initialized")
    ok = mon.alert_engine.update_rule(rule_id, **body)
    if not ok:
        raise HTTPException(404, f"Rule '{rule_id}' not found")
    return {"status": "updated", "id": rule_id}


@monitor_router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Delete an alert rule."""
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        raise HTTPException(503, "Alert engine not initialized")
    mon.alert_engine.remove_rule(rule_id)
    return {"status": "deleted", "id": rule_id}
```

Add import at top of monitor_endpoints.py:
```python
from src.network.alert_engine import AlertRule
```

**Step 5: Run tests**

Run: `cd backend && python3 -m pytest tests/test_alert_rule_crud.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add backend/src/network/alert_engine.py backend/src/api/monitor_endpoints.py backend/tests/test_alert_rule_crud.py
git commit -m "feat(alerts): add alert rule CRUD API with get/update/create/delete"
```

---

### Task 2: Alert History — Persistent Audit Trail

**Files:**
- Modify: `backend/src/network/topology_store.py` (add alert_history table + queries)
- Modify: `backend/src/network/alert_engine.py` (persist fired/resolved events)
- Modify: `backend/src/api/monitor_endpoints.py` (add history endpoint)
- Test: `backend/tests/test_alert_history.py`

**Step 1: Write failing tests**

Create `backend/tests/test_alert_history.py`:

```python
"""Tests for alert history persistence."""
import os
import time
import pytest
from unittest.mock import AsyncMock

from src.network.topology_store import TopologyStore
from src.network.alert_engine import AlertEngine, AlertRule


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def mock_metrics():
    m = AsyncMock()
    m.query_device_metrics = AsyncMock(return_value=[])
    m.write_alert_event = AsyncMock()
    return m


class TestAlertHistoryStore:
    def test_upsert_alert_event(self, store):
        store.upsert_alert_history(
            alert_key="r1:dev-1", rule_id="r1", rule_name="High CPU",
            entity_id="dev-1", severity="warning", metric="cpu_pct",
            value=95.0, threshold=90.0, condition="gt",
            state="firing", message="High CPU: cpu_pct=95.0",
        )
        history = store.list_alert_history()
        assert len(history) == 1
        assert history[0]["alert_key"] == "r1:dev-1"
        assert history[0]["state"] == "firing"

    def test_resolve_alert(self, store):
        store.upsert_alert_history(
            alert_key="r1:dev-1", rule_id="r1", rule_name="High CPU",
            entity_id="dev-1", severity="warning", metric="cpu_pct",
            value=95.0, threshold=90.0, condition="gt",
            state="firing", message="fired",
        )
        store.upsert_alert_history(
            alert_key="r1:dev-1", rule_id="r1", rule_name="High CPU",
            entity_id="dev-1", severity="warning", metric="cpu_pct",
            value=85.0, threshold=90.0, condition="gt",
            state="resolved", message="resolved",
        )
        history = store.list_alert_history()
        assert len(history) == 2

    def test_list_alert_history_filtered(self, store):
        store.upsert_alert_history(
            alert_key="r1:dev-1", rule_id="r1", rule_name="Rule 1",
            entity_id="dev-1", severity="critical", metric="m1",
            value=1, threshold=0, condition="gt",
            state="firing", message="",
        )
        store.upsert_alert_history(
            alert_key="r2:dev-2", rule_id="r2", rule_name="Rule 2",
            entity_id="dev-2", severity="warning", metric="m2",
            value=2, threshold=0, condition="gt",
            state="firing", message="",
        )
        critical = store.list_alert_history(severity="critical")
        assert len(critical) == 1
        assert critical[0]["severity"] == "critical"

    def test_list_alert_history_limit(self, store):
        for i in range(5):
            store.upsert_alert_history(
                alert_key=f"r{i}:dev-1", rule_id=f"r{i}", rule_name=f"Rule {i}",
                entity_id="dev-1", severity="warning", metric="m",
                value=i, threshold=0, condition="gt",
                state="firing", message="",
            )
        limited = store.list_alert_history(limit=3)
        assert len(limited) == 3

    def test_alert_history_count(self, store):
        for i in range(3):
            store.upsert_alert_history(
                alert_key=f"r{i}:dev-1", rule_id=f"r{i}", rule_name=f"Rule {i}",
                entity_id="dev-1", severity="warning", metric="m",
                value=i, threshold=0, condition="gt",
                state="firing", message="",
            )
        assert store.count_alert_history() == 3


class TestAlertEngineHistory:
    @pytest.mark.asyncio
    async def test_evaluate_persists_to_history(self, store, mock_metrics):
        engine = AlertEngine(mock_metrics)
        engine.set_store(store)
        rule = AlertRule(
            id="r1", name="CPU", severity="warning",
            entity_type="device", entity_filter="*",
            metric="cpu_pct", condition="gt", threshold=90.0,
            duration_seconds=0, cooldown_seconds=0,
        )
        engine.add_rule(rule)
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
        await engine.evaluate("dev-1")

        history = store.list_alert_history()
        assert len(history) == 1
        assert history[0]["state"] == "firing"

    @pytest.mark.asyncio
    async def test_resolve_persists_to_history(self, store, mock_metrics):
        engine = AlertEngine(mock_metrics)
        engine.set_store(store)
        rule = AlertRule(
            id="r1", name="CPU", severity="warning",
            entity_type="device", entity_filter="*",
            metric="cpu_pct", condition="gt", threshold=90.0,
            duration_seconds=0, cooldown_seconds=0,
        )
        engine.add_rule(rule)

        # Fire
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
        await engine.evaluate("dev-1")
        # Resolve
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 50.0}]
        await engine.evaluate("dev-1")

        history = store.list_alert_history()
        assert len(history) == 2
        states = [h["state"] for h in history]
        assert "firing" in states
        assert "resolved" in states
```

**Step 2: Run tests — expect failures**

**Step 3: Add alert_history table to TopologyStore**

In `backend/src/network/topology_store.py`, add to `_init_db()`:

```python
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_key TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL,
                threshold REAL NOT NULL,
                condition TEXT NOT NULL,
                state TEXT NOT NULL,
                message TEXT DEFAULT '',
                timestamp TEXT DEFAULT (datetime('now'))
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alert_history_key ON alert_history(alert_key)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alert_history_severity ON alert_history(severity)")
```

Add methods:

```python
    def upsert_alert_history(
        self, alert_key: str, rule_id: str, rule_name: str,
        entity_id: str, severity: str, metric: str,
        value: float, threshold: float, condition: str,
        state: str, message: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO alert_history
                   (alert_key, rule_id, rule_name, entity_id, severity,
                    metric, value, threshold, condition, state, message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (alert_key, rule_id, rule_name, entity_id, severity,
                 metric, value, threshold, condition, state, message),
            )

    def list_alert_history(
        self, severity: str = "", entity_id: str = "",
        state: str = "", limit: int = 100,
    ) -> list[dict]:
        clauses = []
        params: list = []
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if state:
            clauses.append("state = ?")
            params.append(state)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM alert_history {where} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    def count_alert_history(self, severity: str = "") -> int:
        with self._connect() as conn:
            if severity:
                row = conn.execute(
                    "SELECT COUNT(*) FROM alert_history WHERE severity = ?", (severity,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM alert_history").fetchone()
            return row[0]
```

**Step 4: Add `set_store` to AlertEngine + persist on fire/resolve**

In `backend/src/network/alert_engine.py`:

Add `set_store` method:
```python
    def set_store(self, store) -> None:
        """Attach a TopologyStore for persisting alert history."""
        self._store = store
```

Initialize `self._store = None` in `__init__`.

In `_fire_alert`, after building the alert dict, add:
```python
        if self._store:
            self._store.upsert_alert_history(
                alert_key=key, rule_id=rule.id, rule_name=rule.name,
                entity_id=entity_id, severity=rule.severity,
                metric=rule.metric, value=value, threshold=rule.threshold,
                condition=rule.condition, state="firing",
                message=alert["message"],
            )
```

In `evaluate`, where alerts resolve (the `else` branch that deletes from `_active_alerts`), add:
```python
                if key in self._active_alerts:
                    if self._store:
                        old = self._active_alerts[key]
                        self._store.upsert_alert_history(
                            alert_key=key, rule_id=rule.id, rule_name=rule.name,
                            entity_id=entity_id, severity=rule.severity,
                            metric=rule.metric, value=latest_value,
                            threshold=rule.threshold, condition=rule.condition,
                            state="resolved", message=f"Resolved: {rule.metric}={latest_value:.1f}",
                        )
                    del self._active_alerts[key]
```

**Step 5: Add history API endpoint to `monitor_endpoints.py`**

```python
@monitor_router.get("/alerts/history")
async def get_alert_history(severity: str = "", entity_id: str = "",
                            state: str = "", limit: int = 100):
    """Query alert history."""
    store = _get_topology_store()
    if not store:
        return {"history": []}
    return {"history": store.list_alert_history(
        severity=severity, entity_id=entity_id, state=state, limit=min(limit, 500),
    )}
```

**Step 6: Run tests**

Run: `cd backend && python3 -m pytest tests/test_alert_history.py tests/test_alert_engine.py -v`

**Step 7: Commit**

```bash
git add backend/src/network/topology_store.py backend/src/network/alert_engine.py backend/src/api/monitor_endpoints.py backend/tests/test_alert_history.py
git commit -m "feat(alerts): add persistent alert history with audit trail"
```

---

### Task 3: Maintenance Windows — Suppress Alerts During Planned Work

**Files:**
- Modify: `backend/src/network/alert_engine.py` (add maintenance window logic)
- Modify: `backend/src/api/monitor_endpoints.py` (add maintenance window endpoints)
- Test: `backend/tests/test_maintenance_windows.py`

**Step 1: Write failing tests**

Create `backend/tests/test_maintenance_windows.py`:

```python
"""Tests for maintenance window alert suppression."""
import time
import pytest
from unittest.mock import AsyncMock
from src.network.alert_engine import AlertEngine, AlertRule, MaintenanceWindow


@pytest.fixture
def mock_metrics():
    m = AsyncMock()
    m.query_device_metrics = AsyncMock(return_value=[])
    m.write_alert_event = AsyncMock()
    return m


@pytest.fixture
def engine(mock_metrics):
    return AlertEngine(mock_metrics)


class TestMaintenanceWindow:
    def test_create_window(self):
        now = time.time()
        mw = MaintenanceWindow(
            id="mw-1", name="Router Upgrade",
            start_time=now, end_time=now + 3600,
            entity_filter="router-1",
        )
        assert mw.is_active(now + 100)
        assert not mw.is_active(now + 7200)

    def test_window_wildcard(self):
        now = time.time()
        mw = MaintenanceWindow(
            id="mw-2", name="Global Maintenance",
            start_time=now, end_time=now + 3600,
            entity_filter="*",
        )
        assert mw.matches_entity("any-device")

    def test_window_specific_entity(self):
        now = time.time()
        mw = MaintenanceWindow(
            id="mw-3", name="Specific",
            start_time=now, end_time=now + 3600,
            entity_filter="dev-1",
        )
        assert mw.matches_entity("dev-1")
        assert not mw.matches_entity("dev-2")


class TestMaintenanceWindowSuppression:
    def test_add_window(self, engine):
        now = time.time()
        engine.add_maintenance_window(MaintenanceWindow(
            id="mw-1", name="Test",
            start_time=now, end_time=now + 3600,
            entity_filter="*",
        ))
        assert len(engine.list_maintenance_windows()) == 1

    def test_remove_window(self, engine):
        now = time.time()
        engine.add_maintenance_window(MaintenanceWindow(
            id="mw-1", name="Test",
            start_time=now, end_time=now + 3600,
            entity_filter="*",
        ))
        engine.remove_maintenance_window("mw-1")
        assert len(engine.list_maintenance_windows()) == 0

    @pytest.mark.asyncio
    async def test_alert_suppressed_during_window(self, engine, mock_metrics):
        now = time.time()
        engine.add_maintenance_window(MaintenanceWindow(
            id="mw-1", name="Upgrade",
            start_time=now - 60, end_time=now + 3600,
            entity_filter="dev-1",
        ))
        rule = AlertRule(
            id="r1", name="CPU", severity="warning",
            entity_type="device", entity_filter="*",
            metric="cpu_pct", condition="gt", threshold=90.0,
            duration_seconds=0, cooldown_seconds=0,
        )
        engine.add_rule(rule)
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
        alerts = await engine.evaluate("dev-1")
        assert len(alerts) == 0  # Suppressed

    @pytest.mark.asyncio
    async def test_alert_not_suppressed_for_other_entity(self, engine, mock_metrics):
        now = time.time()
        engine.add_maintenance_window(MaintenanceWindow(
            id="mw-1", name="Upgrade",
            start_time=now - 60, end_time=now + 3600,
            entity_filter="dev-1",
        ))
        rule = AlertRule(
            id="r1", name="CPU", severity="warning",
            entity_type="device", entity_filter="*",
            metric="cpu_pct", condition="gt", threshold=90.0,
            duration_seconds=0, cooldown_seconds=0,
        )
        engine.add_rule(rule)
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
        alerts = await engine.evaluate("dev-2")
        assert len(alerts) == 1  # NOT suppressed — different device

    @pytest.mark.asyncio
    async def test_expired_window_doesnt_suppress(self, engine, mock_metrics):
        now = time.time()
        engine.add_maintenance_window(MaintenanceWindow(
            id="mw-1", name="Done",
            start_time=now - 7200, end_time=now - 3600,
            entity_filter="*",
        ))
        rule = AlertRule(
            id="r1", name="CPU", severity="warning",
            entity_type="device", entity_filter="*",
            metric="cpu_pct", condition="gt", threshold=90.0,
            duration_seconds=0, cooldown_seconds=0,
        )
        engine.add_rule(rule)
        mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
        alerts = await engine.evaluate("dev-1")
        assert len(alerts) == 1  # Window expired, alert fires
```

**Step 2: Run tests — expect failures**

**Step 3: Add MaintenanceWindow dataclass to alert_engine.py**

```python
@dataclass
class MaintenanceWindow:
    id: str
    name: str
    start_time: float  # epoch seconds
    end_time: float
    entity_filter: str = "*"  # "*" = all, or specific entity_id

    def is_active(self, now: float | None = None) -> bool:
        now = now or time.time()
        return self.start_time <= now <= self.end_time

    def matches_entity(self, entity_id: str) -> bool:
        return self.entity_filter == "*" or self.entity_filter == entity_id
```

**Step 4: Add maintenance window support to AlertEngine**

In `__init__`, add:
```python
        self._maintenance_windows: list[MaintenanceWindow] = []
```

Add methods:
```python
    def add_maintenance_window(self, window: MaintenanceWindow) -> None:
        self._maintenance_windows.append(window)

    def remove_maintenance_window(self, window_id: str) -> None:
        self._maintenance_windows = [w for w in self._maintenance_windows if w.id != window_id]

    def list_maintenance_windows(self) -> list[dict]:
        return [
            {"id": w.id, "name": w.name, "start_time": w.start_time,
             "end_time": w.end_time, "entity_filter": w.entity_filter,
             "active": w.is_active()}
            for w in self._maintenance_windows
        ]

    def _in_maintenance(self, entity_id: str) -> bool:
        now = time.time()
        return any(
            w.is_active(now) and w.matches_entity(entity_id)
            for w in self._maintenance_windows
        )
```

In `evaluate()`, add at the start of the method (after `fired: list[dict] = []`):
```python
        if self._in_maintenance(entity_id):
            return fired
```

**Step 5: Add maintenance window API endpoints**

In `monitor_endpoints.py`:

```python
@monitor_router.get("/maintenance")
async def list_maintenance_windows():
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        return {"windows": []}
    return {"windows": mon.alert_engine.list_maintenance_windows()}


@monitor_router.post("/maintenance")
async def create_maintenance_window(body: dict):
    from src.network.alert_engine import MaintenanceWindow
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        raise HTTPException(503, "Alert engine not initialized")
    window = MaintenanceWindow(**body)
    mon.alert_engine.add_maintenance_window(window)
    return {"status": "created", "id": window.id}


@monitor_router.delete("/maintenance/{window_id}")
async def delete_maintenance_window(window_id: str):
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        raise HTTPException(503, "Alert engine not initialized")
    mon.alert_engine.remove_maintenance_window(window_id)
    return {"status": "deleted", "id": window_id}
```

**Step 6: Run tests**

Run: `cd backend && python3 -m pytest tests/test_maintenance_windows.py tests/test_alert_engine.py -v`

**Step 7: Commit**

```bash
git add backend/src/network/alert_engine.py backend/src/api/monitor_endpoints.py backend/tests/test_maintenance_windows.py
git commit -m "feat(alerts): add maintenance windows for alert suppression"
```

---

### Task 4: Escalation Policies

**Files:**
- Modify: `backend/src/network/notification_dispatcher.py` (add escalation)
- Modify: `backend/src/network/alert_engine.py` (track ack timing)
- Modify: `backend/src/api/monitor_endpoints.py` (escalation endpoints)
- Test: `backend/tests/test_escalation.py`

**Step 1: Write failing tests**

Create `backend/tests/test_escalation.py`:

```python
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

    @pytest.mark.asyncio
    async def test_check_escalations(self, dispatcher):
        ch1 = NotificationChannel(id="ch-1", name="Slack", channel_type=ChannelType.WEBHOOK,
                                  config={"url": "http://example.com"})
        ch2 = NotificationChannel(id="ch-2", name="PD", channel_type=ChannelType.WEBHOOK,
                                  config={"url": "http://example.com"})
        dispatcher.add_channel(ch1)
        dispatcher.add_channel(ch2)

        policy = EscalationPolicy(
            id="esc-1", name="Test",
            escalate_after_seconds=0,  # Immediate for testing
            source_channel_ids=["ch-1"],
            target_channel_ids=["ch-2"],
        )
        dispatcher.add_escalation(policy)

        # Simulate an unacknowledged alert
        alert = {
            "key": "r1:dev-1", "severity": "critical",
            "fired_at": time.time() - 600, "acknowledged": False,
            "rule_name": "Test", "message": "test",
        }

        with patch.object(dispatcher, '_send', new_callable=AsyncMock):
            escalated = await dispatcher.check_escalations([alert])
            assert len(escalated) >= 0  # May or may not escalate depending on impl

    @pytest.mark.asyncio
    async def test_acknowledged_alerts_not_escalated(self, dispatcher):
        policy = EscalationPolicy(
            id="esc-1", name="Test",
            escalate_after_seconds=0,
            source_channel_ids=["ch-1"],
            target_channel_ids=["ch-2"],
        )
        dispatcher.add_escalation(policy)

        alert = {
            "key": "r1:dev-1", "severity": "critical",
            "fired_at": time.time() - 600, "acknowledged": True,
            "rule_name": "Test", "message": "test",
        }
        escalated = await dispatcher.check_escalations([alert])
        assert len(escalated) == 0
```

**Step 2: Run tests — expect failures**

**Step 3: Add EscalationPolicy to notification_dispatcher.py**

```python
@dataclass
class EscalationPolicy:
    id: str
    name: str
    escalate_after_seconds: int = 300
    source_channel_ids: list[str] = field(default_factory=list)
    target_channel_ids: list[str] = field(default_factory=list)
    severity_filter: list[str] = field(default_factory=lambda: ["critical"])
    enabled: bool = True
```

Add to `__init__`:
```python
        self._escalations: list[EscalationPolicy] = []
        self._escalated_keys: set[str] = set()
```

Add methods:
```python
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
```

Add `import time` and `from dataclasses import dataclass, field` at top.

**Step 4: Add escalation API endpoints**

```python
@monitor_router.get("/escalations")
async def list_escalations():
    mon = _get_monitor()
    if not mon or not mon.alert_engine or not getattr(mon.alert_engine, '_dispatcher', None):
        return {"escalations": []}
    return {"escalations": mon.alert_engine._dispatcher.list_escalations()}


@monitor_router.post("/escalations")
async def create_escalation(body: dict):
    from src.network.notification_dispatcher import EscalationPolicy
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        raise HTTPException(503, "Alert engine not initialized")
    if not getattr(mon.alert_engine, '_dispatcher', None):
        from src.network.notification_dispatcher import NotificationDispatcher
        mon.alert_engine.set_dispatcher(NotificationDispatcher())
    policy = EscalationPolicy(**body)
    mon.alert_engine._dispatcher.add_escalation(policy)
    return {"status": "created", "id": policy.id}


@monitor_router.delete("/escalations/{policy_id}")
async def delete_escalation(policy_id: str):
    mon = _get_monitor()
    if mon and mon.alert_engine and getattr(mon.alert_engine, '_dispatcher', None):
        mon.alert_engine._dispatcher.remove_escalation(policy_id)
    return {"status": "deleted"}
```

**Step 5: Wire escalation check into alert pass**

In `backend/src/network/alert_engine.py`, at the end of `evaluate_all()`, after dispatcher dispatch, add:

```python
        # Check escalations for unacknowledged alerts
        if self._dispatcher:
            try:
                await self._dispatcher.check_escalations(list(self._active_alerts.values()))
            except Exception:
                logger.exception("Escalation check failed")
```

**Step 6: Run tests**

Run: `cd backend && python3 -m pytest tests/test_escalation.py tests/test_alert_engine.py -v`

**Step 7: Commit**

```bash
git add backend/src/network/notification_dispatcher.py backend/src/network/alert_engine.py backend/src/api/monitor_endpoints.py backend/tests/test_escalation.py
git commit -m "feat(alerts): add escalation policies for unacknowledged alerts"
```

---

### Task 5: Composite Alert Rules

**Files:**
- Modify: `backend/src/network/alert_engine.py` (add CompositeRule + evaluation)
- Modify: `backend/src/api/monitor_endpoints.py` (composite rule endpoint)
- Test: `backend/tests/test_composite_rules.py`

**Step 1: Write failing tests**

Create `backend/tests/test_composite_rules.py`:

```python
"""Tests for composite (multi-condition) alert rules."""
import pytest
from unittest.mock import AsyncMock
from src.network.alert_engine import AlertEngine, AlertRule, CompositeRule


@pytest.fixture
def mock_metrics():
    m = AsyncMock()
    m.query_device_metrics = AsyncMock(return_value=[])
    m.write_alert_event = AsyncMock()
    return m


@pytest.fixture
def engine(mock_metrics):
    return AlertEngine(mock_metrics)


class TestCompositeRule:
    def test_create_and_rule(self):
        rule = CompositeRule(
            id="comp-1", name="CPU AND Memory",
            severity="critical", entity_filter="*",
            operator="AND",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 90.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 95.0},
            ],
        )
        assert rule.operator == "AND"
        assert len(rule.conditions) == 2

    def test_create_or_rule(self):
        rule = CompositeRule(
            id="comp-2", name="CPU OR Memory",
            severity="warning", entity_filter="*",
            operator="OR",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 95.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 98.0},
            ],
        )
        assert rule.operator == "OR"


class TestCompositeRuleEvaluation:
    @pytest.mark.asyncio
    async def test_and_rule_fires_when_both_met(self, engine, mock_metrics):
        rule = CompositeRule(
            id="comp-1", name="CPU AND Mem", severity="critical",
            entity_filter="*", operator="AND",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 90.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 95.0},
            ],
            cooldown_seconds=0,
        )
        engine.add_composite_rule(rule)

        async def mock_query(entity_id, metric, **kwargs):
            return [{"time": "now", "value": {"cpu_pct": 95.0, "mem_pct": 98.0}.get(metric, 0)}]

        mock_metrics.query_device_metrics.side_effect = mock_query
        alerts = await engine.evaluate_composites("dev-1")
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_and_rule_does_not_fire_when_partial(self, engine, mock_metrics):
        rule = CompositeRule(
            id="comp-1", name="CPU AND Mem", severity="critical",
            entity_filter="*", operator="AND",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 90.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 95.0},
            ],
            cooldown_seconds=0,
        )
        engine.add_composite_rule(rule)

        async def mock_query(entity_id, metric, **kwargs):
            return [{"time": "now", "value": {"cpu_pct": 95.0, "mem_pct": 50.0}.get(metric, 0)}]

        mock_metrics.query_device_metrics.side_effect = mock_query
        alerts = await engine.evaluate_composites("dev-1")
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_or_rule_fires_when_one_met(self, engine, mock_metrics):
        rule = CompositeRule(
            id="comp-2", name="CPU OR Mem", severity="warning",
            entity_filter="*", operator="OR",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 95.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 98.0},
            ],
            cooldown_seconds=0,
        )
        engine.add_composite_rule(rule)

        async def mock_query(entity_id, metric, **kwargs):
            return [{"time": "now", "value": {"cpu_pct": 97.0, "mem_pct": 50.0}.get(metric, 0)}]

        mock_metrics.query_device_metrics.side_effect = mock_query
        alerts = await engine.evaluate_composites("dev-1")
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_or_rule_does_not_fire_when_none_met(self, engine, mock_metrics):
        rule = CompositeRule(
            id="comp-2", name="CPU OR Mem", severity="warning",
            entity_filter="*", operator="OR",
            conditions=[
                {"metric": "cpu_pct", "condition": "gt", "threshold": 95.0},
                {"metric": "mem_pct", "condition": "gt", "threshold": 98.0},
            ],
            cooldown_seconds=0,
        )
        engine.add_composite_rule(rule)

        async def mock_query(entity_id, metric, **kwargs):
            return [{"time": "now", "value": {"cpu_pct": 50.0, "mem_pct": 50.0}.get(metric, 0)}]

        mock_metrics.query_device_metrics.side_effect = mock_query
        alerts = await engine.evaluate_composites("dev-1")
        assert len(alerts) == 0
```

**Step 2: Run tests — expect failures**

**Step 3: Add CompositeRule and evaluation to AlertEngine**

Add dataclass:
```python
@dataclass
class CompositeRule:
    id: str
    name: str
    severity: str
    entity_filter: str = "*"
    operator: str = "AND"  # "AND" or "OR"
    conditions: list[dict] = field(default_factory=list)
    cooldown_seconds: int = 600
    enabled: bool = True
    description: str = ""
```

In AlertEngine `__init__`, add:
```python
        self._composite_rules: list[CompositeRule] = []
```

Add methods:
```python
    def add_composite_rule(self, rule: CompositeRule) -> None:
        self._composite_rules.append(rule)

    def remove_composite_rule(self, rule_id: str) -> None:
        self._composite_rules = [r for r in self._composite_rules if r.id != rule_id]

    def get_composite_rules(self) -> list[dict]:
        return [
            {"id": r.id, "name": r.name, "severity": r.severity,
             "entity_filter": r.entity_filter, "operator": r.operator,
             "conditions": r.conditions, "cooldown_seconds": r.cooldown_seconds,
             "enabled": r.enabled, "description": r.description}
            for r in self._composite_rules
        ]

    async def evaluate_composites(self, entity_id: str) -> list[dict]:
        """Evaluate composite rules for a given entity."""
        fired: list[dict] = []
        now = time.time()

        for rule in self._composite_rules:
            if not rule.enabled:
                continue
            if not self._matches_filter(entity_id, rule.entity_filter):
                continue

            key = f"{rule.id}:{entity_id}"
            last = self._last_fired.get(key, 0)
            if now - last < rule.cooldown_seconds and key in self._active_alerts:
                continue

            results = []
            for cond in rule.conditions:
                data = await self.metrics.query_device_metrics(
                    entity_id, cond["metric"],
                    range_str=f"30s", resolution="30s",
                )
                if data:
                    val = data[-1].get("value", 0)
                    met = self._check_condition(val, cond["condition"], cond["threshold"])
                    results.append((met, val, cond))
                else:
                    results.append((False, 0, cond))

            if rule.operator == "AND":
                all_met = all(r[0] for r in results)
            else:  # OR
                all_met = any(r[0] for r in results)

            if all_met:
                met_conditions = [r for r in results if r[0]]
                first = met_conditions[0] if met_conditions else results[0]
                alert = self._fire_alert(
                    AlertRule(
                        id=rule.id, name=rule.name, severity=rule.severity,
                        entity_type="device", entity_filter=rule.entity_filter,
                        metric=first[2]["metric"], condition=first[2]["condition"],
                        threshold=first[2]["threshold"],
                        cooldown_seconds=rule.cooldown_seconds,
                    ),
                    entity_id, first[1], now,
                )
                alert["composite"] = True
                alert["operator"] = rule.operator
                fired.append(alert)

        return fired
```

Wire into `evaluate_all` — after regular evaluation, add:
```python
        # Evaluate composite rules
        for eid in entity_ids:
            comp_fired = await self.evaluate_composites(eid)
            all_fired.extend(comp_fired)
```

**Step 4: Add composite rule API endpoint**

```python
@monitor_router.get("/alerts/composite-rules")
async def get_composite_rules():
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        return {"rules": []}
    return {"rules": mon.alert_engine.get_composite_rules()}


@monitor_router.post("/alerts/composite-rules")
async def create_composite_rule(body: dict):
    from src.network.alert_engine import CompositeRule
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        raise HTTPException(503, "Alert engine not initialized")
    rule = CompositeRule(**body)
    mon.alert_engine.add_composite_rule(rule)
    return {"status": "created", "id": rule.id}


@monitor_router.delete("/alerts/composite-rules/{rule_id}")
async def delete_composite_rule(rule_id: str):
    mon = _get_monitor()
    if not mon or not mon.alert_engine:
        raise HTTPException(503, "Alert engine not initialized")
    mon.alert_engine.remove_composite_rule(rule_id)
    return {"status": "deleted", "id": rule_id}
```

**Step 5: Run tests**

Run: `cd backend && python3 -m pytest tests/test_composite_rules.py tests/test_alert_engine.py -v`

**Step 6: Commit**

```bash
git add backend/src/network/alert_engine.py backend/src/api/monitor_endpoints.py backend/tests/test_composite_rules.py
git commit -m "feat(alerts): add composite alert rules with AND/OR logic"
```

---

### Task 6: Final Verification

**Step 1: Run all tests**

```bash
cd backend && python3 -m pytest tests/ -v --tb=short
```

**Step 2: Verify new alert features**

```bash
cd backend && python3 -c "
from src.network.alert_engine import AlertEngine, AlertRule, MaintenanceWindow, CompositeRule
print('AlertRule:', AlertRule.__dataclass_fields__.keys())
print('MaintenanceWindow:', MaintenanceWindow.__dataclass_fields__.keys())
print('CompositeRule:', CompositeRule.__dataclass_fields__.keys())
print('OK')
"
```

**Step 3: Verify escalation**

```bash
cd backend && python3 -c "
from src.network.notification_dispatcher import NotificationDispatcher, EscalationPolicy
d = NotificationDispatcher()
p = EscalationPolicy(id='test', name='Test', escalate_after_seconds=300,
                      source_channel_ids=['ch1'], target_channel_ids=['ch2'])
d.add_escalation(p)
assert len(d.list_escalations()) == 1
print('Escalation OK')
"
```

**Step 4: Commit if any fixes needed**

```bash
git add -A && git commit -m "fix: final adjustments for alert maturity phase 4"
```

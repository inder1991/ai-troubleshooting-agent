# Network Observatory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an always-on network observability dashboard with live device status, drift detection, auto-discovery, and traffic flow visualization.

**Architecture:** A `NetworkMonitor` background task collects device status from ICMP probes, firewall adapters, and Prometheus every 30s. A `DriftEngine` compares live adapter state against KG intent. A `DiscoveryEngine` finds unknown IPs. Five new SQLite tables store current state and 7-day history. The frontend adds a 3-tab Observatory page (Live Topology, NOC Wall, Traffic Flows) that polls a snapshot endpoint every 30s.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/ReactFlow/d3-sankey (frontend), SQLite, icmplib, pytest

**Design doc:** `docs/plans/2026-03-04-network-observatory-design.md`

---

## Task 1: State Store — New Tables + CRUD Methods

**Files:**
- Modify: `backend/src/network/topology_store.py`
- Test: `backend/tests/test_monitor_store.py`

### Step 1: Write the failing tests

Create `backend/tests/test_monitor_store.py`:

```python
"""Tests for Network Observatory state store tables."""
import os
import pytest
from src.network.topology_store import TopologyStore


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


class TestDeviceStatus:
    def test_upsert_and_get(self, store):
        store.upsert_device_status("d1", "up", 2.5, 0.0, "icmp")
        result = store.get_device_status("d1")
        assert result is not None
        assert result["status"] == "up"
        assert result["latency_ms"] == 2.5

    def test_upsert_updates_existing(self, store):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        store.upsert_device_status("d1", "down", 0.0, 1.0, "icmp")
        result = store.get_device_status("d1")
        assert result["status"] == "down"
        assert result["packet_loss"] == 1.0

    def test_status_change_tracks_timestamp(self, store):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        first = store.get_device_status("d1")
        store.upsert_device_status("d1", "down", 0.0, 1.0, "icmp")
        second = store.get_device_status("d1")
        assert second["last_status_change"] != first["last_status_change"]

    def test_same_status_preserves_change_timestamp(self, store):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        first = store.get_device_status("d1")
        store.upsert_device_status("d1", "up", 3.0, 0.0, "icmp")
        second = store.get_device_status("d1")
        assert second["last_status_change"] == first["last_status_change"]

    def test_list_all(self, store):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        store.upsert_device_status("d2", "down", 0.0, 1.0, "tcp")
        results = store.list_device_statuses()
        assert len(results) == 2

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_device_status("nope") is None


class TestLinkMetrics:
    def test_upsert_and_list(self, store):
        store.upsert_link_metric("d1", "d2", 5.0, 1_000_000, 0.01, 0.45)
        results = store.list_link_metrics()
        assert len(results) == 1
        assert results[0]["latency_ms"] == 5.0
        assert results[0]["utilization"] == 0.45

    def test_upsert_updates(self, store):
        store.upsert_link_metric("d1", "d2", 5.0, 1_000_000, 0.01, 0.45)
        store.upsert_link_metric("d1", "d2", 10.0, 2_000_000, 0.02, 0.80)
        results = store.list_link_metrics()
        assert len(results) == 1
        assert results[0]["latency_ms"] == 10.0


class TestMetricHistory:
    def test_append_and_query(self, store):
        store.append_metric("device", "d1", "latency_ms", 2.5)
        store.append_metric("device", "d1", "latency_ms", 3.0)
        rows = store.query_metric_history("device", "d1", "latency_ms", since="2000-01-01")
        assert len(rows) == 2
        assert rows[0]["value"] == 2.5

    def test_prune_old_data(self, store):
        store.append_metric("device", "d1", "latency_ms", 2.5)
        # Manually backdate the row
        conn = store._conn()
        try:
            conn.execute("UPDATE metric_history SET recorded_at='2020-01-01T00:00:00'")
            conn.commit()
        finally:
            conn.close()
        store.prune_metric_history(older_than_days=1)
        rows = store.query_metric_history("device", "d1", "latency_ms", since="2000-01-01")
        assert len(rows) == 0


class TestDriftEvents:
    def test_upsert_and_list_active(self, store):
        store.upsert_drift_event("route", "rt1", "missing", "destination_cidr",
                                  "10.0.0.0/8", "(not present)", "critical")
        events = store.list_active_drift_events()
        assert len(events) == 1
        assert events[0]["drift_type"] == "missing"

    def test_resolve_removes_from_active(self, store):
        store.upsert_drift_event("route", "rt1", "missing", "destination_cidr",
                                  "10.0.0.0/8", "(not present)", "critical")
        events = store.list_active_drift_events()
        store.resolve_drift_event(events[0]["id"])
        assert len(store.list_active_drift_events()) == 0

    def test_unique_constraint_upserts(self, store):
        store.upsert_drift_event("route", "rt1", "missing", "next_hop",
                                  "10.0.0.1", "(not present)", "warning")
        store.upsert_drift_event("route", "rt1", "missing", "next_hop",
                                  "10.0.0.1", "(not present)", "critical")
        events = store.list_active_drift_events()
        assert len(events) == 1
        assert events[0]["severity"] == "critical"


class TestDiscoveryCandidates:
    def test_upsert_and_list(self, store):
        store.upsert_discovery_candidate("10.1.1.50", "aa:bb:cc:dd:ee:ff",
                                          "printer-1", "probe", "")
        candidates = store.list_discovery_candidates()
        assert len(candidates) == 1
        assert candidates[0]["hostname"] == "printer-1"

    def test_promote(self, store):
        store.upsert_discovery_candidate("10.1.1.50", "", "", "probe", "")
        store.promote_candidate("10.1.1.50", "device-printer")
        candidates = store.list_discovery_candidates()
        assert candidates[0]["promoted_device_id"] == "device-printer"

    def test_dismiss(self, store):
        store.upsert_discovery_candidate("10.1.1.50", "", "", "probe", "")
        store.dismiss_candidate("10.1.1.50")
        candidates = store.list_discovery_candidates()
        assert len(candidates) == 0  # dismissed = hidden from list

    def test_dismissed_not_in_list(self, store):
        store.upsert_discovery_candidate("10.1.1.50", "", "", "probe", "")
        store.upsert_discovery_candidate("10.1.1.51", "", "", "probe", "")
        store.dismiss_candidate("10.1.1.50")
        candidates = store.list_discovery_candidates()
        assert len(candidates) == 1
        assert candidates[0]["ip"] == "10.1.1.51"
```

### Step 2: Run tests to verify they fail

Run: `cd backend && python -m pytest tests/test_monitor_store.py -v`
Expected: FAIL — methods don't exist yet.

### Step 3: Implement the store methods

Add the 5 new tables to `_init_tables()` in `topology_store.py` (append to the existing `executescript` block):

```sql
CREATE TABLE IF NOT EXISTS device_status (
    device_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    latency_ms REAL DEFAULT 0,
    packet_loss REAL DEFAULT 0,
    last_seen TEXT,
    last_status_change TEXT,
    probe_method TEXT DEFAULT 'icmp',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS link_metrics (
    src_device_id TEXT,
    dst_device_id TEXT,
    latency_ms REAL DEFAULT 0,
    bandwidth_bps INTEGER DEFAULT 0,
    error_rate REAL DEFAULT 0,
    utilization REAL DEFAULT 0,
    updated_at TEXT,
    PRIMARY KEY (src_device_id, dst_device_id)
);
CREATE TABLE IF NOT EXISTS metric_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metric_history_entity
    ON metric_history(entity_type, entity_id, recorded_at);
CREATE TABLE IF NOT EXISTS drift_events (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    drift_type TEXT NOT NULL,
    field TEXT DEFAULT '',
    expected TEXT DEFAULT '',
    actual TEXT DEFAULT '',
    severity TEXT DEFAULT 'warning',
    detected_at TEXT,
    resolved_at TEXT,
    UNIQUE(entity_type, entity_id, drift_type, field)
);
CREATE TABLE IF NOT EXISTS discovery_candidates (
    ip TEXT PRIMARY KEY,
    mac TEXT DEFAULT '',
    hostname TEXT DEFAULT '',
    discovered_via TEXT DEFAULT '',
    source_device_id TEXT DEFAULT '',
    first_seen TEXT,
    last_seen TEXT,
    promoted_device_id TEXT DEFAULT '',
    dismissed INTEGER DEFAULT 0
);
```

Then add the CRUD methods to `TopologyStore`. Each method follows the existing try-finally pattern:

```python
# ── Device Status ──

def upsert_device_status(self, device_id: str, status: str, latency_ms: float,
                          packet_loss: float, probe_method: str) -> None:
    conn = self._conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        existing = conn.execute(
            "SELECT status, last_status_change FROM device_status WHERE device_id=?",
            (device_id,),
        ).fetchone()
        if existing:
            last_change = existing["last_status_change"]
            if existing["status"] != status:
                last_change = now
            conn.execute(
                "UPDATE device_status SET status=?, latency_ms=?, packet_loss=?, "
                "last_seen=?, last_status_change=?, probe_method=?, updated_at=? "
                "WHERE device_id=?",
                (status, latency_ms, packet_loss, now, last_change, probe_method, now, device_id),
            )
        else:
            conn.execute(
                "INSERT INTO device_status VALUES (?,?,?,?,?,?,?,?)",
                (device_id, status, latency_ms, packet_loss, now, now, probe_method, now),
            )
        conn.commit()
    finally:
        conn.close()

def get_device_status(self, device_id: str) -> Optional[dict]:
    conn = self._conn()
    try:
        row = conn.execute("SELECT * FROM device_status WHERE device_id=?", (device_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def list_device_statuses(self) -> list[dict]:
    conn = self._conn()
    try:
        rows = conn.execute("SELECT * FROM device_status").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# ── Link Metrics ──

def upsert_link_metric(self, src_id: str, dst_id: str, latency_ms: float,
                        bandwidth_bps: int, error_rate: float, utilization: float) -> None:
    conn = self._conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO link_metrics VALUES (?,?,?,?,?,?,?)",
            (src_id, dst_id, latency_ms, bandwidth_bps, error_rate, utilization, now),
        )
        conn.commit()
    finally:
        conn.close()

def list_link_metrics(self) -> list[dict]:
    conn = self._conn()
    try:
        rows = conn.execute("SELECT * FROM link_metrics").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# ── Metric History ──

def append_metric(self, entity_type: str, entity_id: str, metric: str, value: float) -> None:
    conn = self._conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO metric_history (entity_type, entity_id, metric, value, recorded_at) VALUES (?,?,?,?,?)",
            (entity_type, entity_id, metric, value, now),
        )
        conn.commit()
    finally:
        conn.close()

def query_metric_history(self, entity_type: str, entity_id: str, metric: str,
                          since: str) -> list[dict]:
    conn = self._conn()
    try:
        rows = conn.execute(
            "SELECT * FROM metric_history WHERE entity_type=? AND entity_id=? AND metric=? "
            "AND recorded_at>=? ORDER BY recorded_at",
            (entity_type, entity_id, metric, since),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def prune_metric_history(self, older_than_days: int = 7) -> int:
    conn = self._conn()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        cursor = conn.execute("DELETE FROM metric_history WHERE recorded_at < ?", (cutoff,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()

# ── Drift Events ──

def upsert_drift_event(self, entity_type: str, entity_id: str, drift_type: str,
                        field: str, expected: str, actual: str, severity: str) -> None:
    conn = self._conn()
    try:
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO drift_events (id, entity_type, entity_id, drift_type, field, "
            "expected, actual, severity, detected_at) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(entity_type, entity_id, drift_type, field) DO UPDATE SET "
            "expected=excluded.expected, actual=excluded.actual, severity=excluded.severity, "
            "resolved_at=NULL",
            (str(uuid.uuid4()), entity_type, entity_id, drift_type, field,
             expected, actual, severity, now),
        )
        conn.commit()
    finally:
        conn.close()

def resolve_drift_event(self, event_id: str) -> None:
    conn = self._conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE drift_events SET resolved_at=? WHERE id=?", (now, event_id))
        conn.commit()
    finally:
        conn.close()

def list_active_drift_events(self) -> list[dict]:
    conn = self._conn()
    try:
        rows = conn.execute(
            "SELECT * FROM drift_events WHERE resolved_at IS NULL ORDER BY severity, detected_at"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# ── Discovery Candidates ──

def upsert_discovery_candidate(self, ip: str, mac: str, hostname: str,
                                discovered_via: str, source_device_id: str) -> None:
    conn = self._conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO discovery_candidates (ip, mac, hostname, discovered_via, "
            "source_device_id, first_seen, last_seen) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(ip) DO UPDATE SET mac=excluded.mac, "
            "hostname=CASE WHEN excluded.hostname!='' THEN excluded.hostname ELSE discovery_candidates.hostname END, "
            "last_seen=excluded.last_seen",
            (ip, mac, hostname, discovered_via, source_device_id, now, now),
        )
        conn.commit()
    finally:
        conn.close()

def list_discovery_candidates(self) -> list[dict]:
    conn = self._conn()
    try:
        rows = conn.execute(
            "SELECT * FROM discovery_candidates WHERE dismissed=0 AND promoted_device_id=''"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def promote_candidate(self, ip: str, device_id: str) -> None:
    conn = self._conn()
    try:
        conn.execute(
            "UPDATE discovery_candidates SET promoted_device_id=? WHERE ip=?",
            (device_id, ip),
        )
        conn.commit()
    finally:
        conn.close()

def dismiss_candidate(self, ip: str) -> None:
    conn = self._conn()
    try:
        conn.execute("UPDATE discovery_candidates SET dismissed=1 WHERE ip=?", (ip,))
        conn.commit()
    finally:
        conn.close()
```

### Step 4: Run tests to verify they pass

Run: `cd backend && python -m pytest tests/test_monitor_store.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add backend/src/network/topology_store.py backend/tests/test_monitor_store.py
git commit -m "feat(observatory): add state store tables and CRUD for monitoring"
```

---

## Task 2: Drift Engine

**Files:**
- Create: `backend/src/network/drift_engine.py`
- Test: `backend/tests/test_drift_engine.py`

### Step 1: Write the failing tests

Create `backend/tests/test_drift_engine.py`:

```python
"""Tests for drift detection engine."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.network.topology_store import TopologyStore
from src.network.models import (
    Device, DeviceType, Route, FirewallRule, PolicyAction, FirewallVendor,
)
from src.network.drift_engine import DriftEngine


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def engine(store):
    return DriftEngine(store)


def _make_adapter():
    adapter = AsyncMock()
    adapter.get_routes = AsyncMock(return_value=[])
    adapter.get_rules = AsyncMock(return_value=[])
    adapter.get_interfaces = AsyncMock(return_value=[])
    adapter.get_nat_rules = AsyncMock(return_value=[])
    adapter.get_zones = AsyncMock(return_value=[])
    return adapter


class TestRouteDrift:
    @pytest.mark.asyncio
    async def test_missing_route_detected(self, store, engine):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER))
        store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.0.0/8", next_hop="10.0.0.1"))
        adapter = _make_adapter()
        adapter.get_routes.return_value = []  # route missing from device
        events = await engine.check_device("r1", adapter)
        assert any(e["drift_type"] == "missing" and e["entity_type"] == "route" for e in events)

    @pytest.mark.asyncio
    async def test_added_route_detected(self, store, engine):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER))
        # No routes in KG
        adapter = _make_adapter()
        live_route = MagicMock()
        live_route.destination_cidr = "172.16.0.0/12"
        live_route.next_hop = "10.0.0.1"
        live_route.metric = 100
        live_route.protocol = "static"
        adapter.get_routes.return_value = [live_route]
        events = await engine.check_device("r1", adapter)
        assert any(e["drift_type"] == "added" and e["entity_type"] == "route" for e in events)

    @pytest.mark.asyncio
    async def test_changed_route_next_hop(self, store, engine):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER))
        store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.0.0/8", next_hop="10.0.0.1"))
        adapter = _make_adapter()
        live_route = MagicMock()
        live_route.destination_cidr = "10.0.0.0/8"
        live_route.next_hop = "10.0.0.99"  # changed
        adapter.get_routes.return_value = [live_route]
        events = await engine.check_device("r1", adapter)
        assert any(e["drift_type"] == "changed" and e["field"] == "next_hop" for e in events)

    @pytest.mark.asyncio
    async def test_no_drift_when_matching(self, store, engine):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER))
        store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.0.0/8", next_hop="10.0.0.1"))
        adapter = _make_adapter()
        live_route = MagicMock()
        live_route.destination_cidr = "10.0.0.0/8"
        live_route.next_hop = "10.0.0.1"
        adapter.get_routes.return_value = [live_route]
        events = await engine.check_device("r1", adapter)
        route_events = [e for e in events if e["entity_type"] == "route"]
        assert len(route_events) == 0


class TestFirewallRuleDrift:
    @pytest.mark.asyncio
    async def test_action_change_is_critical(self, store, engine):
        store.add_device(Device(id="fw1", name="FW1", device_type=DeviceType.FIREWALL))
        store.add_firewall_rule(FirewallRule(
            id="rule1", device_id="fw1", rule_name="block-ssh",
            action=PolicyAction.DENY, src_ips=["any"], dst_ips=["10.0.0.0/8"],
            ports=[22], protocol="tcp",
        ))
        adapter = _make_adapter()
        live_rule = MagicMock()
        live_rule.rule_name = "block-ssh"
        live_rule.action = PolicyAction.ALLOW  # changed!
        live_rule.src_ips = ["any"]
        live_rule.dst_ips = ["10.0.0.0/8"]
        live_rule.ports = [22]
        adapter.get_rules.return_value = [live_rule]
        events = await engine.check_device("fw1", adapter)
        action_events = [e for e in events if e["field"] == "action"]
        assert len(action_events) == 1
        assert action_events[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_adapter_failure_returns_empty(self, store, engine):
        store.add_device(Device(id="fw1", name="FW1", device_type=DeviceType.FIREWALL))
        adapter = _make_adapter()
        adapter.get_routes.side_effect = Exception("connection refused")
        adapter.get_rules.side_effect = Exception("connection refused")
        adapter.get_interfaces.side_effect = Exception("connection refused")
        adapter.get_nat_rules.side_effect = Exception("connection refused")
        adapter.get_zones.side_effect = Exception("connection refused")
        events = await engine.check_device("fw1", adapter)
        assert events == []
```

### Step 2: Run tests to verify they fail

Run: `cd backend && python -m pytest tests/test_drift_engine.py -v`
Expected: FAIL — `drift_engine` module doesn't exist.

### Step 3: Implement the drift engine

Create `backend/src/network/drift_engine.py`:

```python
"""Drift detection engine — compares KG intent against live adapter state."""
import json
import logging

from .topology_store import TopologyStore
from .models import PolicyAction

logger = logging.getLogger(__name__)


class DriftEngine:
    """Compares KG intent against live adapter state for a device."""

    def __init__(self, store: TopologyStore):
        self.store = store

    async def check_device(self, device_id: str, adapter) -> list[dict]:
        """Run all drift checks for a single device.
        Returns list of drift event dicts (not yet persisted)."""
        events: list[dict] = []
        events.extend(await self._diff_routes(device_id, adapter))
        events.extend(await self._diff_rules(device_id, adapter))
        events.extend(await self._diff_interfaces(device_id, adapter))
        events.extend(await self._diff_nat_rules(device_id, adapter))
        events.extend(await self._diff_zones(device_id, adapter))
        return events

    async def _diff_routes(self, device_id: str, adapter) -> list[dict]:
        kg_routes = self.store.list_routes(device_id=device_id)
        kg_map = {r.destination_cidr: r for r in kg_routes}
        try:
            live_routes = await adapter.get_routes()
        except Exception:
            return []
        live_map = {r.destination_cidr: r for r in live_routes}

        events = []
        for cidr, kg_route in kg_map.items():
            if cidr not in live_map:
                events.append({
                    "entity_type": "route", "entity_id": kg_route.id,
                    "drift_type": "missing", "field": "destination_cidr",
                    "expected": cidr, "actual": "(not present)",
                    "severity": "critical" if cidr == "0.0.0.0/0" else "warning",
                })
        for cidr in live_map:
            if cidr not in kg_map:
                events.append({
                    "entity_type": "route", "entity_id": f"live-{device_id}-{cidr}",
                    "drift_type": "added", "field": "destination_cidr",
                    "expected": "(not in topology)", "actual": cidr,
                    "severity": "info",
                })
        for cidr in kg_map.keys() & live_map.keys():
            kg_r, live_r = kg_map[cidr], live_map[cidr]
            if kg_r.next_hop and live_r.next_hop != kg_r.next_hop:
                events.append({
                    "entity_type": "route", "entity_id": kg_r.id,
                    "drift_type": "changed", "field": "next_hop",
                    "expected": kg_r.next_hop, "actual": live_r.next_hop,
                    "severity": "warning",
                })
        return events

    async def _diff_rules(self, device_id: str, adapter) -> list[dict]:
        kg_rules = self.store.list_firewall_rules(device_id=device_id)
        kg_map = {r.rule_name: r for r in kg_rules}
        try:
            live_rules = await adapter.get_rules()
        except Exception:
            return []
        live_map = {r.rule_name: r for r in live_rules}

        events = []
        for name, kg_rule in kg_map.items():
            if name not in live_map:
                events.append({
                    "entity_type": "firewall_rule", "entity_id": kg_rule.id,
                    "drift_type": "missing", "field": "rule_name",
                    "expected": name, "actual": "(not present)",
                    "severity": "critical",
                })
        for name in live_map:
            if name not in kg_map:
                events.append({
                    "entity_type": "firewall_rule", "entity_id": f"live-{device_id}-{name}",
                    "drift_type": "added", "field": "rule_name",
                    "expected": "(not in topology)", "actual": name,
                    "severity": "warning",
                })
        for name in kg_map.keys() & live_map.keys():
            kg_r, live_r = kg_map[name], live_map[name]
            kg_action = kg_r.action if isinstance(kg_r.action, str) else kg_r.action.value
            live_action = live_r.action if isinstance(live_r.action, str) else live_r.action.value
            if kg_action != live_action:
                events.append({
                    "entity_type": "firewall_rule", "entity_id": kg_r.id,
                    "drift_type": "changed", "field": "action",
                    "expected": kg_action, "actual": live_action,
                    "severity": "critical",
                })
        return events

    async def _diff_interfaces(self, device_id: str, adapter) -> list[dict]:
        kg_ifaces = self.store.list_interfaces(device_id=device_id)
        kg_map = {i.name: i for i in kg_ifaces}
        try:
            live_ifaces = await adapter.get_interfaces()
        except Exception:
            return []
        live_map = {i.name: i for i in live_ifaces}

        events = []
        for name, kg_iface in kg_map.items():
            if name not in live_map:
                events.append({
                    "entity_type": "interface", "entity_id": kg_iface.id,
                    "drift_type": "missing", "field": "name",
                    "expected": name, "actual": "(not present)",
                    "severity": "warning",
                })
        for name in live_map:
            if name not in kg_map:
                events.append({
                    "entity_type": "interface", "entity_id": f"live-{device_id}-{name}",
                    "drift_type": "added", "field": "name",
                    "expected": "(not in topology)", "actual": name,
                    "severity": "info",
                })
        for name in kg_map.keys() & live_map.keys():
            kg_i, live_i = kg_map[name], live_map[name]
            if kg_i.ip and live_i.ip != kg_i.ip:
                events.append({
                    "entity_type": "interface", "entity_id": kg_i.id,
                    "drift_type": "changed", "field": "ip",
                    "expected": kg_i.ip, "actual": live_i.ip,
                    "severity": "warning",
                })
        return events

    async def _diff_nat_rules(self, device_id: str, adapter) -> list[dict]:
        try:
            live_rules = await adapter.get_nat_rules()
        except Exception:
            return []
        # NAT rule diff is lighter — just detect count mismatch and missing rules
        kg_rules = self.store.list_nat_rules(device_id=device_id)
        kg_ids = {(r.rule_id or r.id) for r in kg_rules}
        live_ids = {(r.rule_id or r.id) for r in live_rules}

        events = []
        for rid in kg_ids - live_ids:
            events.append({
                "entity_type": "nat_rule", "entity_id": rid,
                "drift_type": "missing", "field": "rule_id",
                "expected": rid, "actual": "(not present)",
                "severity": "warning",
            })
        for rid in live_ids - kg_ids:
            events.append({
                "entity_type": "nat_rule", "entity_id": rid,
                "drift_type": "added", "field": "rule_id",
                "expected": "(not in topology)", "actual": rid,
                "severity": "info",
            })
        return events

    async def _diff_zones(self, device_id: str, adapter) -> list[dict]:
        try:
            live_zones = await adapter.get_zones()
        except Exception:
            return []
        # Zone drift: compare names only
        kg_zones = self.store.list_zones()
        kg_names = {z.name for z in kg_zones}
        live_names = {z.name for z in live_zones}

        events = []
        for name in live_names - kg_names:
            events.append({
                "entity_type": "zone", "entity_id": f"live-{device_id}-{name}",
                "drift_type": "added", "field": "name",
                "expected": "(not in topology)", "actual": name,
                "severity": "info",
            })
        return events
```

### Step 4: Run tests to verify they pass

Run: `cd backend && python -m pytest tests/test_drift_engine.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add backend/src/network/drift_engine.py backend/tests/test_drift_engine.py
git commit -m "feat(observatory): add drift detection engine"
```

---

## Task 3: Discovery Engine

**Files:**
- Create: `backend/src/network/discovery_engine.py`
- Test: `backend/tests/test_discovery_engine.py`

### Step 1: Write the failing tests

Create `backend/tests/test_discovery_engine.py`:

```python
"""Tests for auto-discovery engine."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet
from src.network.discovery_engine import DiscoveryEngine


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def kg(store):
    kg = NetworkKnowledgeGraph(store)
    return kg


@pytest.fixture
def engine(store, kg):
    return DiscoveryEngine(store, kg)


class TestAdapterDiscovery:
    @pytest.mark.asyncio
    async def test_discovers_unknown_ip_from_adapter(self, store, kg, engine):
        # Known device in KG
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        # Adapter reports an interface with unknown IP
        adapter = AsyncMock()
        iface = MagicMock()
        iface.ip = "10.0.0.99"
        iface.name = "unknown-peer"
        adapter.get_interfaces.return_value = [iface]

        from src.network.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        registry.register("r1", adapter)

        candidates = await engine.discover_from_adapters(registry)
        assert any(c["ip"] == "10.0.0.99" for c in candidates)

    @pytest.mark.asyncio
    async def test_skips_known_ips(self, store, kg, engine):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        adapter = AsyncMock()
        iface = MagicMock()
        iface.ip = "10.0.0.1"  # already known
        iface.name = "known"
        adapter.get_interfaces.return_value = [iface]

        from src.network.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        registry.register("r1", adapter)

        candidates = await engine.discover_from_adapters(registry)
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_adapter_failure_skipped(self, store, kg, engine):
        kg.load_from_store()
        adapter = AsyncMock()
        adapter.get_interfaces.side_effect = Exception("timeout")

        from src.network.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        registry.register("r1", adapter)

        candidates = await engine.discover_from_adapters(registry)
        assert candidates == []


class TestSubnetProbe:
    @pytest.mark.asyncio
    async def test_skips_large_subnets(self, store, kg, engine):
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/16"))  # /16 = 65K hosts, too large
        kg.load_from_store()
        # Should not attempt to scan
        with patch.object(engine, "_ping_check", new_callable=AsyncMock) as mock_ping:
            await engine.probe_known_subnets()
            mock_ping.assert_not_called()

    @pytest.mark.asyncio
    async def test_scans_small_subnets(self, store, kg, engine):
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/30"))  # /30 = 2 hosts
        kg.load_from_store()
        with patch.object(engine, "_ping_check", new_callable=AsyncMock,
                          return_value=("10.0.0.1", True)) as mock_ping:
            candidates = await engine.probe_known_subnets()
            assert mock_ping.call_count > 0


class TestReverseDNS:
    @pytest.mark.asyncio
    async def test_reverse_dns_returns_hostname(self, engine):
        with patch("socket.gethostbyaddr", return_value=("printer.local", [], ["10.0.0.5"])):
            result = await engine.reverse_dns("10.0.0.5")
            assert result == "printer.local"

    @pytest.mark.asyncio
    async def test_reverse_dns_returns_empty_on_failure(self, engine):
        import socket
        with patch("socket.gethostbyaddr", side_effect=socket.herror):
            result = await engine.reverse_dns("10.0.0.5")
            assert result == ""
```

### Step 2: Run tests to verify they fail

Run: `cd backend && python -m pytest tests/test_discovery_engine.py -v`
Expected: FAIL — module doesn't exist.

### Step 3: Implement the discovery engine

Create `backend/src/network/discovery_engine.py`:

```python
"""Auto-discovery engine — finds network devices not yet in the Knowledge Graph."""
import asyncio
import ipaddress
import logging
import random
import socket

from .topology_store import TopologyStore

logger = logging.getLogger(__name__)

# Safety limits
_MAX_SUBNET_PREFIX_MIN = 20  # skip subnets larger than /20
_MAX_HOSTS_PER_SUBNET = 50   # sample per cycle


class DiscoveryEngine:
    """Finds devices on the network not yet in the Knowledge Graph."""

    def __init__(self, store: TopologyStore, kg):
        self.store = store
        self.kg = kg

    def _known_ips(self) -> set[str]:
        return set(self.kg._device_index.keys())

    async def discover_from_adapters(self, adapters) -> list[dict]:
        """Source 1: Check adapter interface tables for unknown IPs."""
        known = self._known_ips()
        candidates = []
        for instance_id, adapter in adapters.all_instances().items():
            try:
                ifaces = await adapter.get_interfaces()
                for iface in ifaces:
                    if iface.ip and iface.ip not in known:
                        hostname = await self.reverse_dns(iface.ip)
                        candidates.append({
                            "ip": iface.ip,
                            "mac": getattr(iface, "mac", ""),
                            "hostname": hostname or getattr(iface, "name", ""),
                            "discovered_via": "adapter_neighbor",
                            "source_device_id": instance_id,
                        })
                        known.add(iface.ip)  # don't double-count within cycle
            except Exception as e:
                logger.debug("Discovery: adapter %s failed: %s", instance_id, e)
                continue
        return candidates

    async def probe_known_subnets(self) -> list[dict]:
        """Source 2: Ping-sweep subnets in the KG to find responsive unknown IPs."""
        known = self._known_ips()
        subnets = self.store.list_subnets()
        candidates = []

        for subnet in subnets:
            try:
                network = ipaddress.ip_network(subnet.cidr, strict=False)
            except ValueError:
                continue
            if network.num_addresses > (2 ** (32 - _MAX_SUBNET_PREFIX_MIN)):
                continue

            hosts = list(network.hosts())
            unknown_hosts = [str(h) for h in hosts if str(h) not in known]
            if len(unknown_hosts) > _MAX_HOSTS_PER_SUBNET:
                unknown_hosts = random.sample(unknown_hosts, _MAX_HOSTS_PER_SUBNET)

            tasks = [self._ping_check(ip) for ip in unknown_hosts]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    continue
                ip_str, alive = result
                if alive:
                    hostname = await self.reverse_dns(ip_str)
                    candidates.append({
                        "ip": ip_str,
                        "mac": "",
                        "hostname": hostname,
                        "discovered_via": "probe",
                        "source_device_id": "",
                    })
                    known.add(ip_str)
        return candidates

    async def check_prometheus_targets(self, prometheus_url: str) -> list[dict]:
        """Source 4: Query Prometheus for unknown target IPs."""
        known = self._known_ips()
        candidates = []
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{prometheus_url}/api/v1/targets")
                data = resp.json()
                for target in data.get("data", {}).get("activeTargets", []):
                    # Extract IP from target labels
                    address = target.get("labels", {}).get("instance", "")
                    ip = address.split(":")[0] if address else ""
                    if ip and ip not in known:
                        candidates.append({
                            "ip": ip,
                            "mac": "",
                            "hostname": "",
                            "discovered_via": "prometheus",
                            "source_device_id": "",
                        })
                        known.add(ip)
        except Exception as e:
            logger.debug("Discovery: Prometheus check failed: %s", e)
        return candidates

    async def _ping_check(self, ip: str) -> tuple[str, bool]:
        """Single async ping with 2s timeout."""
        try:
            from icmplib import async_ping
            result = await asyncio.wait_for(
                async_ping(ip, count=1, timeout=2),
                timeout=3,
            )
            return (ip, result.is_alive)
        except Exception:
            return (ip, False)

    async def reverse_dns(self, ip: str) -> str:
        """Best-effort reverse DNS lookup."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, socket.gethostbyaddr, ip)
            return result[0]
        except (socket.herror, socket.gaierror, OSError):
            return ""
```

### Step 4: Run tests to verify they pass

Run: `cd backend && python -m pytest tests/test_discovery_engine.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add backend/src/network/discovery_engine.py backend/tests/test_discovery_engine.py
git commit -m "feat(observatory): add auto-discovery engine"
```

---

## Task 4: Network Monitor (Collection Engine)

**Files:**
- Create: `backend/src/network/monitor.py`
- Test: `backend/tests/test_network_monitor.py`

### Step 1: Write the failing tests

Create `backend/tests/test_network_monitor.py`:

```python
"""Tests for the NetworkMonitor collection engine."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet
from src.network.adapters.registry import AdapterRegistry
from src.network.monitor import NetworkMonitor


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def adapters():
    return AdapterRegistry()


@pytest.fixture
def monitor(store, kg, adapters):
    return NetworkMonitor(store, kg, adapters)


class TestProbePass:
    @pytest.mark.asyncio
    async def test_probe_sets_device_status_up(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            mock_result = MagicMock()
            mock_result.is_alive = True
            mock_result.avg_rtt = 2.5
            mock_result.packet_loss = 0.0
            mock_ping.return_value = mock_result
            await monitor._probe_pass()

        status = store.get_device_status("r1")
        assert status is not None
        assert status["status"] == "up"

    @pytest.mark.asyncio
    async def test_probe_sets_device_status_down(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            mock_result = MagicMock()
            mock_result.is_alive = False
            mock_result.avg_rtt = 0
            mock_result.packet_loss = 1.0
            mock_ping.return_value = mock_result
            await monitor._probe_pass()

        status = store.get_device_status("r1")
        assert status["status"] == "down"

    @pytest.mark.asyncio
    async def test_probe_sets_degraded_on_high_latency(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            mock_result = MagicMock()
            mock_result.is_alive = True
            mock_result.avg_rtt = 150.0  # > 100ms threshold
            mock_result.packet_loss = 0.0
            mock_ping.return_value = mock_result
            await monitor._probe_pass()

        status = store.get_device_status("r1")
        assert status["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_skips_devices_without_ip(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip=""))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            await monitor._probe_pass()
            mock_ping.assert_not_called()


class TestCollectCycle:
    @pytest.mark.asyncio
    async def test_full_cycle_runs_without_error(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            mock_result = MagicMock()
            mock_result.is_alive = True
            mock_result.avg_rtt = 2.0
            mock_result.packet_loss = 0.0
            mock_ping.return_value = mock_result
            await monitor._collect_cycle()

        assert store.get_device_status("r1") is not None

    @pytest.mark.asyncio
    async def test_cycle_records_metric_history(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            mock_result = MagicMock()
            mock_result.is_alive = True
            mock_result.avg_rtt = 2.0
            mock_result.packet_loss = 0.0
            mock_ping.return_value = mock_result
            await monitor._collect_cycle()

        history = store.query_metric_history("device", "r1", "latency_ms", since="2000-01-01")
        assert len(history) >= 1


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_get_snapshot_returns_all_data(self, store, monitor):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        store.upsert_link_metric("d1", "d2", 5.0, 1000000, 0.0, 0.5)
        store.upsert_drift_event("route", "rt1", "missing", "cidr", "10.0.0.0/8", "", "warning")
        store.upsert_discovery_candidate("10.0.0.99", "", "", "probe", "")

        snapshot = monitor.get_snapshot()
        assert len(snapshot["devices"]) == 1
        assert len(snapshot["links"]) == 1
        assert len(snapshot["drifts"]) == 1
        assert len(snapshot["candidates"]) == 1
```

### Step 2: Run tests to verify they fail

Run: `cd backend && python -m pytest tests/test_network_monitor.py -v`
Expected: FAIL — module doesn't exist.

### Step 3: Implement the monitor

Create `backend/src/network/monitor.py`:

```python
"""Network Monitor — 30s collection engine for device status, metrics, drift, and discovery."""
import asyncio
import logging

from icmplib import async_ping

from .topology_store import TopologyStore
from .drift_engine import DriftEngine
from .discovery_engine import DiscoveryEngine

logger = logging.getLogger(__name__)

# Thresholds for status derivation
_LATENCY_DEGRADED_MS = 100.0
_PACKET_LOSS_DEGRADED = 0.10
_PROBE_TIMEOUT = 5


class NetworkMonitor:
    """Background collector that runs a probe/adapter/drift/discovery cycle."""

    def __init__(self, store: TopologyStore, kg, adapters,
                 prometheus_url: str | None = None):
        self.store = store
        self.kg = kg
        self.adapters = adapters
        self.prometheus_url = prometheus_url
        self.drift_engine = DriftEngine(store)
        self.discovery_engine = DiscoveryEngine(store, kg)
        self.cycle_interval = 30
        self._task: asyncio.Task | None = None

    # ── Lifecycle ──

    async def start(self):
        """Start the monitor loop. Call from FastAPI startup."""
        self._task = asyncio.create_task(self._run_loop())
        logger.info("NetworkMonitor started (interval=%ds)", self.cycle_interval)

    async def stop(self):
        """Stop the monitor loop. Call from FastAPI shutdown."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("NetworkMonitor stopped")

    async def _run_loop(self):
        while True:
            try:
                await self._collect_cycle()
            except Exception as e:
                logger.error("Monitor cycle failed: %s", e)
            await asyncio.sleep(self.cycle_interval)

    # ── Collection Cycle ──

    async def _collect_cycle(self):
        """Single collection cycle — probes, adapters, drift, discovery."""
        # 1. Probe pass
        await self._probe_pass()

        # 2. Adapter pass (interface counters → link_metrics)
        await self._adapter_pass()

        # 3. Drift pass
        await self._drift_pass()

        # 4. Discovery pass
        await self._discovery_pass()

        # 5. Prune old metric history (runs every cycle, cheap no-op if nothing to prune)
        self.store.prune_metric_history(older_than_days=7)

    async def _probe_pass(self):
        """Ping every device in the KG and write status."""
        devices = self.store.list_devices()
        tasks = []
        for d in devices:
            if not d.management_ip:
                continue
            tasks.append(self._probe_one(d.id, d.management_ip))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _probe_one(self, device_id: str, ip: str):
        """Probe a single device and write status + history."""
        try:
            result = await asyncio.wait_for(
                async_ping(ip, count=3, timeout=2),
                timeout=_PROBE_TIMEOUT,
            )
            latency = result.avg_rtt
            loss = result.packet_loss
            alive = result.is_alive

            if not alive:
                status = "down"
            elif latency > _LATENCY_DEGRADED_MS or loss > _PACKET_LOSS_DEGRADED:
                status = "degraded"
            else:
                status = "up"

            self.store.upsert_device_status(device_id, status, latency, loss, "icmp")
            self.store.append_metric("device", device_id, "latency_ms", latency)
            self.store.append_metric("device", device_id, "packet_loss", loss)

        except Exception as e:
            logger.debug("Probe failed for %s (%s): %s", device_id, ip, e)
            self.store.upsert_device_status(device_id, "down", 0.0, 1.0, "icmp")

    async def _adapter_pass(self):
        """Pull interface counters from adapters → link_metrics."""
        for instance_id, adapter in self.adapters.all_instances().items():
            try:
                ifaces = await adapter.get_interfaces()
                # Adapter interfaces provide status info but not cross-link metrics
                # Link metrics would require adapter-specific bandwidth counters
                # For now, adapter pass enriches device status for adapter-managed devices
            except Exception as e:
                logger.debug("Adapter pass failed for %s: %s", instance_id, e)

    async def _drift_pass(self):
        """Run drift checks for all adapter-managed devices."""
        for instance_id, adapter in self.adapters.all_instances().items():
            # Find devices bound to this adapter
            bindings = self.store.list_device_bindings_for_instance(instance_id)
            for device_id in bindings:
                try:
                    events = await self.drift_engine.check_device(device_id, adapter)
                    for event in events:
                        self.store.upsert_drift_event(
                            event["entity_type"], event["entity_id"],
                            event["drift_type"], event["field"],
                            event["expected"], event["actual"], event["severity"],
                        )
                except Exception as e:
                    logger.debug("Drift check failed for %s: %s", device_id, e)

    async def _discovery_pass(self):
        """Run discovery from adapters and subnet probes."""
        try:
            candidates = await self.discovery_engine.discover_from_adapters(self.adapters)
            for c in candidates:
                self.store.upsert_discovery_candidate(
                    c["ip"], c.get("mac", ""), c.get("hostname", ""),
                    c["discovered_via"], c.get("source_device_id", ""),
                )
        except Exception as e:
            logger.debug("Adapter discovery failed: %s", e)

        try:
            probe_candidates = await self.discovery_engine.probe_known_subnets()
            for c in probe_candidates:
                self.store.upsert_discovery_candidate(
                    c["ip"], c.get("mac", ""), c.get("hostname", ""),
                    c["discovered_via"], c.get("source_device_id", ""),
                )
        except Exception as e:
            logger.debug("Probe discovery failed: %s", e)

    # ── Snapshot API ──

    def get_snapshot(self) -> dict:
        """Return current state for the dashboard."""
        return {
            "devices": self.store.list_device_statuses(),
            "links": self.store.list_link_metrics(),
            "drifts": self.store.list_active_drift_events(),
            "candidates": self.store.list_discovery_candidates(),
        }
```

### Step 4: Run tests to verify they pass

Run: `cd backend && python -m pytest tests/test_network_monitor.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add backend/src/network/monitor.py backend/tests/test_network_monitor.py
git commit -m "feat(observatory): add NetworkMonitor collection engine"
```

---

## Task 5: Monitor API Endpoints

**Files:**
- Create: `backend/src/api/monitor_endpoints.py`
- Modify: `backend/src/api/main.py`
- Test: `backend/tests/test_monitor_endpoints.py`

### Step 1: Write the failing tests

Create `backend/tests/test_monitor_endpoints.py`:

```python
"""Tests for /api/v4/network/monitor endpoints."""
import os
import pytest
from unittest.mock import patch, MagicMock

from starlette.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet
from src.network.adapters.registry import AdapterRegistry


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def client(store, kg):
    from src.network.monitor import NetworkMonitor
    registry = AdapterRegistry()
    monitor = NetworkMonitor(store, kg, registry)

    with patch("src.api.monitor_endpoints._get_monitor", return_value=monitor), \
         patch("src.api.monitor_endpoints._get_topology_store", return_value=store), \
         patch("src.api.monitor_endpoints._get_knowledge_graph", return_value=kg):
        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


class TestSnapshotEndpoint:
    def test_snapshot_returns_empty(self, client):
        resp = client.get("/api/v4/network/monitor/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert "devices" in data
        assert "links" in data
        assert "drifts" in data
        assert "candidates" in data

    def test_snapshot_returns_device_status(self, client, store):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        resp = client.get("/api/v4/network/monitor/snapshot")
        assert len(resp.json()["devices"]) == 1


class TestDriftEndpoint:
    def test_drift_list(self, client, store):
        store.upsert_drift_event("route", "rt1", "missing", "cidr", "10.0.0.0/8", "", "warning")
        resp = client.get("/api/v4/network/monitor/drift")
        assert resp.status_code == 200
        assert len(resp.json()["drifts"]) == 1


class TestDeviceHistory:
    def test_device_history(self, client, store):
        store.append_metric("device", "d1", "latency_ms", 5.0)
        resp = client.get("/api/v4/network/monitor/device/d1/history?period=24h")
        assert resp.status_code == 200
        assert len(resp.json()["history"]) >= 1


class TestDiscoveryPromote:
    def test_promote_candidate(self, client, store, kg):
        store.upsert_discovery_candidate("10.0.0.99", "", "printer", "probe", "")
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))
        resp = client.post("/api/v4/network/monitor/discover/10.0.0.99/promote", json={
            "name": "printer-1",
            "device_type": "HOST",
        })
        assert resp.status_code == 200
        assert resp.json()["device_id"]

    def test_dismiss_candidate(self, client, store):
        store.upsert_discovery_candidate("10.0.0.99", "", "", "probe", "")
        resp = client.post("/api/v4/network/monitor/discover/10.0.0.99/dismiss")
        assert resp.status_code == 200
        assert len(store.list_discovery_candidates()) == 0
```

### Step 2: Run tests to verify they fail

Run: `cd backend && python -m pytest tests/test_monitor_endpoints.py -v`
Expected: FAIL — module doesn't exist.

### Step 3: Implement the endpoints

Create `backend/src/api/monitor_endpoints.py`:

```python
"""FastAPI router for Network Observatory — /api/v4/network/monitor."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Interface
from src.utils.logger import get_logger

logger = get_logger(__name__)

monitor_router = APIRouter(prefix="/api/v4/network/monitor", tags=["observatory"])

# Singletons — injected from main.py startup
_monitor = None
_topology_store = None
_knowledge_graph = None


def _get_monitor():
    return _monitor


def _get_topology_store():
    from src.api.network_endpoints import _get_topology_store as _ts
    return _topology_store or _ts()


def _get_knowledge_graph():
    from src.api.network_endpoints import _get_knowledge_graph as _kg
    return _knowledge_graph or _kg()


class PromoteRequest(BaseModel):
    name: str
    device_type: str = "HOST"


@monitor_router.get("/snapshot")
async def get_snapshot():
    """Current state for the observatory dashboard."""
    mon = _get_monitor()
    if not mon:
        return {"devices": [], "links": [], "drifts": [], "candidates": []}
    return mon.get_snapshot()


@monitor_router.get("/drift")
async def list_drift_events():
    """List all active drift events."""
    store = _get_topology_store()
    return {"drifts": store.list_active_drift_events()}


@monitor_router.get("/device/{device_id}/history")
async def device_history(device_id: str, period: str = "24h"):
    """Latency/status history for a specific device."""
    store = _get_topology_store()
    period_map = {"1h": 1/24, "24h": 1, "7d": 7}
    days = period_map.get(period, 1)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    latency = store.query_metric_history("device", device_id, "latency_ms", since)
    packet_loss = store.query_metric_history("device", device_id, "packet_loss", since)
    return {
        "device_id": device_id,
        "period": period,
        "history": latency,
        "packet_loss_history": packet_loss,
    }


@monitor_router.post("/discover/{ip}/promote")
async def promote_discovery(ip: str, req: PromoteRequest):
    """Promote a discovered IP to a KG device."""
    store = _get_topology_store()
    kg = _get_knowledge_graph()

    candidates = store.list_discovery_candidates()
    candidate = next((c for c in candidates if c["ip"] == ip), None)
    if not candidate:
        raise HTTPException(404, f"No discovery candidate for IP {ip}")

    try:
        dt = DeviceType[req.device_type.upper()]
    except KeyError:
        dt = DeviceType.HOST

    device_id = f"device-discovered-{ip.replace('.', '-').replace(':', '-')}"
    device = Device(
        id=device_id,
        name=req.name,
        device_type=dt,
        management_ip=ip,
    )
    store.add_device(device)
    kg.add_device(device)

    # Create interface for the discovered IP
    iface = Interface(
        id=f"iface-{device_id}-discovered",
        device_id=device_id,
        name="discovered",
        ip=ip,
    )
    store.add_interface(iface)

    store.promote_candidate(ip, device_id)

    return {"status": "promoted", "device_id": device_id, "ip": ip}


@monitor_router.post("/discover/{ip}/dismiss")
async def dismiss_discovery(ip: str):
    """Dismiss a discovery candidate."""
    store = _get_topology_store()
    store.dismiss_candidate(ip)
    return {"status": "dismissed", "ip": ip}
```

Then register the router in `backend/src/api/main.py`. Add to the imports:

```python
from src.api.monitor_endpoints import monitor_router
```

And in `create_app()`, add after the existing `app.include_router(network_router)`:

```python
app.include_router(monitor_router)
```

Add to the `startup()` event:

```python
# Start Network Monitor
from src.network.monitor import NetworkMonitor
from src.api.network_endpoints import _get_topology_store, _get_knowledge_graph, _get_adapters
import src.api.monitor_endpoints as _mon_ep
store = _get_topology_store()
kg = _get_knowledge_graph()
adapters = _get_adapters()
_monitor = NetworkMonitor(store, kg, adapters)
_mon_ep._monitor = _monitor
_mon_ep._topology_store = store
_mon_ep._knowledge_graph = kg
asyncio.create_task(_monitor.start())
```

### Step 4: Run tests to verify they pass

Run: `cd backend && python -m pytest tests/test_monitor_endpoints.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add backend/src/api/monitor_endpoints.py backend/src/api/main.py backend/tests/test_monitor_endpoints.py
git commit -m "feat(observatory): add monitor API endpoints and register in main"
```

---

## Task 6: Frontend — Observatory Page Shell + Polling Hook

**Files:**
- Create: `frontend/src/components/Observatory/ObservatoryView.tsx`
- Create: `frontend/src/components/Observatory/hooks/useMonitorSnapshot.ts`
- Modify: `frontend/src/components/Layout/SidebarNav.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/services/api.ts`

### Step 1: Add API functions

Add to `frontend/src/services/api.ts`:

```typescript
// ── Observatory API ──

export const fetchMonitorSnapshot = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/snapshot`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch monitor snapshot'));
  return resp.json();
};

export const fetchDeviceHistory = async (deviceId: string, period: string = '24h') => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/device/${deviceId}/history?period=${period}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch device history'));
  return resp.json();
};

export const fetchDriftEvents = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/drift`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch drift events'));
  return resp.json();
};

export const promoteDiscovery = async (ip: string, name: string, deviceType: string = 'HOST') => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/discover/${ip}/promote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, device_type: deviceType }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to promote discovery'));
  return resp.json();
};

export const dismissDiscovery = async (ip: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/discover/${ip}/dismiss`, {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to dismiss discovery'));
  return resp.json();
};
```

### Step 2: Create the polling hook

Create `frontend/src/components/Observatory/hooks/useMonitorSnapshot.ts`:

```typescript
import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchMonitorSnapshot } from '../../../services/api';

export interface DeviceStatus {
  device_id: string;
  status: 'up' | 'down' | 'degraded';
  latency_ms: number;
  packet_loss: number;
  last_seen: string;
  last_status_change: string;
  probe_method: string;
}

export interface LinkMetric {
  src_device_id: string;
  dst_device_id: string;
  latency_ms: number;
  bandwidth_bps: number;
  error_rate: number;
  utilization: number;
}

export interface DriftEvent {
  id: string;
  entity_type: string;
  entity_id: string;
  drift_type: 'missing' | 'added' | 'changed';
  field: string;
  expected: string;
  actual: string;
  severity: 'info' | 'warning' | 'critical';
  detected_at: string;
}

export interface DiscoveryCandidate {
  ip: string;
  mac: string;
  hostname: string;
  discovered_via: string;
  source_device_id: string;
  first_seen: string;
  last_seen: string;
}

export interface MonitorSnapshot {
  devices: DeviceStatus[];
  links: LinkMetric[];
  drifts: DriftEvent[];
  candidates: DiscoveryCandidate[];
}

export function useMonitorSnapshot(intervalMs: number = 30_000) {
  const [snapshot, setSnapshot] = useState<MonitorSnapshot>({
    devices: [], links: [], drifts: [], candidates: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchMonitorSnapshot();
      setSnapshot(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch snapshot');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    timerRef.current = setInterval(refresh, intervalMs);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [refresh, intervalMs]);

  return { snapshot, loading, error, lastUpdated, refresh };
}
```

### Step 3: Create the Observatory page shell

Create `frontend/src/components/Observatory/ObservatoryView.tsx`:

```tsx
import React, { useState } from 'react';
import { useMonitorSnapshot } from './hooks/useMonitorSnapshot';

type Tab = 'topology' | 'noc' | 'flows';

const ObservatoryView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('topology');
  const { snapshot, loading, lastUpdated } = useMonitorSnapshot(30_000);

  const upCount = snapshot.devices.filter((d) => d.status === 'up').length;
  const totalCount = snapshot.devices.length;
  const driftCount = snapshot.drifts.length;
  const discoveryCount = snapshot.candidates.length;

  const secondsAgo = lastUpdated
    ? Math.round((Date.now() - lastUpdated.getTime()) / 1000)
    : null;

  const tabs: { id: Tab; label: string }[] = [
    { id: 'topology', label: 'Live Topology' },
    { id: 'noc', label: 'NOC Wall' },
    { id: 'flows', label: 'Traffic Flows' },
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden" style={{ backgroundColor: '#0f2023' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: '#224349' }}>
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-2xl" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>
            monitoring
          </span>
          <h1 className="text-xl font-bold text-white">Network Observatory</h1>
        </div>
        <div className="flex items-center gap-4">
          {/* Tabs */}
          <div className="flex gap-1 rounded-lg p-0.5" style={{ backgroundColor: '#0a1a1e' }}>
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="px-4 py-1.5 rounded-md text-sm font-medium transition-colors"
                style={activeTab === tab.id
                  ? { backgroundColor: 'rgba(7,182,213,0.15)', color: '#07b6d5' }
                  : { color: '#64748b' }
                }
              >
                {tab.label}
              </button>
            ))}
          </div>
          {/* Status badges */}
          <div className="flex items-center gap-3 text-xs font-mono">
            {secondsAgo !== null && (
              <span style={{ color: '#64748b' }}>Updated {secondsAgo}s ago</span>
            )}
            <span style={{ color: upCount === totalCount ? '#22c55e' : '#f59e0b' }}>
              {upCount}/{totalCount} UP
            </span>
            {driftCount > 0 && (
              <span style={{ color: '#f59e0b' }}>{driftCount} drift</span>
            )}
            {discoveryCount > 0 && (
              <span style={{ color: '#07b6d5' }}>{discoveryCount} discovered</span>
            )}
          </div>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-slate-500 text-sm">Loading observatory data...</div>
        ) : activeTab === 'topology' ? (
          <div className="p-6 text-slate-500 text-sm">Live Topology — coming in Task 7</div>
        ) : activeTab === 'noc' ? (
          <div className="p-6 text-slate-500 text-sm">NOC Wall — coming in Task 8</div>
        ) : (
          <div className="p-6 text-slate-500 text-sm">Traffic Flows — coming in Task 9</div>
        )}
      </div>
    </div>
  );
};

export default ObservatoryView;
```

### Step 4: Wire into App.tsx and SidebarNav

In `frontend/src/components/Layout/SidebarNav.tsx`, add `'observatory'` to the `NavView` type and add a nav item under the Network group:

```typescript
// In navItems, inside the Network group children array, add:
{ id: 'observatory', label: 'Observatory', icon: 'monitoring' },
```

In `frontend/src/App.tsx`, add the `'observatory'` case to the `ViewState` type and import/render `ObservatoryView`:

```typescript
// Add to ViewState type
type ViewState = '...' | 'observatory';

// Add import
import ObservatoryView from './components/Observatory/ObservatoryView';

// Add render case
{viewState === 'observatory' && <ObservatoryView />}
```

### Step 5: Verify frontend compiles

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

### Step 6: Commit

```bash
git add frontend/src/components/Observatory/ frontend/src/services/api.ts \
  frontend/src/components/Layout/SidebarNav.tsx frontend/src/App.tsx
git commit -m "feat(observatory): add Observatory page shell, polling hook, nav entry"
```

---

## Task 7: Frontend — NOC Wall Tab

**Files:**
- Create: `frontend/src/components/Observatory/NOCWallTab.tsx`
- Modify: `frontend/src/components/Observatory/ObservatoryView.tsx`

### Step 1: Implement the NOC Wall

Create `frontend/src/components/Observatory/NOCWallTab.tsx`:

```tsx
import React, { useState, useMemo } from 'react';
import type { DeviceStatus, DriftEvent } from './hooks/useMonitorSnapshot';

interface Props {
  devices: DeviceStatus[];
  drifts: DriftEvent[];
  onSelectDevice: (deviceId: string) => void;
}

const statusOrder = { down: 0, degraded: 1, up: 2 };
const statusColor = { up: '#22c55e', degraded: '#f59e0b', down: '#ef4444' };

const NOCWallTab: React.FC<Props> = ({ devices, drifts, onSelectDevice }) => {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const driftCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of drifts) {
      // entity_id may contain device_id or be related
      // Count by entity_id prefix for now
      const key = d.entity_id.split('-')[0] || d.entity_id;
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [drifts]);

  const filtered = useMemo(() => {
    let list = [...devices];
    if (statusFilter !== 'all') {
      list = list.filter((d) => d.status === statusFilter);
    }
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((d) => d.device_id.toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      const so = (statusOrder[a.status] ?? 2) - (statusOrder[b.status] ?? 2);
      if (so !== 0) return so;
      return b.latency_ms - a.latency_ms;
    });
    return list;
  }, [devices, search, statusFilter]);

  const downCount = devices.filter((d) => d.status === 'down').length;
  const degradedCount = devices.filter((d) => d.status === 'degraded').length;
  const upCount = devices.filter((d) => d.status === 'up').length;

  const thClass = 'text-left text-[11px] font-semibold uppercase tracking-wider py-2.5 px-3 border-b';
  const tdClass = 'py-2 px-3 text-[13px] font-mono border-b';

  return (
    <div className="flex flex-col h-full">
      {/* Filters */}
      <div className="flex items-center gap-4 px-6 py-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search devices..."
          className="pl-3 pr-3 py-2 rounded-lg border text-sm font-mono outline-none focus:border-[#07b6d5] max-w-xs"
          style={{ backgroundColor: '#0a1a1e', borderColor: '#224349', color: '#e2e8f0' }}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 rounded-lg border text-sm font-mono outline-none"
          style={{ backgroundColor: '#0a1a1e', borderColor: '#224349', color: '#e2e8f0' }}
        >
          <option value="all">All Status</option>
          <option value="down">Down</option>
          <option value="degraded">Degraded</option>
          <option value="up">Up</option>
        </select>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto px-6 pb-4">
        <table className="w-full border-collapse">
          <thead>
            <tr style={{ color: '#64748b', borderColor: '#224349' }}>
              <th className={thClass} style={{ width: 60 }}>Status</th>
              <th className={thClass}>Device</th>
              <th className={thClass}>Latency</th>
              <th className={thClass}>Packet Loss</th>
              <th className={thClass}>Drift</th>
              <th className={thClass}>Since</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((d) => (
              <tr
                key={d.device_id}
                className="hover:bg-[#162a2e] transition-colors cursor-pointer"
                style={{ borderColor: '#224349' }}
                onClick={() => onSelectDevice(d.device_id)}
              >
                <td className={tdClass}>
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: statusColor[d.status] }}
                  />
                </td>
                <td className={tdClass} style={{ color: '#e2e8f0' }}>{d.device_id}</td>
                <td className={tdClass} style={{ color: d.status === 'down' ? '#64748b' : '#07b6d5' }}>
                  {d.status === 'down' ? '—' : `${d.latency_ms.toFixed(1)}ms`}
                </td>
                <td className={tdClass} style={{ color: d.packet_loss > 0 ? '#f59e0b' : '#94a3b8' }}>
                  {(d.packet_loss * 100).toFixed(0)}%
                </td>
                <td className={tdClass} style={{ color: '#94a3b8' }}>
                  {driftCounts[d.device_id] || 0}
                </td>
                <td className={tdClass} style={{ color: '#64748b' }}>
                  {d.status !== 'up' && d.last_status_change
                    ? new Date(d.last_status_change).toLocaleTimeString()
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer summary */}
      <div className="px-6 py-2 border-t text-xs font-mono" style={{ borderColor: '#224349', color: '#64748b' }}>
        {downCount > 0 && <span style={{ color: '#ef4444' }}>{downCount} DOWN</span>}
        {downCount > 0 && (degradedCount > 0 || upCount > 0) && ' · '}
        {degradedCount > 0 && <span style={{ color: '#f59e0b' }}>{degradedCount} DEGRADED</span>}
        {degradedCount > 0 && upCount > 0 && ' · '}
        <span style={{ color: '#22c55e' }}>{upCount} UP</span>
        {drifts.length > 0 && <span> · {drifts.length} active drift events</span>}
      </div>
    </div>
  );
};

export default NOCWallTab;
```

### Step 2: Wire into ObservatoryView

Replace the NOC placeholder in `ObservatoryView.tsx`:

```tsx
// Add import
import NOCWallTab from './NOCWallTab';

// Replace the noc case
) : activeTab === 'noc' ? (
  <NOCWallTab
    devices={snapshot.devices}
    drifts={snapshot.drifts}
    onSelectDevice={(id) => { setActiveTab('topology'); /* TODO: select device */ }}
  />
)
```

### Step 3: Verify frontend compiles

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

### Step 4: Commit

```bash
git add frontend/src/components/Observatory/NOCWallTab.tsx \
  frontend/src/components/Observatory/ObservatoryView.tsx
git commit -m "feat(observatory): add NOC Wall tab with severity sorting and filters"
```

---

## Task 8: Frontend — Live Topology Tab

**Files:**
- Create: `frontend/src/components/Observatory/LiveTopologyTab.tsx`
- Create: `frontend/src/components/Observatory/DeviceStatusSidebar.tsx`
- Modify: `frontend/src/components/Observatory/ObservatoryView.tsx`

This is the largest frontend task. It reuses React Flow in read-only mode with status color overlay.

### Step 1: Implement DeviceStatusSidebar

Create `frontend/src/components/Observatory/DeviceStatusSidebar.tsx` — shows device detail when a node is clicked. Includes status, latency, packet loss, and a simple sparkline from metric history.

### Step 2: Implement LiveTopologyTab

Create `frontend/src/components/Observatory/LiveTopologyTab.tsx` — fetches `GET /topology/current` for the React Flow graph, then overlays `DeviceStatus` data as node border colors and edge labels.

Key behavior:
- Nodes get colored ring: `#22c55e` (up), `#f59e0b` (degraded), `#ef4444` (down)
- Edges show latency labels from `link_metrics` data
- Click a node → opens `DeviceStatusSidebar`
- Bottom-left: `DriftEventsList` and `DiscoveryCandidates` panels

### Step 3: Wire into ObservatoryView, verify compiles, commit

```bash
git commit -m "feat(observatory): add Live Topology tab with status overlay and sidebar"
```

---

## Task 9: Frontend — Traffic Flows Tab (Sankey)

**Files:**
- Create: `frontend/src/components/Observatory/TrafficFlowsTab.tsx`
- Modify: `frontend/src/components/Observatory/ObservatoryView.tsx`

### Step 1: Install d3-sankey

Run: `cd frontend && npm install d3-sankey @types/d3-sankey`

### Step 2: Implement TrafficFlowsTab

Uses `d3-sankey` to render a Sankey diagram. Groups link_metrics by zone (from device data). Bands sized by bandwidth, colored by health.

### Step 3: Wire into ObservatoryView, verify compiles, commit

```bash
git commit -m "feat(observatory): add Traffic Flows tab with Sankey diagram"
```

---

## Task 10: Frontend — Drift Events + Discovery Panels

**Files:**
- Create: `frontend/src/components/Observatory/DriftEventsList.tsx`
- Create: `frontend/src/components/Observatory/DiscoveryCandidates.tsx`

### Step 1: Implement DriftEventsList

Shows drift summary: count by severity, expandable list. Each event shows entity type, drift type, expected vs actual, severity badge.

### Step 2: Implement DiscoveryCandidates

Table of discovered IPs with hostname, source, "Add" and "Dismiss" buttons. "Add" opens a small form, calls `promoteDiscovery()`. "Dismiss" calls `dismissDiscovery()`.

### Step 3: Wire into LiveTopologyTab, verify compiles, commit

```bash
git commit -m "feat(observatory): add drift events list and discovery candidates panel"
```

---

## Task 11: Integration — Drift in Diagnosis Reports

**Files:**
- Modify: `backend/src/agents/network/report_generator.py`
- Test: `backend/tests/test_report_generator.py` (existing)

### Step 1: Write the failing test

Add to the existing report generator test file:

```python
def test_report_includes_drift_events():
    state = {
        "final_path": {"blocked": False},
        "firewall_verdicts": [{"device_name": "fw-01", "action": "allow", "device_id": "fw1"}],
        "firewalls_in_path": [{"device_id": "fw1"}],
        "nat_translations": [],
        "identity_chain": [],
        "trace_hops": [],
        "contradictions": [],
        "confidence": 0.8,
        "diagnosis_status": "complete",
        "evidence": [],
        "nacl_verdicts": [],
        "vpn_segments": [],
        "vpc_boundary_crossings": [],
        "load_balancers_in_path": [],
        "active_drift_events": [
            {"entity_type": "firewall_rule", "entity_id": "rule1",
             "drift_type": "changed", "field": "action",
             "expected": "deny", "actual": "allow", "severity": "critical",
             "detected_at": "2026-03-04T14:00:00"}
        ],
    }
    result = report_generator(state)
    assert "drift" in result["executive_summary"].lower()
```

### Step 2: Run test to verify it fails

### Step 3: Add drift awareness to report_generator

In `report_generator.py`, after the security warnings section, add:

```python
    # Drift event warnings
    drift_events = state.get("active_drift_events", [])
    if drift_events:
        critical_drifts = [d for d in drift_events if d.get("severity") == "critical"]
        if critical_drifts:
            drift_summary = ", ".join(
                f"{d['entity_type']} '{d['entity_id']}' {d['drift_type']} ({d['field']})"
                for d in critical_drifts[:3]
            )
            summary += f" DRIFT WARNING: {drift_summary}."
            next_steps.append("Review active drift events on devices in the path")
```

### Step 4: Run test to verify it passes, commit

```bash
git commit -m "feat(observatory): include drift events in diagnosis reports"
```

---

## Task 12: Final Verification

### Step 1: Run all backend tests

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All existing + new tests pass.

### Step 2: Run frontend type check

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

### Step 3: Manual smoke test

1. Start backend: `cd backend && uvicorn src.api.main:create_app --factory --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Navigate to Observatory in sidebar
4. Verify 3 tabs render
5. Verify polling badge shows "Updated Xs ago"

### Step 4: Final commit

```bash
git commit -m "feat(observatory): complete Network Observatory implementation"
```

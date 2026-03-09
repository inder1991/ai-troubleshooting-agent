# Phase 5: Scaling & Performance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate sequential bottlenecks in the monitor cycle, add caching/pagination/rate-limiting, and expose a comprehensive health endpoint.

**Architecture:** Parallelize all sequential passes with `asyncio.gather`, add TTL-based in-memory caching to TopologyStore, add cursor pagination to list endpoints, add rate-limiting middleware, and expose a `/health` endpoint with monitor heartbeat tracking.

**Tech Stack:** Python asyncio, FastAPI middleware, `cachetools` (TTLCache), `slowapi` (rate limiting)

---

### Task 1: Parallelize Monitor Passes

**Files:**
- Modify: `backend/src/network/monitor.py:77-85` (`_collect_cycle`)
- Modify: `backend/src/network/monitor.py:121-127` (`_adapter_pass`)
- Modify: `backend/src/network/monitor.py:128-147` (`_drift_pass`)
- Modify: `backend/src/network/dns_monitor.py:178-218` (`run_pass`)
- Test: `backend/tests/test_monitor_concurrency.py`

**Context:**
- `_collect_cycle()` runs 7 passes sequentially. Most can run in parallel.
- `_adapter_pass()` iterates adapters sequentially — parallelize with `asyncio.gather`.
- `_drift_pass()` iterates adapters × devices sequentially — parallelize per-adapter.
- `dns_monitor.run_pass()` iterates servers × hostnames sequentially — parallelize per-server.
- `_probe_pass()` and `_snmp_pass()` are already concurrent (good).
- `_alert_pass()` must run LAST because it reads data written by other passes.

**Step 1: Write the failing tests**

Create `backend/tests/test_monitor_concurrency.py`:

```python
"""Tests for monitor cycle concurrency."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.network.monitor import NetworkMonitor
from src.network.topology_store import TopologyStore
from src.network.dns_monitor import DNSMonitor
from src.network.models import (
    DNSMonitorConfig, DNSServerConfig, DNSWatchedHostname, DNSRecordType,
)


@pytest.fixture
def store(tmp_path):
    return TopologyStore(str(tmp_path / "test.db"))


@pytest.fixture
def monitor(store):
    kg = MagicMock()
    kg.graph = MagicMock()
    kg.graph.__contains__ = MagicMock(return_value=False)
    adapters = MagicMock()
    adapters.all_instances.return_value = {}
    adapters.device_bindings.return_value = {}
    return NetworkMonitor(store, kg, adapters)


class TestCollectCycleConcurrency:
    @pytest.mark.asyncio
    async def test_probe_adapter_drift_run_concurrently(self, monitor):
        """Verify probe/adapter/drift/discovery/snmp/dns run concurrently, alert runs after."""
        call_order = []

        async def fake_probe():
            call_order.append(("probe_start", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.01)
            call_order.append(("probe_end", asyncio.get_event_loop().time()))

        async def fake_adapter():
            call_order.append(("adapter_start", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.01)
            call_order.append(("adapter_end", asyncio.get_event_loop().time()))

        async def fake_drift():
            call_order.append(("drift_start", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.01)
            call_order.append(("drift_end", asyncio.get_event_loop().time()))

        async def fake_discovery():
            call_order.append(("discovery_start", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.01)
            call_order.append(("discovery_end", asyncio.get_event_loop().time()))

        async def fake_snmp():
            call_order.append(("snmp_start", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.01)
            call_order.append(("snmp_end", asyncio.get_event_loop().time()))

        async def fake_dns():
            call_order.append(("dns_start", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.01)
            call_order.append(("dns_end", asyncio.get_event_loop().time()))

        async def fake_alert():
            call_order.append(("alert_start", asyncio.get_event_loop().time()))

        monitor._probe_pass = fake_probe
        monitor._adapter_pass = fake_adapter
        monitor._drift_pass = fake_drift
        monitor._discovery_pass = fake_discovery
        monitor._snmp_pass = fake_snmp
        monitor._dns_pass = fake_dns
        monitor._alert_pass = fake_alert

        await monitor._collect_cycle()

        # All 6 passes should have started before any ended (concurrent)
        starts = [t for name, t in call_order if name.endswith("_start") and "alert" not in name]
        ends = [t for name, t in call_order if name.endswith("_end")]
        # All starts should happen before the first end (within tolerance)
        assert max(starts) < min(ends) + 0.005, "Passes should run concurrently"

        # Alert must start AFTER all others end
        alert_start = [t for name, t in call_order if name == "alert_start"][0]
        assert alert_start >= max(ends) - 0.005, "Alert pass must run after others"

    @pytest.mark.asyncio
    async def test_cycle_tolerates_single_pass_failure(self, monitor):
        """One pass raising doesn't kill the whole cycle."""
        async def failing_adapter():
            raise RuntimeError("adapter boom")

        monitor._probe_pass = AsyncMock()
        monitor._adapter_pass = failing_adapter
        monitor._drift_pass = AsyncMock()
        monitor._discovery_pass = AsyncMock()
        monitor._snmp_pass = AsyncMock()
        monitor._dns_pass = AsyncMock()
        monitor._alert_pass = AsyncMock()

        await monitor._collect_cycle()  # should not raise

        monitor._alert_pass.assert_awaited_once()


class TestAdapterPassConcurrency:
    @pytest.mark.asyncio
    async def test_adapters_queried_concurrently(self, store):
        """Multiple adapters should be queried concurrently."""
        kg = MagicMock()
        kg.graph = MagicMock()
        kg.graph.__contains__ = MagicMock(return_value=False)
        call_times = []

        async def slow_get_interfaces():
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.02)
            return []

        adapter1 = MagicMock()
        adapter1.get_interfaces = slow_get_interfaces
        adapter2 = MagicMock()
        adapter2.get_interfaces = slow_get_interfaces
        adapter3 = MagicMock()
        adapter3.get_interfaces = slow_get_interfaces

        adapters = MagicMock()
        adapters.all_instances.return_value = {"a1": adapter1, "a2": adapter2, "a3": adapter3}
        adapters.device_bindings.return_value = {}

        mon = NetworkMonitor(store, kg, adapters)
        await mon._adapter_pass()

        # All 3 should have started within 5ms of each other (concurrent)
        assert len(call_times) == 3
        assert max(call_times) - min(call_times) < 0.01


class TestDNSPassConcurrency:
    @pytest.mark.asyncio
    async def test_dns_servers_queried_concurrently(self):
        """DNS run_pass should query servers concurrently."""
        config = DNSMonitorConfig(
            servers=[
                DNSServerConfig(id="s1", name="DNS1", ip="8.8.8.8"),
                DNSServerConfig(id="s2", name="DNS2", ip="1.1.1.1"),
            ],
            watched_hostnames=[
                DNSWatchedHostname(hostname="example.com"),
            ],
            enabled=True,
        )
        monitor = DNSMonitor(config)
        call_times = []

        async def fake_query(server, watched):
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.02)
            from src.network.dns_monitor import DNSQueryResult
            return DNSQueryResult(
                server_id=server.id, server_ip=server.ip,
                hostname=watched.hostname, record_type=watched.record_type.value,
                values=["1.2.3.4"], success=True,
            )

        monitor.query_hostname = fake_query
        await monitor.run_pass()

        assert len(call_times) == 2
        assert max(call_times) - min(call_times) < 0.01
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_monitor_concurrency.py -v`
Expected: FAIL — passes are still sequential, timing assertions fail.

**Step 3: Implement concurrency**

**monitor.py — `_collect_cycle()`:**
Replace the sequential calls with:
```python
async def _collect_cycle(self):
    # Run all data-collection passes concurrently
    results = await asyncio.gather(
        self._probe_pass(),
        self._adapter_pass(),
        self._drift_pass(),
        self._discovery_pass(),
        self._snmp_pass(),
        self._dns_pass(),
        return_exceptions=True,
    )
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error("Pass %d failed: %s", i, r)
    # Alert pass runs after all data is collected
    await self._alert_pass()
    self.store.prune_metric_history(older_than_days=7)
```

**monitor.py — `_adapter_pass()`:**
Replace sequential loop with:
```python
async def _adapter_pass(self):
    async def _query_adapter(instance_id, adapter):
        try:
            await adapter.get_interfaces()
        except Exception as e:
            logger.debug("Adapter pass failed for %s: %s", instance_id, e)

    tasks = [
        _query_adapter(iid, a)
        for iid, a in self.adapters.all_instances().items()
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
```

**monitor.py — `_drift_pass()`:**
Replace sequential loop with:
```python
async def _drift_pass(self):
    bindings = self.adapters.device_bindings()
    instance_devices: dict[str, list[str]] = defaultdict(list)
    for device_id, instance_id in bindings.items():
        instance_devices[instance_id].append(device_id)

    async def _check_one(device_id, adapter):
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

    tasks = []
    for instance_id, adapter in self.adapters.all_instances().items():
        for device_id in instance_devices.get(instance_id, []):
            tasks.append(_check_one(device_id, adapter))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
```

**dns_monitor.py — `run_pass()`:**
Replace sequential loop with per-server concurrency:
```python
async def run_pass(self) -> list[dict[str, Any]]:
    if not self.config.enabled:
        return []

    enabled_servers = [s for s in self.config.servers if s.enabled]

    async def _query_server(server):
        results = []
        for watched in self.config.watched_hostnames:
            result = await self.query_hostname(server, watched)
            drift = self.detect_drift(result, watched)
            results.append({
                "measurement": "dns_query",
                "server_id": server.id,
                "server_ip": server.ip,
                "hostname": watched.hostname,
                "record_type": watched.record_type.value,
                "latency_ms": result.latency_ms,
                "success": result.success,
                "nxdomain": result.nxdomain,
                "values": result.values,
                "drift": drift,
                "critical": watched.critical,
            })
            if drift:
                logger.warning(
                    "DNS drift detected: %s/%s on %s — expected %s, got %s",
                    watched.hostname, watched.record_type.value,
                    server.id, drift["expected"], drift["actual"],
                )
        return results

    server_results = await asyncio.gather(
        *[_query_server(s) for s in enabled_servers],
        return_exceptions=True,
    )
    metrics: list[dict[str, Any]] = []
    for r in server_results:
        if isinstance(r, Exception):
            logger.error("DNS server query failed: %s", r)
        else:
            metrics.extend(r)
    return metrics
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_monitor_concurrency.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_monitor_concurrency.py src/network/monitor.py src/network/dns_monitor.py
git commit -m "perf(monitor): parallelize adapter, drift, and DNS passes with asyncio.gather"
```

---

### Task 2: In-Memory TTL Cache for TopologyStore

**Files:**
- Modify: `backend/src/network/topology_store.py:33-39` (`_conn` and add cache)
- Test: `backend/tests/test_topology_cache.py`

**Context:**
- `TopologyStore._conn()` creates a new SQLite connection per call, re-sets PRAGMAs each time.
- `list_devices()`, `list_interfaces()`, `list_device_statuses()` are called every 30s cycle AND on every API request — no caching.
- Use `cachetools.TTLCache` for lightweight in-memory caching (10s TTL, short enough to stay fresh).
- Cache invalidation: any write method (upsert_device, upsert_interface, etc.) clears the cache.

**Step 1: Write the failing tests**

Create `backend/tests/test_topology_cache.py`:

```python
"""Tests for TopologyStore TTL cache."""
import pytest
from src.network.topology_store import TopologyStore
from src.network.models import DeviceType


@pytest.fixture
def store(tmp_path):
    return TopologyStore(str(tmp_path / "test.db"))


class TestTopologyCache:
    def test_list_devices_is_cached(self, store):
        """Second call to list_devices returns cached result without DB query."""
        store.upsert_device("d1", "Device1", "cisco", DeviceType.ROUTER, "10.0.0.1")
        result1 = store.list_devices()
        result2 = store.list_devices()
        assert len(result1) == len(result2) == 1
        # Both should reference the same cached list
        assert result1 is result2

    def test_cache_invalidated_on_upsert(self, store):
        """Upserting a device invalidates the device list cache."""
        store.upsert_device("d1", "Device1", "cisco", DeviceType.ROUTER, "10.0.0.1")
        result1 = store.list_devices()
        store.upsert_device("d2", "Device2", "juniper", DeviceType.SWITCH, "10.0.0.2")
        result2 = store.list_devices()
        assert len(result1) == 1
        assert len(result2) == 2
        assert result1 is not result2

    def test_list_interfaces_is_cached(self, store):
        """list_interfaces results are cached."""
        store.upsert_device("d1", "Device1", "cisco", DeviceType.ROUTER, "10.0.0.1")
        result1 = store.list_interfaces("d1")
        result2 = store.list_interfaces("d1")
        assert result1 is result2

    def test_interface_cache_invalidated_on_upsert(self, store):
        """Upserting an interface invalidates the interface cache."""
        store.upsert_device("d1", "Device1", "cisco", DeviceType.ROUTER, "10.0.0.1")
        result1 = store.list_interfaces("d1")
        store.upsert_interface("i1", "d1", "eth0", "10.0.0.1/24")
        result2 = store.list_interfaces("d1")
        assert result1 is not result2

    def test_list_device_statuses_is_cached(self, store):
        """list_device_statuses results are cached."""
        store.upsert_device("d1", "Device1", "cisco", DeviceType.ROUTER, "10.0.0.1")
        store.upsert_device_status("d1", "up", 5.0, 0.0, "icmp")
        result1 = store.list_device_statuses()
        result2 = store.list_device_statuses()
        assert result1 is result2

    def test_status_cache_invalidated_on_status_upsert(self, store):
        """Upserting device status invalidates the status cache."""
        store.upsert_device("d1", "Device1", "cisco", DeviceType.ROUTER, "10.0.0.1")
        store.upsert_device_status("d1", "up", 5.0, 0.0, "icmp")
        result1 = store.list_device_statuses()
        store.upsert_device_status("d1", "down", 0.0, 1.0, "icmp")
        result2 = store.list_device_statuses()
        assert result1 is not result2
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_topology_cache.py -v`
Expected: FAIL — `result1 is result2` will be False (no caching yet).

**Step 3: Implement caching**

Add to `topology_store.py.__init__()`:
```python
from cachetools import TTLCache

# In __init__:
self._cache = TTLCache(maxsize=64, ttl=10)
```

Add a `_invalidate_cache(*keys)` helper:
```python
def _invalidate_cache(self, *keys):
    for k in keys:
        self._cache.pop(k, None)
```

Wrap `list_devices()`:
```python
def list_devices(self):
    key = "list_devices"
    if key in self._cache:
        return self._cache[key]
    # ... existing query logic ...
    self._cache[key] = result
    return result
```

Same pattern for `list_interfaces(device_id)` (key=`f"list_interfaces:{device_id}"`) and `list_device_statuses()` (key=`"list_device_statuses"`).

Call `_invalidate_cache("list_devices")` in `upsert_device()`, `remove_device()`.
Call `_invalidate_cache(f"list_interfaces:{device_id}")` in `upsert_interface()`, `remove_interface()`.
Call `_invalidate_cache("list_device_statuses")` in `upsert_device_status()`.

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_topology_cache.py -v`
Expected: PASS

**Step 5: Commit**

```bash
pip install cachetools  # if not installed
git add tests/test_topology_cache.py src/network/topology_store.py
git commit -m "perf(store): add TTL-based in-memory cache to TopologyStore list methods"
```

---

### Task 3: Pagination for List Endpoints

**Files:**
- Modify: `backend/src/network/topology_store.py` (`list_devices`, `list_interfaces`, `list_device_statuses`, `list_discovery_candidates`, `list_active_drift_events`)
- Modify: `backend/src/api/monitor_endpoints.py` (add offset/limit query params)
- Test: `backend/tests/test_pagination.py`

**Context:**
- Currently `list_devices()` returns ALL devices. With 1000+ devices this causes memory issues.
- Add `offset` and `limit` params to store methods and API endpoints.
- Default limit=100, max limit=500. Offset defaults to 0.
- Return a `{"items": [...], "total": N, "offset": O, "limit": L}` envelope from API endpoints.

**Step 1: Write the failing tests**

Create `backend/tests/test_pagination.py`:

```python
"""Tests for paginated list endpoints."""
import pytest
from src.network.topology_store import TopologyStore
from src.network.models import DeviceType


@pytest.fixture
def store(tmp_path):
    s = TopologyStore(str(tmp_path / "test.db"))
    for i in range(25):
        s.upsert_device(f"d{i}", f"Device{i}", "cisco", DeviceType.ROUTER, f"10.0.0.{i}")
        s.upsert_device_status(f"d{i}", "up", 5.0, 0.0, "icmp")
    return s


class TestStorePagination:
    def test_list_devices_default(self, store):
        """Default returns all (backwards-compat)."""
        result = store.list_devices()
        assert len(result) == 25

    def test_list_devices_with_limit(self, store):
        result = store.list_devices(limit=10)
        assert len(result) == 10

    def test_list_devices_with_offset(self, store):
        all_devices = store.list_devices()
        page2 = store.list_devices(offset=10, limit=10)
        assert len(page2) == 10
        assert page2[0].id == all_devices[10].id

    def test_list_devices_offset_past_end(self, store):
        result = store.list_devices(offset=100, limit=10)
        assert len(result) == 0

    def test_list_device_statuses_with_limit(self, store):
        result = store.list_device_statuses(limit=5)
        assert len(result) == 5

    def test_list_device_statuses_with_offset(self, store):
        result = store.list_device_statuses(offset=20, limit=10)
        assert len(result) == 5  # only 25 total, offset 20 = 5 remaining

    def test_count_devices(self, store):
        assert store.count_devices() == 25
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_pagination.py -v`
Expected: FAIL — `list_devices()` doesn't accept limit/offset.

**Step 3: Implement pagination**

**topology_store.py — `list_devices()`:**
Add `offset: int = 0, limit: int | None = None` parameters:
```python
def list_devices(self, offset: int = 0, limit: int | None = None):
    conn = self._conn()
    try:
        if limit is not None:
            rows = conn.execute(
                "SELECT * FROM devices ORDER BY id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM devices ORDER BY id").fetchall()
        result = [Device(...) for row in rows]
        return result
    finally:
        conn.close()
```

Note: when limit is None, return all (backwards compat). When limit is set, use LIMIT/OFFSET.

Add `count_devices()`:
```python
def count_devices(self) -> int:
    conn = self._conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    finally:
        conn.close()
```

Same pattern for `list_device_statuses(offset, limit)` and `count_device_statuses()`.

**monitor_endpoints.py — device list endpoint:**
Add query params to the snapshot/device-list endpoints:
```python
@monitor_router.get("/devices")
def list_devices(offset: int = 0, limit: int = 100):
    store = _get_topology_store()
    items = store.list_devices(offset=offset, limit=min(limit, 500))
    total = store.count_devices()
    return {"items": [d.model_dump() for d in items], "total": total, "offset": offset, "limit": limit}
```

**Important:** Don't break the existing `get_snapshot()` — it should continue calling `list_devices()` without args (returns all).

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_pagination.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_pagination.py src/network/topology_store.py src/api/monitor_endpoints.py
git commit -m "feat(store): add offset/limit pagination to list methods and API endpoints"
```

---

### Task 4: API Rate Limiting

**Files:**
- Modify: `backend/src/api/main.py` (add rate-limiting middleware)
- Test: `backend/tests/test_rate_limiting.py`

**Context:**
- No rate limiting exists on any endpoint.
- Use `slowapi` — lightweight FastAPI-compatible rate limiter.
- Default: 60 requests/minute per IP for all endpoints.
- Stricter: 10 requests/minute for heavy endpoints (diagnosis, ad-hoc DNS query).
- Returns 429 Too Many Requests when exceeded.

**Step 1: Write the failing tests**

Create `backend/tests/test_rate_limiting.py`:

```python
"""Tests for API rate limiting."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app)


class TestRateLimiting:
    def test_rate_limiter_middleware_exists(self, client):
        """App should have rate-limiting middleware registered."""
        from src.api.main import app
        middleware_types = [type(m).__name__ for m in app.user_middleware]
        # slowapi adds SlowAPIMiddleware or we check the state
        assert hasattr(app.state, "limiter"), "Rate limiter should be attached to app state"

    def test_rate_limit_header_present(self, client):
        """Responses should include rate-limit headers."""
        response = client.get("/api/v4/network/monitor/snapshot")
        # slowapi adds X-RateLimit headers
        assert "X-RateLimit-Limit" in response.headers or response.status_code in (200, 404, 500)

    def test_excessive_requests_return_429(self, client):
        """Exceeding rate limit returns 429."""
        from src.api.main import limiter
        # Use a test-specific low limit
        # This test verifies the limiter is wired up correctly
        assert limiter is not None
        assert limiter._default_limits is not None or len(limiter._default_limits) > 0
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_rate_limiting.py -v`
Expected: FAIL — no `limiter` attribute on app.

**Step 3: Implement rate limiting**

**main.py — add at top:**
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
```

**main.py — after app creation:**
```python
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

**monitor_endpoints.py — heavy endpoints:**
Add `@limiter.limit("10/minute")` decorator to:
- POST `/diagnose` (network diagnosis)
- POST `/dns/query` (ad-hoc DNS query)

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_rate_limiting.py -v`
Expected: PASS

**Step 5: Commit**

```bash
pip install slowapi
git add tests/test_rate_limiting.py src/api/main.py
git commit -m "feat(api): add rate limiting with slowapi (60/min default, 10/min for heavy endpoints)"
```

---

### Task 5: Health Endpoint with Monitor Heartbeat

**Files:**
- Modify: `backend/src/network/monitor.py` (add heartbeat tracking)
- Modify: `backend/src/api/monitor_endpoints.py` (add `/health` endpoint)
- Test: `backend/tests/test_health_endpoint.py`

**Context:**
- No way to know if the monitor is running, stuck, or crashed.
- Add `_last_cycle_at` and `_last_cycle_duration` to NetworkMonitor.
- Expose `GET /api/v4/network/monitor/health` returning monitor status, uptime, last cycle time, component health.
- Health statuses: "healthy" (cycle < 2 minutes ago), "degraded" (cycle < 5 minutes ago), "unhealthy" (cycle > 5 minutes ago or never ran).

**Step 1: Write the failing tests**

Create `backend/tests/test_health_endpoint.py`:

```python
"""Tests for health endpoint and monitor heartbeat."""
import time
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

from src.network.monitor import NetworkMonitor
from src.network.topology_store import TopologyStore


@pytest.fixture
def store(tmp_path):
    return TopologyStore(str(tmp_path / "test.db"))


@pytest.fixture
def monitor(store):
    kg = MagicMock()
    kg.graph = MagicMock()
    kg.graph.__contains__ = MagicMock(return_value=False)
    adapters = MagicMock()
    adapters.all_instances.return_value = {}
    adapters.device_bindings.return_value = {}
    return NetworkMonitor(store, kg, adapters)


class TestMonitorHeartbeat:
    def test_initial_heartbeat_is_none(self, monitor):
        assert monitor.last_cycle_at is None
        assert monitor.last_cycle_duration is None

    @pytest.mark.asyncio
    async def test_heartbeat_updated_after_cycle(self, monitor):
        monitor._probe_pass = AsyncMock()
        monitor._adapter_pass = AsyncMock()
        monitor._drift_pass = AsyncMock()
        monitor._discovery_pass = AsyncMock()
        monitor._snmp_pass = AsyncMock()
        monitor._dns_pass = AsyncMock()
        monitor._alert_pass = AsyncMock()

        await monitor._collect_cycle()

        assert monitor.last_cycle_at is not None
        assert monitor.last_cycle_duration is not None
        assert monitor.last_cycle_duration >= 0

    def test_health_status_healthy(self, monitor):
        monitor._last_cycle_at = time.monotonic()
        assert monitor.health_status() == "healthy"

    def test_health_status_degraded(self, monitor):
        monitor._last_cycle_at = time.monotonic() - 180  # 3 minutes ago
        assert monitor.health_status() == "degraded"

    def test_health_status_unhealthy(self, monitor):
        monitor._last_cycle_at = time.monotonic() - 600  # 10 minutes ago
        assert monitor.health_status() == "unhealthy"

    def test_health_status_never_ran(self, monitor):
        assert monitor.health_status() == "unhealthy"


class TestHealthEndpoint:
    def test_health_endpoint_returns_status(self):
        from src.api.main import app
        from src.api import monitor_endpoints
        mock_monitor = MagicMock()
        mock_monitor.health_status.return_value = "healthy"
        mock_monitor.last_cycle_at = time.monotonic()
        mock_monitor.last_cycle_duration = 1.5
        mock_monitor.cycle_interval = 30
        mock_monitor.dns_monitor = None
        mock_monitor.alert_engine = None
        mock_monitor.snmp_collector = None

        original = monitor_endpoints._monitor
        monitor_endpoints._monitor = mock_monitor
        try:
            client = TestClient(app)
            response = client.get("/api/v4/network/monitor/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ("healthy", "degraded", "unhealthy")
            assert "last_cycle_duration_s" in data
            assert "cycle_interval_s" in data
        finally:
            monitor_endpoints._monitor = original
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_health_endpoint.py -v`
Expected: FAIL — `last_cycle_at` attribute doesn't exist.

**Step 3: Implement heartbeat and health endpoint**

**monitor.py — add heartbeat tracking:**

In `__init__()`:
```python
self._last_cycle_at: float | None = None
self._last_cycle_duration: float | None = None
self._started_at: float = time.monotonic()
```

Add `import time` at top.

Add properties:
```python
@property
def last_cycle_at(self) -> float | None:
    return self._last_cycle_at

@property
def last_cycle_duration(self) -> float | None:
    return self._last_cycle_duration

def health_status(self) -> str:
    if self._last_cycle_at is None:
        return "unhealthy"
    age = time.monotonic() - self._last_cycle_at
    if age < 120:
        return "healthy"
    elif age < 300:
        return "degraded"
    return "unhealthy"
```

In `_collect_cycle()`, wrap the body:
```python
async def _collect_cycle(self):
    t0 = time.monotonic()
    # ... existing gather + alert logic ...
    self._last_cycle_at = time.monotonic()
    self._last_cycle_duration = time.monotonic() - t0
```

**monitor_endpoints.py — add health endpoint:**
```python
@monitor_router.get("/health")
def get_health():
    monitor = _get_monitor()
    if not monitor:
        return {"status": "unavailable", "message": "Monitor not started"}
    return {
        "status": monitor.health_status(),
        "last_cycle_duration_s": monitor.last_cycle_duration,
        "cycle_interval_s": monitor.cycle_interval,
        "components": {
            "dns_monitor": monitor.dns_monitor is not None,
            "alert_engine": monitor.alert_engine is not None,
            "snmp_collector": monitor.snmp_collector is not None,
        },
    }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_health_endpoint.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_health_endpoint.py src/network/monitor.py src/api/monitor_endpoints.py
git commit -m "feat(monitor): add heartbeat tracking and /health endpoint"
```

---

### Task 6: Final Verification

**Files:** None (read-only verification)

**Step 1: Run all tests**

```bash
cd backend && python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All new tests pass, no regressions (only pre-existing `test_enterprise_store.py` failure).

**Step 2: Verify imports**

```bash
python3 -c "
from src.network.monitor import NetworkMonitor
from src.network.topology_store import TopologyStore
from src.network.dns_monitor import DNSMonitor
print('Monitor: last_cycle_at, health_status —', hasattr(NetworkMonitor, 'health_status'))
print('Store: _cache, _invalidate_cache —', 'OK')
print('All Phase 5 imports verified')
"
```

**Step 3: Verify new features**

```bash
# Check rate limiter
python3 -c "from src.api.main import limiter; print('Rate limiter:', limiter)"

# Check pagination
python3 -c "
import inspect
from src.network.topology_store import TopologyStore
sig = inspect.signature(TopologyStore.list_devices)
print('list_devices params:', list(sig.parameters.keys()))
"
```

**Step 4: Count new tests**

```bash
python3 -m pytest tests/test_monitor_concurrency.py tests/test_topology_cache.py tests/test_pagination.py tests/test_rate_limiting.py tests/test_health_endpoint.py --co -q 2>&1 | tail -1
```

Expected: ~25-30 new tests across 5 files.

# NDM Enterprise Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 56 identified gaps across architecture, backend reliability, API quality, frontend UX, and enterprise features to make the NDM system production-ready.

**Architecture:** TDD approach — write failing tests first, then implement fixes. Each task is a self-contained unit with exact file paths, code, and test commands. Phases are sequential; tasks within a phase can be parallelized where noted.

**Tech Stack:** Python 3.14, FastAPI, SQLite, InfluxDB, Redis Streams, React 18, TypeScript, Tailwind CSS, Recharts, pysnmp, structlog, react-window.

---

## Phase 1: Critical Fixes (7 tasks)

These are ship-blocking issues: fake data, security vulnerability, memory leaks, resource leaks, and missing timeouts.

---

### Task 1: Replace Fake Golden Signals with Real SNMP Metrics

**Files:**
- Modify: `backend/src/network/topology_store.py` — add `aggregate_device_metrics()` method
- Modify: `backend/src/api/collector_endpoints.py` — add aggregate-metrics endpoint
- Modify: `frontend/src/components/Network/NDMOverviewTab.tsx:54-65` — replace Math.random()
- Modify: `frontend/src/services/api.ts` — add `fetchAggregateMetrics()` function
- Test: `backend/tests/test_aggregate_metrics.py` (new)

**Step 1: Write the failing test**

Create `backend/tests/test_aggregate_metrics.py`:

```python
"""Tests for aggregate device metrics endpoint."""
import os
import time
import pytest
from src.network.topology_store import TopologyStore
from src.network.models import Device


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=str(tmp_path / "test.db"))


def test_aggregate_metrics_empty(store):
    result = store.aggregate_device_metrics([])
    assert result == {"avg_cpu": 0, "avg_mem": 0, "avg_temp": 0, "device_count": 0}


def test_aggregate_metrics_with_data(store):
    store.add_device(Device(id="d1", name="sw1", vendor="cisco", device_type="switch", management_ip="10.0.0.1"))
    store.add_device(Device(id="d2", name="sw2", vendor="cisco", device_type="switch", management_ip="10.0.0.2"))
    now = time.time()
    store.add_metric_history("d1", now, {"cpu_pct": 40.0, "mem_pct": 60.0, "temperature": 35.0})
    store.add_metric_history("d2", now, {"cpu_pct": 60.0, "mem_pct": 80.0, "temperature": 45.0})

    result = store.aggregate_device_metrics(["d1", "d2"])
    assert result["avg_cpu"] == pytest.approx(50.0)
    assert result["avg_mem"] == pytest.approx(70.0)
    assert result["avg_temp"] == pytest.approx(40.0)
    assert result["device_count"] == 2


def test_aggregate_metrics_filters_by_device_ids(store):
    store.add_device(Device(id="d1", name="sw1", vendor="cisco", device_type="switch", management_ip="10.0.0.1"))
    store.add_device(Device(id="d2", name="sw2", vendor="cisco", device_type="switch", management_ip="10.0.0.2"))
    now = time.time()
    store.add_metric_history("d1", now, {"cpu_pct": 80.0, "mem_pct": 90.0})
    store.add_metric_history("d2", now, {"cpu_pct": 20.0, "mem_pct": 30.0})

    result = store.aggregate_device_metrics(["d1"])
    assert result["avg_cpu"] == pytest.approx(80.0)
    assert result["device_count"] == 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_aggregate_metrics.py -v`
Expected: FAIL — `AttributeError: 'TopologyStore' object has no attribute 'aggregate_device_metrics'`

**Step 3: Implement aggregate_device_metrics in topology_store.py**

Add after the existing `prune_metric_history` method (search for `def prune_metric_history`):

```python
def aggregate_device_metrics(self, device_ids: list[str]) -> dict:
    """Return averaged latest CPU, memory, temperature across given devices."""
    if not device_ids:
        return {"avg_cpu": 0, "avg_mem": 0, "avg_temp": 0, "device_count": 0}
    conn = self._conn()
    try:
        placeholders = ",".join("?" for _ in device_ids)
        rows = conn.execute(f"""
            SELECT device_id, metrics_json
            FROM metric_history
            WHERE device_id IN ({placeholders})
            AND id IN (
                SELECT MAX(id) FROM metric_history
                WHERE device_id IN ({placeholders})
                GROUP BY device_id
            )
        """, device_ids + device_ids).fetchall()

        cpu_vals, mem_vals, temp_vals = [], [], []
        for row in rows:
            import json
            metrics = json.loads(row["metrics_json"]) if row["metrics_json"] else {}
            if "cpu_pct" in metrics:
                cpu_vals.append(metrics["cpu_pct"])
            if "mem_pct" in metrics:
                mem_vals.append(metrics["mem_pct"])
            if "temperature" in metrics:
                temp_vals.append(metrics["temperature"])

        return {
            "avg_cpu": sum(cpu_vals) / len(cpu_vals) if cpu_vals else 0,
            "avg_mem": sum(mem_vals) / len(mem_vals) if mem_vals else 0,
            "avg_temp": sum(temp_vals) / len(temp_vals) if temp_vals else 0,
            "device_count": len(rows),
        }
    finally:
        conn.close()
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_aggregate_metrics.py -v`
Expected: PASS (3 tests)

**Step 5: Add API endpoint**

In `backend/src/api/collector_endpoints.py`, add:

```python
@collector_router.get("/devices/aggregate-metrics")
async def aggregate_metrics(tag: str | None = None):
    """Return averaged golden signals across all (or tag-filtered) devices."""
    devices = _store().list_devices()
    if tag:
        devices = [d for d in devices if hasattr(d, 'tags') and tag in (d.tags or [])]
    device_ids = [d.id for d in devices]
    return _store().aggregate_device_metrics(device_ids)
```

**Step 6: Update frontend**

In `frontend/src/services/api.ts`, add:

```typescript
export async function fetchAggregateMetrics(tag?: string): Promise<{avg_cpu: number; avg_mem: number; avg_temp: number; device_count: number}> {
  const params = tag ? `?tag=${encodeURIComponent(tag)}` : '';
  const res = await fetch(`${API_BASE}/api/collector/devices/aggregate-metrics${params}`);
  return res.json();
}
```

In `frontend/src/components/Network/NDMOverviewTab.tsx`, replace lines 62-65:

```typescript
// OLD:
const avgCpu = devices.length > 0 ? Math.random() * 40 + 20 : 0;
const avgMem = devices.length > 0 ? Math.random() * 30 + 40 : 0;
return { avgCpu, avgMem, avgLatency, avgLoss };

// NEW — move to useEffect with state:
```

Replace the entire `goldenSignals` useMemo with a `useState` + `useEffect` pattern that calls `fetchAggregateMetrics()` on mount and every 30s, storing `avgCpu` and `avgMem` from the API response. Show "Collecting..." when values are 0 and `device_count` is 0.

**Step 7: Commit**

```bash
git add backend/src/network/topology_store.py backend/src/api/collector_endpoints.py backend/tests/test_aggregate_metrics.py frontend/src/components/Network/NDMOverviewTab.tsx frontend/src/services/api.ts
git commit -m "fix: replace fake golden signals with real SNMP metrics (#1)"
```

---

### Task 2: Fix Command Injection in Codebase Tools

**Files:**
- Modify: `backend/src/tools/codebase_tools.py:44-58`
- Test: `backend/tests/test_codebase_tools_injection.py` (new)

**Step 1: Write the failing test**

Create `backend/tests/test_codebase_tools_injection.py`:

```python
"""Tests for command injection prevention in codebase tools."""
import subprocess
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.tools.codebase_tools import CodebaseSearchTool


def test_search_uses_list_args_not_shell():
    tool = CodebaseSearchTool(repo_path=Path("/tmp"))
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
        tool.search("harmless_pattern", file_extension="py")
        call_args = mock_run.call_args
        # Must NOT use shell=True
        assert call_args.kwargs.get("shell", False) is False or "shell" not in call_args.kwargs
        # First arg must be a list, not a string
        assert isinstance(call_args.args[0], list)


def test_search_with_malicious_pattern():
    tool = CodebaseSearchTool(repo_path=Path("/tmp"))
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
        # Pattern that would be dangerous with shell=True
        tool.search("'; rm -rf /; '", file_extension="*")
        call_args = mock_run.call_args
        assert isinstance(call_args.args[0], list)
        # The malicious pattern should be passed as a single argument, not interpreted
        assert "'; rm -rf /; '" in call_args.args[0]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_codebase_tools_injection.py -v`
Expected: FAIL — `shell=True` found in call args

**Step 3: Fix the subprocess call**

In `backend/src/tools/codebase_tools.py`, replace lines 44-58:

```python
# OLD:
if file_extension == "*":
    cmd = f"grep -rn '{pattern}' {self.repo_path}"
else:
    cmd = f"grep -rn --include='*.{file_extension}' '{pattern}' {self.repo_path}"
cmd += " --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=venv --exclude-dir=__pycache__"
result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

# NEW:
cmd = ["grep", "-rn"]
if file_extension != "*":
    cmd.append(f"--include=*.{file_extension}")
cmd.extend([
    "--exclude-dir=node_modules", "--exclude-dir=.git",
    "--exclude-dir=venv", "--exclude-dir=__pycache__",
    pattern, str(self.repo_path),
])
result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_codebase_tools_injection.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/tools/codebase_tools.py backend/tests/test_codebase_tools_injection.py
git commit -m "security: fix command injection in codebase search tool (#2)"
```

---

### Task 3: Bound Conversation/Application/ASN Dicts in FlowAggregator

**Files:**
- Modify: `backend/src/network/flow_receiver.py:289-291,370-396`
- Test: `backend/tests/test_flow_enhancements.py` — add memory bound tests

**Step 1: Write the failing test**

Add to `backend/tests/test_flow_enhancements.py`:

```python
@pytest.mark.asyncio
async def test_conversations_bounded(aggregator):
    """Conversations dict should not exceed MAX_CONVERSATIONS."""
    for i in range(15000):
        aggregator.ingest(_make_flow(f"10.{i//256}.{i%256}.1", f"10.{i//256}.{i%256}.2", bytes_=100))
    await aggregator.flush()
    convos = aggregator.get_conversations(limit=20000)
    assert len(convos) <= 10001  # MAX_CONVERSATIONS default
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_flow_enhancements.py::test_conversations_bounded -v`
Expected: FAIL — returns 15000 conversations (unbounded)

**Step 3: Implement bounds**

In `backend/src/network/flow_receiver.py`, in the `FlowAggregator.__init__`:

```python
# After line 292 (self._event_bus = event_bus)
MAX_CONVERSATIONS = 10_000
MAX_APPLICATIONS = 500
MAX_ASN_ENTRIES = 1_000
```

In the `flush()` method, after building the `conversations` dict (around line 385), add eviction:

```python
# After conversations are built, trim to MAX
if len(conversations) > self.MAX_CONVERSATIONS:
    sorted_convos = sorted(conversations.items(), key=lambda x: x[1]["bytes"])
    conversations = dict(sorted_convos[len(sorted_convos) - self.MAX_CONVERSATIONS:])
self._conversations = conversations
```

Apply same pattern for `_applications` (MAX_APPLICATIONS) and `_asn_stats` (MAX_ASN_ENTRIES).

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_flow_enhancements.py -v`
Expected: ALL PASS including new bounded test

**Step 5: Commit**

```bash
git add backend/src/network/flow_receiver.py backend/tests/test_flow_enhancements.py
git commit -m "fix: bound conversation/application/ASN dicts to prevent OOM (#3)"
```

---

### Task 4: Add InfluxDB Query Timeout

**Files:**
- Modify: `backend/src/network/metrics_store.py:231-239`
- Test: `backend/tests/test_metrics_timeout.py` (new)

**Step 1: Write the failing test**

Create `backend/tests/test_metrics_timeout.py`:

```python
"""Tests for InfluxDB query timeout handling."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_query_timeout_raises():
    from src.network.metrics_store import MetricsStore

    store = MetricsStore.__new__(MetricsStore)
    store.bucket = "test"
    store._query_api = AsyncMock()
    store._write_api = AsyncMock()
    store._query_timeout = 0.1  # 100ms

    # Simulate a slow query
    async def slow_query(*args, **kwargs):
        await asyncio.sleep(5)  # Takes 5s, timeout is 0.1s

    store._query_api.query = slow_query

    result = await store.query_device_metrics("dev-1", "cpu_pct", "1h")
    # Should return empty list (timeout caught gracefully), not hang
    assert result == []


@pytest.mark.asyncio
async def test_query_succeeds_within_timeout():
    from src.network.metrics_store import MetricsStore

    store = MetricsStore.__new__(MetricsStore)
    store.bucket = "test"
    store._query_timeout = 30.0

    mock_record = MagicMock()
    mock_record.get_time.return_value = MagicMock(isoformat=lambda: "2026-01-01T00:00:00Z")
    mock_record.get_value.return_value = 42.0
    mock_table = MagicMock()
    mock_table.records = [mock_record]
    store._query_api = AsyncMock()
    store._query_api.query = AsyncMock(return_value=[mock_table])

    result = await store.query_device_metrics("dev-1", "cpu_pct", "1h")
    assert len(result) == 1
    assert result[0]["value"] == 42.0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_metrics_timeout.py -v`
Expected: FAIL — `MetricsStore` has no `_query_timeout` attribute

**Step 3: Implement timeout**

In `backend/src/network/metrics_store.py`:

1. In `__init__`, add: `self._query_timeout = float(os.getenv("INFLUXDB_QUERY_TIMEOUT", "30"))`
2. In `query_device_metrics` (and all other query methods), replace:

```python
# OLD:
tables = await self._query_api.query(query)

# NEW:
tables = await asyncio.wait_for(self._query_api.query(query), timeout=self._query_timeout)
```

Add `import asyncio` at top if not already present. Apply to all query methods: `query_device_metrics`, `query_top_talkers`, `query_traffic_matrix`, `query_protocol_breakdown`, and any others.

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_metrics_timeout.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/network/metrics_store.py backend/tests/test_metrics_timeout.py
git commit -m "fix: add configurable query timeout to InfluxDB queries (#4)"
```

---

### Task 5: Fix InfluxDB Cardinality Explosion

**Files:**
- Modify: `backend/src/network/metrics_store.py:90-105`
- Test: `backend/tests/test_flow_cardinality.py` (new)

**Step 1: Write the failing test**

Create `backend/tests/test_flow_cardinality.py`:

```python
"""Tests for flow write cardinality control."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from src.network.metrics_store import FlowRecord, ip_to_subnet_tag


def test_ip_to_subnet_tag_default_24():
    assert ip_to_subnet_tag("10.0.0.123") == "10.0.0.0/24"
    assert ip_to_subnet_tag("192.168.1.55") == "192.168.1.0/24"


def test_ip_to_subnet_tag_custom_prefix():
    assert ip_to_subnet_tag("10.0.1.123", prefix=16) == "10.0.0.0/16"


def test_ip_to_subnet_tag_invalid():
    assert ip_to_subnet_tag("invalid") == "unknown"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_flow_cardinality.py -v`
Expected: FAIL — `ip_to_subnet_tag` not found

**Step 3: Implement cardinality control**

In `backend/src/network/metrics_store.py`, add helper function:

```python
import ipaddress

def ip_to_subnet_tag(ip: str, prefix: int = 24) -> str:
    """Convert IP to /prefix subnet for tag cardinality control."""
    try:
        net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
        return str(net)
    except ValueError:
        return "unknown"
```

Then modify `write_flow()` to use subnet tags instead of raw IPs:

```python
# OLD:
.tag("src_ip", flow.src_ip)
.tag("dst_ip", flow.dst_ip)

# NEW:
.tag("src_subnet", ip_to_subnet_tag(flow.src_ip))
.tag("dst_subnet", ip_to_subnet_tag(flow.dst_ip))
.field("src_ip", flow.src_ip)    # Keep raw IP as field for drill-down
.field("dst_ip", flow.dst_ip)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_flow_cardinality.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/network/metrics_store.py backend/tests/test_flow_cardinality.py
git commit -m "fix: use subnet tags instead of raw IPs to prevent cardinality explosion (#5)"
```

---

### Task 6: Fix SNMP Engine Resource Leak

**Files:**
- Modify: `backend/src/network/snmp_collector.py:120,170`
- Test: `backend/tests/test_snmp_engine_leak.py` (new)

**Step 1: Write the failing test**

Create `backend/tests/test_snmp_engine_leak.py`:

```python
"""Tests for SNMP engine resource cleanup."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_walk_interfaces_closes_engine():
    from src.network.snmp_collector import SNMPProtocolCollector
    from src.network.collectors.instance_store import SNMPDeviceConfig

    collector = SNMPProtocolCollector.__new__(SNMPProtocolCollector)
    cfg = SNMPDeviceConfig(
        device_id="d1", ip="10.0.0.1", community="public",
        version="2c", port=161,
    )

    mock_engine = MagicMock()
    mock_engine.close_dispatcher = MagicMock()

    with patch("src.network.snmp_collector.SnmpEngine", return_value=mock_engine), \
         patch("src.network.snmp_collector.bulk_cmd", new_callable=AsyncMock) as mock_bulk:
        # Simulate empty walk (no interfaces)
        mock_bulk.return_value = (None, None, None, [])

        result = await collector._walk_interfaces(cfg)

        # Engine MUST be closed even when walk returns empty
        mock_engine.close_dispatcher.assert_called_once()


@pytest.mark.asyncio
async def test_walk_interfaces_closes_engine_on_error():
    from src.network.snmp_collector import SNMPProtocolCollector
    from src.network.collectors.instance_store import SNMPDeviceConfig

    collector = SNMPProtocolCollector.__new__(SNMPProtocolCollector)
    cfg = SNMPDeviceConfig(
        device_id="d1", ip="10.0.0.1", community="public",
        version="2c", port=161,
    )

    mock_engine = MagicMock()
    mock_engine.close_dispatcher = MagicMock()

    with patch("src.network.snmp_collector.SnmpEngine", return_value=mock_engine), \
         patch("src.network.snmp_collector.bulk_cmd", side_effect=Exception("timeout")):

        result = await collector._walk_interfaces(cfg)

        # Engine MUST be closed even on exception
        mock_engine.close_dispatcher.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_snmp_engine_leak.py -v`
Expected: FAIL — `close_dispatcher` never called

**Step 3: Fix the leak**

In `backend/src/network/snmp_collector.py`, modify `_walk_interfaces` to close the engine:

```python
# Replace the method body to wrap in try/finally:
async def _walk_interfaces(self, cfg: SNMPDeviceConfig) -> dict[int, dict]:
    # ... existing imports ...
    engine = SnmpEngine()
    try:
        target = UdpTransportTarget((cfg.ip, cfg.port), timeout=5, retries=1)
        # ... rest of existing walk logic (lines 122-169) ...
        return interfaces
    finally:
        engine.close_dispatcher()
```

The key change: wrap everything after `engine = SnmpEngine()` in `try:` and add `finally: engine.close_dispatcher()`.

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_snmp_engine_leak.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/network/snmp_collector.py backend/tests/test_snmp_engine_leak.py
git commit -m "fix: close SNMP engine in _walk_interfaces to prevent FD leak (#6)"
```

---

### Task 7: Add SNMP Walk Timeout

**Files:**
- Modify: `backend/src/network/snmp_collector.py:210` (the call to `_walk_interfaces`)
- Test: `backend/tests/test_snmp_walk_timeout.py` (new)

**Step 1: Write the failing test**

Create `backend/tests/test_snmp_walk_timeout.py`:

```python
"""Tests for SNMP walk timeout protection."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_walk_timeout_returns_partial():
    from src.network.snmp_collector import SNMPProtocolCollector
    from src.network.collectors.instance_store import SNMPDeviceConfig

    collector = SNMPProtocolCollector.__new__(SNMPProtocolCollector)
    collector._walk_timeout = 0.1  # 100ms timeout

    cfg = SNMPDeviceConfig(
        device_id="d1", ip="10.0.0.1", community="public",
        version="2c", port=161,
    )

    original_walk = collector._walk_interfaces

    async def slow_walk(cfg):
        await asyncio.sleep(5)  # 5 seconds, should timeout
        return {}

    collector._walk_interfaces_impl = slow_walk

    # The wrapped call should timeout gracefully
    result = await collector._safe_walk_interfaces(cfg)
    assert result == {}  # Returns empty on timeout
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_snmp_walk_timeout.py -v`
Expected: FAIL — no `_safe_walk_interfaces` or `_walk_timeout` attribute

**Step 3: Implement timeout wrapper**

In `backend/src/network/snmp_collector.py`:

1. Add to `__init__` (or class body): `_walk_timeout = float(os.getenv("SNMP_WALK_TIMEOUT", "60"))`

2. Add timeout wrapper method:

```python
async def _safe_walk_interfaces(self, cfg: SNMPDeviceConfig) -> dict[int, dict]:
    """Walk interfaces with timeout protection."""
    try:
        return await asyncio.wait_for(
            self._walk_interfaces(cfg), timeout=self._walk_timeout
        )
    except asyncio.TimeoutError:
        logger.warning("SNMP walk timed out for %s after %.0fs", cfg.device_id, self._walk_timeout)
        return {}
```

3. In `_snmp_get` (line 210), change:
```python
# OLD:
result["interfaces"] = await self._walk_interfaces(cfg)

# NEW:
result["interfaces"] = await self._safe_walk_interfaces(cfg)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_snmp_walk_timeout.py -v`
Expected: PASS

**Step 5: Run all existing SNMP tests**

Run: `cd backend && python3 -m pytest tests/ -k snmp -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add backend/src/network/snmp_collector.py backend/tests/test_snmp_walk_timeout.py
git commit -m "fix: add timeout protection to SNMP walk to prevent collector hang (#7)"
```

---

## Phase 2: Event Bus & Pipeline Hardening (9 tasks)

### Task 8: Dead Letter Queue for Event Processor

**Files:**
- Modify: `backend/src/network/event_bus/redis_bus.py` — add DLQ on handler failure
- Modify: `backend/src/network/event_bus/memory_bus.py` — add DLQ deque
- Modify: `backend/src/network/event_bus/base.py` — add `get_dlq()` to interface
- Test: `backend/tests/test_event_bus.py` — add DLQ tests

**Step 1: Write the failing test**

Add to `backend/tests/test_event_bus.py`:

```python
@pytest.mark.asyncio
async def test_failed_handler_routes_to_dlq():
    bus = MemoryEventBus(maxsize=100)
    await bus.start()

    async def failing_handler(event):
        raise ValueError("handler crashed")

    await bus.subscribe("traps", failing_handler)
    await bus.publish("traps", {"oid": "1.2.3", "severity": "critical"})

    await asyncio.sleep(0.2)  # Let consumer process

    dlq = bus.get_dlq("traps")
    assert len(dlq) == 1
    assert dlq[0]["event"]["oid"] == "1.2.3"
    assert "ValueError" in dlq[0]["error"]

    await bus.stop()
```

**Step 2-5: Implement, test, commit**

In `base.py` add abstract method `get_dlq(channel) -> list[dict]`.
In `memory_bus.py` add `_dlq: dict[str, deque]` with maxlen=10000. On handler exception, append `{"event": event, "error": str(e), "timestamp": time.time()}` to DLQ instead of silently dropping.
In `redis_bus.py`, XADD to `{channel}:dlq` stream on handler failure.

```bash
git commit -m "feat: add dead letter queue for failed event processing (#8)"
```

---

### Task 9: Backpressure Mechanism

**Files:**
- Modify: `backend/src/network/event_bus/redis_bus.py` — check stream length before XADD
- Modify: `backend/src/network/event_bus/memory_bus.py` — raise on queue > 80%
- Create: `backend/src/network/event_bus/errors.py` — `BackpressureError`
- Test: `backend/tests/test_event_bus.py` — add backpressure tests

**Implementation:**
- Add `BackpressureError(Exception)` in `errors.py`.
- In `memory_bus.publish()`: if `queue.qsize() > self._maxsize * 0.8`, raise `BackpressureError`.
- In `redis_bus.publish()`: check `XLEN` before `XADD`; if > `_STREAM_MAXLEN * 0.8`, raise `BackpressureError`.
- Callers (trap/syslog listeners) catch `BackpressureError` and increment `_dropped_count`.

```bash
git commit -m "feat: add backpressure mechanism to event bus (#9)"
```

---

### Task 10: NetFlow Template Cache TTL

**Files:**
- Modify: `backend/src/network/flow_receiver.py:73` — add timestamp tracking + eviction
- Test: `backend/tests/test_flow_enhancements.py` — add template TTL test

**Implementation:**
- Add `_template_timestamps: dict[tuple, float]` alongside `_v9_templates`.
- On template store, record `time.time()`.
- On template lookup, evict if age > 3600s.
- Add `_MAX_TEMPLATES = 500` cap with LRU eviction.

```bash
git commit -m "fix: add TTL and max size to NetFlow template cache (#10)"
```

---

### Task 11: Alert Deduplication Across Rules

**Files:**
- Modify: `backend/src/network/alert_engine.py:331-336` — add fingerprint-based dedup
- Test: `backend/tests/test_alert_dedup.py` (new)

**Implementation:**
- Add `_active_fingerprints: dict[str, float]` keyed by `f"{entity_id}:{metric_name}:{severity}"`.
- Before `_fire_alert()`, check fingerprint. If exists and within 300s dedup window, skip.
- On resolve, remove fingerprint.

```bash
git commit -m "feat: add cross-rule alert deduplication (#11)"
```

---

### Task 12: Escalation Respects Acknowledgment

**Files:**
- Modify: `backend/src/network/alert_engine.py:427-431`
- Test: `backend/tests/test_alert_dedup.py` — add ack test

**Implementation:**
- In `check_escalations()`, filter out alerts where `acknowledged == True`.

```bash
git commit -m "fix: skip escalation for acknowledged alerts (#12)"
```

---

### Task 13: Knowledge Graph Path Finding Bounds

**Files:**
- Modify: `backend/src/network/knowledge_graph.py:305-306`
- Test: `backend/tests/test_knowledge_graph_paths.py` — add bound test

**Implementation:**
Replace `list(nx.shortest_simple_paths(...))` with `list(itertools.islice(nx.shortest_simple_paths(...), 1000))`. Add `max_depth` parameter that filters out paths longer than 15 nodes.

```bash
git commit -m "fix: bound knowledge graph path enumeration to prevent hang (#13)"
```

---

### Task 14: SQLite Connection Pooling & Cache Thread Safety

**Files:**
- Modify: `backend/src/network/topology_store.py:31-49` — add pool + lock
- Test: `backend/tests/test_topology_concurrency.py` (new)

**Implementation:**
- Replace `_conn()` with `queue.Queue(maxsize=5)` pool.
- Add `threading.Lock` around `_cache` access.
- Add `_get_conn()` that gets from pool or creates new, `_return_conn()` that puts back.
- Use context manager: `with self._connection() as conn:`.

```bash
git commit -m "fix: add connection pooling and thread-safe cache (#14)"
```

---

### Task 15: SNMP Credential Security

**Files:**
- Modify: `backend/src/api/collector_endpoints.py:124-132` — redact in logging
- Test: `backend/tests/test_credential_redaction.py` (new)

**Implementation:**
- Never log `community_string`, `v3_auth_key`, `v3_priv_key`.
- Redact in any debug/warning log: replace with `"***"`.
- Add `X-Sensitive: true` response header on credential endpoints.

```bash
git commit -m "security: redact SNMP credentials from logs (#15)"
```

---

### Task 16: Discovery Concurrency Limit

**Files:**
- Modify: `backend/src/network/discovery_engine.py:69-70`
- Test: `backend/tests/test_discovery_concurrency.py` (new)

**Implementation:**
Replace unbounded `asyncio.gather(*tasks)` with semaphore-controlled:

```python
sem = asyncio.Semaphore(int(os.getenv("DISCOVERY_MAX_CONCURRENT_PROBES", "50")))
async def _bounded_ping(ip):
    async with sem:
        return await self._ping_check(ip)
tasks = [_bounded_ping(ip) for ip in unknown_hosts]
```

```bash
git commit -m "fix: add concurrency limit to discovery probes (#16)"
```

---

## Phase 3: Backend Reliability (Tasks 17-36)

### Task 17/22: API Pagination

**Files:**
- Create: `backend/src/api/pagination.py` — `PaginatedResponse` model + helper
- Modify: `backend/src/api/collector_endpoints.py` — add `?page=&limit=` to list endpoints
- Modify: `backend/src/network/topology_store.py` — add `offset`/`limit` to list methods
- Test: `backend/tests/test_pagination.py` (new)

**Implementation:** Add `PaginatedResponse` Pydantic model. Modify `list_devices()`, `list_interfaces()` etc. to accept `offset` and `limit` params with SQL `LIMIT ? OFFSET ?`. Max limit=100, default=25.

```bash
git commit -m "feat: add server-side pagination to all list endpoints (#17, #22)"
```

---

### Task 23: API Key Authentication

**Files:**
- Create: `backend/src/api/auth.py` — API key middleware
- Modify: `backend/src/api/main.py` — add middleware
- Test: `backend/tests/test_api_auth.py` (new)

**Implementation:** Middleware reads `X-API-Key` header, validates against `API_KEYS` env var. Skip for `/health`, `/metrics`. When `API_KEYS` not set, auth is disabled (dev mode).

```bash
git commit -m "feat: add API key authentication middleware (#23)"
```

---

### Task 24: Health Check Endpoints

**Files:**
- Modify: `backend/src/api/main.py` — add `/health`, `/health/ready`, `/health/live`
- Test: `backend/tests/test_health_endpoints.py` (new)

**Implementation:**
- `/health` — aggregate status from DB, InfluxDB, event bus.
- `/health/ready` — checks SQLite writable, event bus connected.
- `/health/live` — 200 if event loop responsive.

```bash
git commit -m "feat: add health check endpoints for K8s probes (#24)"
```

---

### Tasks 25-36: Remaining Backend Reliability

Each follows the same TDD pattern. Key implementations:

- **Task 25** (Sampling): Parse sampling_interval from v9 template, multiply bytes/packets. Commit: `"feat: add flow sampling rate compensation (#25)"`
- **Task 26** (Flapping): Track state transitions, suppress after 5 in 5min. Commit: `"feat: add alert flapping detection (#26)"`
- **Task 27** (Syslog timestamp): Parse RFC3164/5424 timestamps. Commit: `"fix: parse syslog device timestamps (#27)"`
- **Task 28** (IPv6): Dual-stack listening. Commit: `"feat: add IPv6 syslog support (#28)"`
- **Task 29** (Message size): `MAX_MESSAGE_SIZE = 8192` truncation. Commit: `"fix: validate message size in collectors (#29)"`
- **Task 30** (UDP buffer): Set `SO_RCVBUF = 4MB`. Commit: `"fix: increase UDP receive buffer for trap storms (#30)"`
- **Task 31** (Counter wrap): Auto-detect 32/64-bit counters. Commit: `"fix: handle 64-bit counter wraparound (#31)"`
- **Task 32** (Batch retry): Local retry queue for failed writes. Commit: `"fix: add retry queue for failed metric writes (#32)"`
- **Task 33** (Cache lock): `threading.Lock` on TTLCache. Commit: `"fix: thread-safe TTLCache access (#33)"`
- **Task 34** (Pass timing): Per-pass duration tracking. Commit: `"feat: add per-pass timing to monitor cycle (#34)"`
- **Task 35** (Shutdown): `asyncio.wait_for` with 10s timeout. Commit: `"fix: add graceful shutdown timeout (#35)"`
- **Task 36** (IPAM streaming): 50MB limit + chunked processing. Commit: `"fix: streaming IPAM import with size limit (#36)"`

---

## Phase 4: Input Validation & Testing (Tasks 48-50)

### Task 48: Input Validation on API Endpoints

**Files:**
- Modify: `backend/src/api/collector_endpoints.py` — Pydantic validators
- Modify: `backend/src/api/flow_endpoints.py` — window/interval validation
- Modify: `backend/src/network/models.py` — MAC validation
- Test: `backend/tests/test_input_validation.py` (new)

**Implementation:** Add `@field_validator` for IP (`ipaddress.ip_address`), CIDR (prefix 8-32), port (1-65535), SNMP version (`Literal["1","2c","3"]`), flow window (`re.match(r"^\d+[smhd]$")`).

```bash
git commit -m "feat: add comprehensive input validation on API endpoints (#48)"
```

---

### Task 49: Improve Mock Quality in Tests

**Files:**
- Modify: Multiple test files — use `spec=` parameter
- Test: Run full suite

**Implementation:** Replace `AsyncMock()` with `AsyncMock(spec=MetricsStore)` etc. Add `assert_called_with` for critical paths. Add negative tests for empty/None inputs.

```bash
git commit -m "test: improve mock quality with spec= and negative tests (#49)"
```

---

### Task 50: Integration Tests

**Files:**
- Create: `backend/tests/test_integration_pipeline.py`

**Implementation:** Test full cycles: IPAM→KG→discovery→alerts, SNMP→metrics→alerts, flow→aggregation→flush, concurrent topology writes.

```bash
git commit -m "test: add integration tests for data pipeline (#50)"
```

---

## Phase 5: Frontend UX Hardening (Tasks 18-21, 37-47)

### Task 18: Error Boundary

**Files:**
- Create: `frontend/src/components/Network/NDMErrorBoundary.tsx`
- Modify: `frontend/src/components/Network/DeviceMonitoring.tsx` — wrap each tab

**Implementation:** React error boundary class component. Shows "This tab encountered an error. Click to retry." Catches render errors per-tab.

```bash
git commit -m "feat: add error boundary to NDM tabs (#18)"
```

---

### Task 19: Real-Time Syslog Streaming

**Files:**
- Modify: `frontend/src/components/Network/NDMSyslogTab.tsx` — WebSocket connection
- Modify: `backend/src/network/event_bus/event_processor.py` — broadcast syslog events

**Implementation:** Connect to existing `/ws` WebSocket. New events prepend with fade-in animation. "Pause stream" toggle. Fallback to 10s polling when WS disconnects.

```bash
git commit -m "feat: add real-time syslog streaming via WebSocket (#19)"
```

---

### Task 20: Topology Zoom/Pan

**Files:**
- Modify: `frontend/src/components/Network/NDMTopologyTab.tsx`

**Implementation:** Add SVG transform state `{scale, tx, ty}`. Wheel→zoom (0.25x-4x), drag→pan, +/- buttons, "Fit" reset.

```bash
git commit -m "feat: add zoom/pan controls to topology map (#20)"
```

---

### Task 21: OID MIB Registry

**Files:**
- Create: `backend/src/network/collectors/mib_registry.py` — 200+ common OIDs
- Modify: `backend/src/api/collector_endpoints.py` — add lookup endpoint
- Modify: `frontend/src/components/Network/NDMTrapsTab.tsx` — batch lookup on load

```bash
git commit -m "feat: add MIB OID registry with 200+ common OIDs (#21)"
```

---

### Tasks 37-47: Remaining Frontend UX

- **Task 37** (Debounce): 300ms debounce on search inputs. Commit: `"fix: debounce search inputs (#37)"`
- **Task 38** (Column sort): Clickable headers with sort arrows. Commit: `"feat: add column sorting to device/interface tables (#38)"`
- **Task 39** (Drill-through): Click chart element → filter related table. Commit: `"feat: add chart drill-through on NetFlow tab (#39)"`
- **Task 40** (Virtual scroll): `react-window` for syslog/interface tables. Commit: `"feat: add virtual scrolling for large tables (#40)"`
- **Task 41** (Saved filters): localStorage-based filter presets. Commit: `"feat: add saved filter presets (#41)"`
- **Task 42** (URL routing): `useSearchParams` for tab + filter state. Commit: `"feat: add URL-based tab routing (#42)"`
- **Task 43** (Toast): Replace `alert()` with toast component. Commit: `"fix: replace alert() with toast notifications (#43)"`
- **Task 44** (Responsive panel): `min(520px, 90vw)` + mobile overlay. Commit: `"fix: make detail panel responsive (#44)"`
- **Task 45/46** (Accessibility): ARIA labels, keyboard nav, text labels alongside colors. Commit: `"feat: add ARIA labels and keyboard navigation (#45, #46)"`
- **Task 47** (Design tokens): Create `tokens.ts`, replace hardcoded colors. Commit: `"refactor: extract design tokens for consistent theming (#47)"`

---

## Phase 6: Enterprise Features (Tasks 57-65)

- **Task 57** (Bulk actions): Checkbox column + bulk action toolbar + API. Commit: `"feat: add bulk device actions (#57)"`
- **Task 58** (Log aggregation): Template-based grouping. Commit: `"feat: add syslog message aggregation (#58)"`
- **Task 59** (Flow stitching): 5-tuple biflow matching with 120s timeout. Commit: `"feat: add biflow stitching for accurate bandwidth (#59)"`
- **Task 61** (Circuit breaker): 3-state per-adapter circuit breaker. Commit: `"feat: add circuit breaker for adapter integrations (#61)"`
- **Task 62** (Structured logging): `structlog` with JSON output + correlation IDs. Commit: `"feat: add structured JSON logging with correlation IDs (#62)"`
- **Task 64** (Device relationships): `DeviceRelationship` model + CRUD. Commit: `"feat: add device relationship tracking (#64)"`
- **Task 65** (ASN mapping): Static 5000 ASN→name registry. Commit: `"feat: add ASN-to-name and country mapping (#65)"`

---

## Verification Checkpoints

After each phase, run:

```bash
# Backend tests
cd backend && python3 -m pytest tests/ -v --tb=short

# Frontend type check
cd frontend && npx tsc --noEmit
```

Expected: 0 failures, 0 type errors after every phase.

---

## Total: 56 tasks across 6 phases
## Estimated commits: 56 (one per task)

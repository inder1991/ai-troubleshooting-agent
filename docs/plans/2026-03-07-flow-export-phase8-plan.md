# Phase 8: Flow Analytics & Config Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire up the existing FlowReceiver (dead code) into the app lifecycle, expose flow analytics APIs, and add bulk config export/import endpoints.

**Architecture:** FlowReceiver is already 100% implemented but never instantiated. Wire it into main.py startup, add flow query endpoints leveraging existing MetricsStore queries, and add CSV/JSON export endpoints for devices/subnets/interfaces.

**Tech Stack:** Python asyncio (UDP datagram), InfluxDB (existing), CSV (stdlib)

---

### Task 1: Wire FlowReceiver Into App Lifecycle

**Files:**
- Modify: `backend/src/api/main.py` (instantiate FlowReceiver in startup, stop in shutdown)
- Create: `backend/src/api/flow_endpoints.py` (flow query REST endpoints)
- Test: `backend/tests/test_flow_integration.py`

**Context:**
- `FlowReceiver` in `backend/src/network/flow_receiver.py` is fully implemented but never instantiated.
- It needs `metrics_store` and `topology_store` — both already available in startup.
- It binds to UDP port 2055 (NetFlow) by default. Make port configurable via env var `FLOW_RECEIVER_PORT`.
- `FlowAggregator` needs `device_ip_map` — build from `store.list_devices()` management IPs.
- The receiver should be optional (only starts if `FLOW_RECEIVER_ENABLED=1`).

**Step 1: Write the failing tests**

Create `backend/tests/test_flow_integration.py`:

```python
"""Tests for flow receiver integration and flow query endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.network.flow_receiver import FlowReceiver, FlowParser, FlowAggregator, FlowRecord
from src.network.metrics_store import FlowRecord as MSFlowRecord


class TestFlowReceiverLifecycle:
    def test_flow_receiver_creates(self):
        metrics = MagicMock()
        topo = MagicMock()
        receiver = FlowReceiver(metrics, topo)
        assert receiver is not None
        assert receiver.parser is not None
        assert receiver.aggregator is not None

    def test_update_device_map(self):
        metrics = MagicMock()
        topo = MagicMock()
        receiver = FlowReceiver(metrics, topo)
        receiver.update_device_map({"10.0.0.1": "router-1"})
        assert receiver.aggregator._device_ip_map == {"10.0.0.1": "router-1"}


class TestFlowAggregator:
    def test_ingest_buffers_records(self):
        agg = FlowAggregator(MagicMock(), MagicMock())
        record = FlowRecord(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", src_port=80, dst_port=443,
            protocol=6, bytes=1000, packets=10,
            start_time=None, end_time=None,
            tcp_flags=0, tos=0, input_snmp=0, output_snmp=0,
            src_as=0, dst_as=0, exporter_ip="10.0.0.1",
        )
        agg.ingest(record)
        assert len(agg._buffer) == 1

    @pytest.mark.asyncio
    async def test_flush_writes_to_metrics(self):
        metrics = MagicMock()
        metrics.write_flow = AsyncMock()
        metrics.write_link_metric = AsyncMock()
        topo = MagicMock()
        topo.upsert_link_metric = MagicMock()
        agg = FlowAggregator(metrics, topo)
        record = FlowRecord(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", src_port=80, dst_port=443,
            protocol=6, bytes=1000, packets=10,
            start_time=None, end_time=None,
            tcp_flags=0, tos=0, input_snmp=0, output_snmp=0,
            src_as=0, dst_as=0, exporter_ip="10.0.0.1",
        )
        agg.ingest(record)
        count = await agg.flush()
        assert count == 1
        metrics.write_flow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flush_empty_returns_zero(self):
        agg = FlowAggregator(MagicMock(), MagicMock())
        count = await agg.flush()
        assert count == 0


class TestFlowParser:
    def test_detect_unsupported_version(self):
        parser = FlowParser()
        # Version 99
        import struct
        data = struct.pack("!H", 99) + b"\x00" * 20
        records = parser.detect_and_parse(data, "1.2.3.4")
        assert records == []

    def test_detect_too_short(self):
        parser = FlowParser()
        records = parser.detect_and_parse(b"\x00", "1.2.3.4")
        assert records == []


class TestFlowEndpoints:
    def test_top_talkers_endpoint(self):
        from src.api.main import app
        from src.api import flow_endpoints
        mock_store = MagicMock()
        mock_store.query_top_talkers = AsyncMock(return_value=[
            {"src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "protocol": "6", "bytes": 5000},
        ])
        original = flow_endpoints._metrics_store
        flow_endpoints._metrics_store = mock_store
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/flows/top-talkers")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) >= 1
        finally:
            flow_endpoints._metrics_store = original

    def test_traffic_matrix_endpoint(self):
        from src.api.main import app
        from src.api import flow_endpoints
        mock_store = MagicMock()
        mock_store.query_traffic_matrix = AsyncMock(return_value=[
            {"src": "router-1", "dst": "router-2", "bytes": 10000},
        ])
        original = flow_endpoints._metrics_store
        flow_endpoints._metrics_store = mock_store
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/flows/traffic-matrix")
            assert resp.status_code == 200
        finally:
            flow_endpoints._metrics_store = original

    def test_protocol_breakdown_endpoint(self):
        from src.api.main import app
        from src.api import flow_endpoints
        mock_store = MagicMock()
        mock_store.query_protocol_breakdown = AsyncMock(return_value=[
            {"protocol": "6", "bytes": 50000},
            {"protocol": "17", "bytes": 20000},
        ])
        original = flow_endpoints._metrics_store
        flow_endpoints._metrics_store = mock_store
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/flows/protocol-breakdown")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
        finally:
            flow_endpoints._metrics_store = original

    def test_flow_status_endpoint(self):
        from src.api.main import app
        from src.api import flow_endpoints
        original = flow_endpoints._flow_receiver
        flow_endpoints._flow_receiver = None
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/flows/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] is False
        finally:
            flow_endpoints._flow_receiver = original
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_flow_integration.py -v`
Expected: FAIL — flow_endpoints module doesn't exist.

**Step 3: Implement**

**Create `backend/src/api/flow_endpoints.py`:**

```python
"""Flow analytics REST endpoints."""
from __future__ import annotations
from fastapi import APIRouter

flow_router = APIRouter(prefix="/api/v4/network/flows", tags=["flows"])

_metrics_store = None
_flow_receiver = None


def init_flow_endpoints(metrics_store, flow_receiver=None):
    global _metrics_store, _flow_receiver
    _metrics_store = metrics_store
    _flow_receiver = flow_receiver


@flow_router.get("/top-talkers")
async def top_talkers(window: str = "5m", limit: int = 20):
    if not _metrics_store:
        return []
    return await _metrics_store.query_top_talkers(window=window, limit=limit)


@flow_router.get("/traffic-matrix")
async def traffic_matrix(window: str = "15m"):
    if not _metrics_store:
        return []
    return await _metrics_store.query_traffic_matrix(window=window)


@flow_router.get("/protocol-breakdown")
async def protocol_breakdown(window: str = "1h"):
    if not _metrics_store:
        return []
    return await _metrics_store.query_protocol_breakdown(window=window)


@flow_router.get("/status")
def flow_status():
    return {
        "enabled": _flow_receiver is not None,
        "buffer_size": len(_flow_receiver.aggregator._buffer) if _flow_receiver else 0,
    }
```

**Modify `backend/src/api/main.py`:**

Add import and router registration:
```python
from .flow_endpoints import flow_router, init_flow_endpoints

# In create_app(), with other include_router calls:
app.include_router(flow_router)
```

In the startup handler, after InfluxDB/monitor init:
```python
# ── Initialize FlowReceiver (optional) ──
import os
if os.getenv("FLOW_RECEIVER_ENABLED") == "1":
    from src.network.flow_receiver import FlowReceiver
    flow_receiver = FlowReceiver(metrics_store, topology_store)
    # Build device IP map
    device_map = {d.management_ip: d.id for d in topology_store.list_devices() if d.management_ip}
    flow_receiver.update_device_map(device_map)
    port = int(os.getenv("FLOW_RECEIVER_PORT", "2055"))
    await flow_receiver.start(ports={"netflow": port})
    init_flow_endpoints(metrics_store, flow_receiver)
else:
    init_flow_endpoints(metrics_store)
```

In the shutdown handler:
```python
# Stop flow receiver if running
if hasattr(app.state, 'flow_receiver') and app.state.flow_receiver:
    await app.state.flow_receiver.stop()
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_flow_integration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/flow_endpoints.py tests/test_flow_integration.py src/api/main.py
git commit -m "feat(flows): wire FlowReceiver into app lifecycle and add flow analytics endpoints"
```

---

### Task 2: Bulk Device/Subnet Export (CSV & JSON)

**Files:**
- Create: `backend/src/api/export_endpoints.py`
- Modify: `backend/src/api/main.py` (register export router)
- Test: `backend/tests/test_export_endpoints.py`

**Context:**
- Export devices, subnets, interfaces as CSV or JSON for backup/migration.
- Use `?format=csv` or `?format=json` query param (default json).
- CSV export uses `csv.DictWriter` with appropriate headers.
- JSON export returns the list as-is.
- For CSV: set `Content-Disposition: attachment; filename="devices.csv"` header.

**Step 1: Write the failing tests**

Create `backend/tests/test_export_endpoints.py`:

```python
"""Tests for bulk export endpoints."""
import csv
import io
import json
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from src.network.models import Device, DeviceType, Subnet, Interface
from src.network.topology_store import TopologyStore


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.upsert_device("d1", "Router1", "cisco", DeviceType.ROUTER, "10.0.0.1")
    store.upsert_device("d2", "Switch1", "juniper", DeviceType.SWITCH, "10.0.0.2")
    store.upsert_interface("i1", "d1", "eth0", "10.0.0.1/24")
    store.upsert_interface("i2", "d1", "eth1", "10.0.1.1/24")
    store.upsert_subnet("s1", "10.0.0.0/24", "Office LAN")

    from src.api.main import app
    from src.api import export_endpoints
    original = export_endpoints._topology_store
    export_endpoints._topology_store = store
    client = TestClient(app)
    yield store, client
    export_endpoints._topology_store = original


class TestDeviceExport:
    def test_export_devices_json(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/devices?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Router1"

    def test_export_devices_csv(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/devices?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers.get("content-disposition", "")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "Router1"


class TestSubnetExport:
    def test_export_subnets_json(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/subnets?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_export_subnets_csv(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/subnets?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]


class TestInterfaceExport:
    def test_export_interfaces_json(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/interfaces?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_export_interfaces_csv(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/interfaces?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]


class TestAlertRulesExport:
    def test_export_alert_rules_json(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/alert-rules?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_export_endpoints.py -v`
Expected: FAIL — export_endpoints module doesn't exist.

**Step 3: Implement**

**Create `backend/src/api/export_endpoints.py`:**

```python
"""Bulk export endpoints for devices, subnets, interfaces, alert rules."""
from __future__ import annotations
import csv
import io
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, JSONResponse
from src.utils.logger import get_logger

logger = get_logger(__name__)

export_router = APIRouter(prefix="/api/v4/network/export", tags=["export"])

_topology_store = None
_alert_engine = None


def init_export_endpoints(topology_store, alert_engine=None):
    global _topology_store, _alert_engine
    _topology_store = topology_store
    _alert_engine = alert_engine


def _to_csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    if not rows:
        return StreamingResponse(
            iter(["No data"]), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@export_router.get("/devices")
def export_devices(format: str = Query("json", regex="^(json|csv)$")):
    store = _topology_store
    if not store:
        return []
    devices = store.list_devices()
    rows = [d.model_dump() for d in devices]
    if format == "csv":
        return _to_csv_response(rows, "devices.csv")
    return JSONResponse(content=rows)


@export_router.get("/subnets")
def export_subnets(format: str = Query("json", regex="^(json|csv)$")):
    store = _topology_store
    if not store:
        return []
    subnets = store.list_subnets()
    rows = [s.model_dump() for s in subnets]
    if format == "csv":
        return _to_csv_response(rows, "subnets.csv")
    return JSONResponse(content=rows)


@export_router.get("/interfaces")
def export_interfaces(format: str = Query("json", regex="^(json|csv)$")):
    store = _topology_store
    if not store:
        return []
    interfaces = store.list_interfaces()
    rows = [i.model_dump() for i in interfaces]
    if format == "csv":
        return _to_csv_response(rows, "interfaces.csv")
    return JSONResponse(content=rows)


@export_router.get("/alert-rules")
def export_alert_rules(format: str = Query("json", regex="^(json|csv)$")):
    engine = _alert_engine
    if not engine:
        return JSONResponse(content=[])
    rules = engine.list_rules()
    if format == "csv":
        return _to_csv_response(rules, "alert-rules.csv")
    return JSONResponse(content=rules)
```

**Modify `backend/src/api/main.py`:**

```python
from .export_endpoints import export_router, init_export_endpoints

# In create_app(), with other include_router calls:
app.include_router(export_router)
```

In startup, after topology_store and alert_engine are available:
```python
init_export_endpoints(topology_store, monitor.alert_engine if monitor else None)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_export_endpoints.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/export_endpoints.py tests/test_export_endpoints.py src/api/main.py
git commit -m "feat(export): add bulk CSV/JSON export for devices, subnets, interfaces, alert rules"
```

---

### Task 3: Bulk Device Import from JSON

**Files:**
- Modify: `backend/src/api/export_endpoints.py` (add import endpoint)
- Test: `backend/tests/test_import_endpoints.py`

**Context:**
- Mirror of export: accept JSON array of devices and upsert them.
- `POST /api/v4/network/export/devices/import` accepts JSON body `[{id, name, vendor, device_type, management_ip, ...}]`.
- Returns count of imported/updated devices.
- Validates required fields (id, name, device_type).

**Step 1: Write the failing tests**

Create `backend/tests/test_import_endpoints.py`:

```python
"""Tests for bulk import endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    from src.api.main import app
    from src.api import export_endpoints
    original = export_endpoints._topology_store
    export_endpoints._topology_store = store
    client = TestClient(app)
    yield store, client
    export_endpoints._topology_store = original


class TestDeviceImport:
    def test_import_devices(self, store_and_client):
        store, client = store_and_client
        devices = [
            {"id": "d1", "name": "Router1", "vendor": "cisco", "device_type": "router", "management_ip": "10.0.0.1"},
            {"id": "d2", "name": "Switch1", "vendor": "juniper", "device_type": "switch", "management_ip": "10.0.0.2"},
        ]
        resp = client.post("/api/v4/network/export/devices/import", json=devices)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2

        # Verify devices exist
        stored = store.list_devices()
        assert len(stored) == 2

    def test_import_updates_existing(self, store_and_client):
        store, client = store_and_client
        devices = [{"id": "d1", "name": "Router1", "vendor": "cisco", "device_type": "router", "management_ip": "10.0.0.1"}]
        client.post("/api/v4/network/export/devices/import", json=devices)

        # Import again with updated name
        devices[0]["name"] = "Router1-Updated"
        resp = client.post("/api/v4/network/export/devices/import", json=devices)
        assert resp.status_code == 200

        stored = store.list_devices()
        assert stored[0].name == "Router1-Updated"

    def test_import_empty_list(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/export/devices/import", json=[])
        assert resp.status_code == 200
        assert resp.json()["imported"] == 0

    def test_import_invalid_device_type(self, store_and_client):
        _, client = store_and_client
        devices = [{"id": "d1", "name": "Bad", "vendor": "x", "device_type": "INVALID", "management_ip": "1.2.3.4"}]
        resp = client.post("/api/v4/network/export/devices/import", json=devices)
        # Should handle gracefully — skip or default
        assert resp.status_code == 200
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_import_endpoints.py -v`
Expected: FAIL — endpoint doesn't exist.

**Step 3: Implement**

**Add to `backend/src/api/export_endpoints.py`:**

```python
from src.network.models import DeviceType

@export_router.post("/devices/import")
def import_devices(devices: list[dict]):
    store = _topology_store
    if not store:
        return {"imported": 0, "error": "Store not initialized"}
    count = 0
    for d in devices:
        device_id = d.get("id", "")
        name = d.get("name", "")
        vendor = d.get("vendor", "")
        dt_str = d.get("device_type", "host").upper()
        mgmt_ip = d.get("management_ip", "")
        try:
            device_type = DeviceType[dt_str] if hasattr(DeviceType, dt_str) else DeviceType.HOST
        except (KeyError, ValueError):
            device_type = DeviceType.HOST
        if device_id and name:
            store.upsert_device(device_id, name, vendor, device_type, mgmt_ip)
            count += 1
    return {"imported": count}
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_import_endpoints.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/export_endpoints.py tests/test_import_endpoints.py
git commit -m "feat(export): add bulk device import from JSON"
```

---

### Task 4: Final Verification

**Files:** None (read-only verification)

**Step 1: Run all Phase 8 tests**

```bash
cd backend && python3 -m pytest tests/test_flow_integration.py tests/test_export_endpoints.py tests/test_import_endpoints.py -v
```

**Step 2: Run full test suite**

```bash
python3 -m pytest tests/ --tb=line -q 2>&1 | tail -5
```

**Step 3: Verify imports**

```bash
python3 -c "
from src.api.flow_endpoints import flow_router
from src.api.export_endpoints import export_router
from src.network.flow_receiver import FlowReceiver
print('Flow router endpoints:', [r.path for r in flow_router.routes])
print('Export router endpoints:', [r.path for r in export_router.routes])
print('All Phase 8 imports verified')
"
```

# Phase 16: Bulk Operations & Advanced Queries Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add bulk create/delete operations and advanced search/filter capabilities for network resources.

**Architecture:** New bulk endpoint methods on existing routers + a new search endpoint file for cross-resource queries.

**Tech Stack:** FastAPI (existing), TopologyStore (existing, extend with bulk methods)

---

### Task 1: Bulk Create & Delete Operations

**Files:**
- Modify: `backend/src/api/resource_endpoints.py` (add bulk endpoints)
- Create: `backend/tests/test_bulk_operations.py`

**Context:**
- `bulk_add_routes(routes)` already exists in TopologyStore
- Need bulk create for devices, interfaces, subnets
- Need bulk delete for devices, interfaces, routes
- TopologyStore `add_device`, `add_interface`, `add_subnet` already exist — just loop
- `delete_device` cascades to interfaces/routes

**Endpoints to add to resource_router:**
- POST /devices/bulk — bulk create devices (list of Device objects)
- POST /subnets/bulk — bulk create subnets
- POST /interfaces/bulk — bulk create interfaces
- POST /routes/bulk — bulk create routes (use existing bulk_add_routes)
- DELETE /devices/bulk — bulk delete devices (body: list of IDs)

**Step 1: Write tests**

Create `backend/tests/test_bulk_operations.py`:

```python
"""Tests for bulk create and delete operations."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    from src.api.main import app
    from src.api import resource_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


class TestBulkCreate:
    def test_bulk_create_devices(self, store_and_client):
        store, client = store_and_client
        devices = [
            {"id": f"d{i}", "name": f"Device{i}", "device_type": "host"}
            for i in range(5)
        ]
        resp = client.post("/api/v4/network/resources/devices/bulk", json=devices)
        assert resp.status_code == 201
        assert resp.json()["created"] == 5
        assert len(store.list_devices(offset=0, limit=100)) == 5

    def test_bulk_create_subnets(self, store_and_client):
        store, client = store_and_client
        subnets = [
            {"id": f"sub{i}", "cidr": f"10.{i}.0.0/24"}
            for i in range(3)
        ]
        resp = client.post("/api/v4/network/resources/subnets/bulk", json=subnets)
        assert resp.status_code == 201
        assert resp.json()["created"] == 3

    def test_bulk_create_interfaces(self, store_and_client):
        store, client = store_and_client
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        ifaces = [
            {"id": f"if{i}", "device_id": "d1", "name": f"eth{i}"}
            for i in range(3)
        ]
        resp = client.post("/api/v4/network/resources/interfaces/bulk", json=ifaces)
        assert resp.status_code == 201
        assert resp.json()["created"] == 3

    def test_bulk_create_routes(self, store_and_client):
        store, client = store_and_client
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        routes = [
            {"id": f"rt{i}", "device_id": "d1", "destination_cidr": f"10.{i}.0.0/24", "next_hop": "10.0.0.1"}
            for i in range(5)
        ]
        resp = client.post("/api/v4/network/resources/routes/bulk", json=routes)
        assert resp.status_code == 201
        assert resp.json()["created"] == 5


class TestBulkDelete:
    def test_bulk_delete_devices(self, store_and_client):
        store, client = store_and_client
        for i in range(3):
            store.add_device(Device(id=f"d{i}", name=f"D{i}", device_type=DeviceType.HOST))
        resp = client.request("DELETE", "/api/v4/network/resources/devices/bulk",
                             json={"ids": ["d0", "d1"]})
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2
        assert len(store.list_devices(offset=0, limit=100)) == 1

    def test_bulk_delete_empty_list(self, store_and_client):
        _, client = store_and_client
        resp = client.request("DELETE", "/api/v4/network/resources/devices/bulk",
                             json={"ids": []})
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0
```

Read the actual Route model field names (destination_cidr vs destination) before finalizing tests.

**Step 2:** Run tests, verify failures
**Step 3:** Add bulk endpoints to `resource_endpoints.py`
**Step 4:** Run tests, verify pass
**Step 5:** Commit: `git commit -m "feat(api): add bulk create and delete operations for core resources"`

---

### Task 2: Advanced Device Search & Filtering

**Files:**
- Create: `backend/src/api/search_endpoints.py`
- Modify: `backend/src/api/main.py` (register router)
- Create: `backend/tests/test_search_endpoints.py`

**Context:**
- Devices have: name, vendor, device_type, location, zone_id, management_ip
- Currently: `list_devices(offset, limit)` — no filtering
- Need: search by name pattern, filter by device_type, vendor, location
- TopologyStore stores devices in SQLite — can add WHERE clauses

**Endpoints (under `/api/v4/network/search`):**
- GET /devices — search devices with filters: ?name=, ?device_type=, ?vendor=, ?location=, ?zone_id=, offset, limit
- GET /stats — aggregated counts: devices by type, by vendor, total interfaces, total subnets

**Step 1: Write tests**

Create `backend/tests/test_search_endpoints.py`:

```python
"""Tests for advanced search endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType, Interface, Subnet


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.add_device(Device(id="r1", name="core-router-1", device_type=DeviceType.ROUTER, vendor="cisco", location="us-east"))
    store.add_device(Device(id="r2", name="edge-router-2", device_type=DeviceType.ROUTER, vendor="juniper", location="us-west"))
    store.add_device(Device(id="fw1", name="palo-fw-1", device_type=DeviceType.FIREWALL, vendor="palo_alto", location="us-east"))
    store.add_device(Device(id="sw1", name="access-switch-1", device_type=DeviceType.SWITCH, vendor="cisco", location="eu-west"))
    store.add_interface(Interface(id="if1", device_id="r1", name="eth0"))
    store.add_subnet(Subnet(id="sub1", cidr="10.0.0.0/24"))

    from src.api.main import app
    from src.api import search_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


class TestDeviceSearch:
    def test_search_by_name(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices?name=router")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 2  # core-router-1, edge-router-2

    def test_search_by_type(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices?device_type=firewall")
        assert resp.status_code == 200
        assert len(resp.json()["devices"]) == 1

    def test_search_by_vendor(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices?vendor=cisco")
        assert resp.status_code == 200
        assert len(resp.json()["devices"]) == 2

    def test_search_by_location(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices?location=us-east")
        assert resp.status_code == 200
        assert len(resp.json()["devices"]) == 2

    def test_search_combined_filters(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices?vendor=cisco&location=us-east")
        assert resp.status_code == 200
        assert len(resp.json()["devices"]) == 1  # only core-router-1

    def test_search_pagination(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices?limit=2&offset=0")
        assert resp.status_code == 200
        assert len(resp.json()["devices"]) == 2

    def test_search_no_results(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices?name=nonexistent")
        assert resp.status_code == 200
        assert len(resp.json()["devices"]) == 0


class TestStats:
    def test_get_stats(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_devices"] == 4
        assert data["total_interfaces"] >= 1
        assert data["total_subnets"] >= 1
        assert "by_type" in data
        assert "by_vendor" in data
```

**Step 2:** Run tests, verify failures

**Step 3:** Implement

Create `backend/src/api/search_endpoints.py` — implements search by querying TopologyStore's SQLite directly:

```python
"""Advanced search and statistics endpoints."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from src.utils.logger import get_logger

logger = get_logger(__name__)

search_router = APIRouter(prefix="/api/v4/network/search", tags=["search"])

_topology_store = None


def init_search_endpoints(topology_store):
    global _topology_store
    _topology_store = topology_store


def _store():
    if not _topology_store:
        raise HTTPException(503, "Store not initialized")
    return _topology_store


@search_router.get("/devices")
def search_devices(
    name: str = None, device_type: str = None, vendor: str = None,
    location: str = None, zone_id: str = None,
    offset: int = 0, limit: int = 50,
):
    store = _store()
    # Build WHERE clauses dynamically
    conditions = []
    params = []
    if name:
        conditions.append("name LIKE ?")
        params.append(f"%{name}%")
    if device_type:
        conditions.append("device_type = ?")
        params.append(device_type)
    if vendor:
        conditions.append("vendor = ?")
        params.append(vendor)
    if location:
        conditions.append("location = ?")
        params.append(location)
    if zone_id:
        conditions.append("zone_id = ?")
        params.append(zone_id)

    where = " AND ".join(conditions) if conditions else "1=1"
    query = f"SELECT * FROM devices WHERE {where} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    conn = store._get_conn()
    conn.row_factory = _dict_factory
    rows = conn.execute(query, params).fetchall()
    return {"devices": rows, "offset": offset, "limit": limit, "count": len(rows)}


@search_router.get("/stats")
def get_stats():
    store = _store()
    conn = store._get_conn()
    total_devices = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    total_interfaces = conn.execute("SELECT COUNT(*) FROM interfaces").fetchone()[0]
    total_subnets = conn.execute("SELECT COUNT(*) FROM subnets").fetchone()[0]

    by_type = {}
    for row in conn.execute("SELECT device_type, COUNT(*) as cnt FROM devices GROUP BY device_type"):
        by_type[row[0]] = row[1]

    by_vendor = {}
    for row in conn.execute("SELECT vendor, COUNT(*) as cnt FROM devices GROUP BY vendor"):
        by_vendor[row[0]] = row[1]

    return {
        "total_devices": total_devices,
        "total_interfaces": total_interfaces,
        "total_subnets": total_subnets,
        "by_type": by_type,
        "by_vendor": by_vendor,
    }


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
```

IMPORTANT: Check how TopologyStore exposes its connection. It might use `_get_conn()`, `_conn`, or a `conn` property. Read the file first. Also check if there's a `sqlite3.Row` factory already being used.

Register in main.py.

**Step 4:** Run tests, verify pass
**Step 5:** Commit: `git commit -m "feat(api): add device search with filters and network statistics endpoint"`

---

### Task 3: Final Verification

**Step 1:** Run all Phase 16 tests:
```bash
cd backend && python3 -m pytest tests/test_bulk_operations.py tests/test_search_endpoints.py -v
```

**Step 2:** Run full suite:
```bash
python3 -m pytest tests/ --tb=line -q 2>&1 | tail -5
```

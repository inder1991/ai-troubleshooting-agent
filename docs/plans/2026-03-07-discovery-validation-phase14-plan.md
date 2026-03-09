# Phase 14: Discovery & Validation APIs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose discovery engine capabilities and interface validation as API endpoints.

**Architecture:** Thin API wrappers around existing DiscoveryEngine and validate_device_interfaces.

**Tech Stack:** FastAPI (existing), DiscoveryEngine (existing), interface_validation (existing)

---

### Task 1: Discovery Engine Query & Trigger Endpoints

**Files:**
- Create: `backend/src/api/discovery_endpoints.py`
- Modify: `backend/src/api/main.py` (register router)
- Create: `backend/tests/test_discovery_endpoints.py`

**Context:**
- `DiscoveryEngine.__init__(store, kg)` — takes topology store and knowledge graph
- `discover_from_adapters(adapters)` — async, discovers devices from configured adapters, returns list of dicts
- `probe_known_subnets()` — async, pings IPs in known subnets to find new devices
- `reverse_dns(ip)` — async, does reverse DNS lookup
- Existing endpoints in monitor_endpoints.py: `POST /discover/{ip}/promote`, `POST /discover/{ip}/dismiss`
- `TopologyStore.list_discovery_candidates()` returns candidates
- Need: `GET /discovery/candidates` (list), `POST /discovery/scan` (trigger subnet probe)

**Endpoints (under `/api/v4/network/discovery`):**
- GET /candidates — list discovery candidates (already in store)
- POST /scan — trigger subnet probe (calls probe_known_subnets)
- POST /reverse-dns — resolve hostname for an IP

**Step 1: Write tests**

Create `backend/tests/test_discovery_endpoints.py`:

```python
"""Tests for discovery engine endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType, Subnet


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
    store.add_subnet(Subnet(id="sub1", cidr="10.0.0.0/24"))
    # Seed a candidate
    store.upsert_discovery_candidate("10.0.0.50", "aa:bb:cc:dd:ee:ff", "unknown-host", "2026-03-07", "2026-03-07")

    from src.api.main import app
    from src.api import discovery_endpoints as ep
    orig_store = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig_store


class TestDiscoveryCandidates:
    def test_list_candidates(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/discovery/candidates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_list_candidates_empty(self, tmp_path):
        store = TopologyStore(str(tmp_path / "empty.db"))
        from src.api.main import app
        from src.api import discovery_endpoints as ep
        orig = ep._topology_store
        ep._topology_store = store
        client = TestClient(app)
        resp = client.get("/api/v4/network/discovery/candidates")
        assert resp.status_code == 200
        assert resp.json() == []
        ep._topology_store = orig


class TestDiscoveryScan:
    def test_scan_endpoint_exists(self, store_and_client):
        _, client = store_and_client
        # Scan triggers async probe — just verify endpoint responds
        resp = client.post("/api/v4/network/discovery/scan")
        assert resp.status_code in (200, 503)  # 503 if engine not initialized

    def test_reverse_dns(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/discovery/reverse-dns", json={"ip": "8.8.8.8"})
        assert resp.status_code in (200, 503)
```

**Step 2:** Run tests, verify failures
**Step 3:** Implement `discovery_endpoints.py`, register in main.py
**Step 4:** Run tests, verify pass
**Step 5:** Commit: `git commit -m "feat(api): add discovery candidate and scan endpoints"`

---

### Task 2: Interface Validation API Endpoint

**Files:**
- Modify: `backend/src/api/resource_endpoints.py` (add validation endpoint)
- Create: `backend/tests/test_validation_endpoint.py`

**Context:**
- `validate_device_interfaces(device_id, interfaces, subnets, zones, device_vlan_id)` returns list of error dicts
- Each error: `{rule, field, message, severity, interface_id}`
- TopologyStore has all the data needed: `list_interfaces(device_id)`, `list_subnets()`, `list_zones()`
- Need: `GET /api/v4/network/resources/validate/{device_id}` — runs validation for a device's interfaces

**Endpoints:**
- GET /validate/{device_id} — validate all interfaces for a device
- POST /validate/bulk — validate multiple devices at once

**Step 1: Write tests**

Create `backend/tests/test_validation_endpoint.py`:

```python
"""Tests for interface validation endpoint."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType, Interface, Subnet, Zone


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.add_device(Device(id="fw1", name="FW1", device_type=DeviceType.FIREWALL))
    store.add_subnet(Subnet(id="sub1", cidr="10.0.0.0/24"))
    # Valid interface
    store.add_interface(Interface(id="if1", device_id="fw1", name="eth0", ip="10.0.0.1", subnet_id="sub1", zone_id="z1"))
    # Invalid: IP outside subnet
    store.add_interface(Interface(id="if2", device_id="fw1", name="eth1", ip="192.168.1.1", subnet_id="sub1", zone_id="z2"))
    store.add_zone(Zone(id="z1", name="Inside"))
    store.add_zone(Zone(id="z2", name="Outside"))

    from src.api.main import app
    from src.api import resource_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


class TestValidationEndpoint:
    def test_validate_device(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/resources/validate/fw1")
        assert resp.status_code == 200
        data = resp.json()
        assert "errors" in data
        assert "device_id" in data
        # Should find rule 29 violation (IP outside subnet)
        assert any(e["rule"] == 29 for e in data["errors"])

    def test_validate_unknown_device(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/resources/validate/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["errors"] == []  # No interfaces = no errors

    def test_validate_bulk(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/validate/bulk", json={"device_ids": ["fw1"]})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "fw1"
```

**Step 2:** Run tests, verify failures
**Step 3:** Add validation endpoints to `resource_endpoints.py`

```python
from src.network.interface_validation import validate_device_interfaces
from src.network.models import Interface, Subnet, Zone

@resource_router.get("/validate/{device_id}")
def validate_device(device_id: str):
    store = _store()
    ifaces_raw = store.list_interfaces(device_id=device_id)
    subnets_raw = store.list_subnets()
    zones_raw = store.list_zones()
    # Convert dicts back to models
    ifaces = [Interface(**i) for i in ifaces_raw]
    subnets = [Subnet(**s) for s in subnets_raw]
    zones = [Zone(**z) for z in zones_raw]
    errors = validate_device_interfaces(device_id, ifaces, subnets, zones)
    return {"device_id": device_id, "errors": errors, "interface_count": len(ifaces)}

@resource_router.post("/validate/bulk")
def validate_bulk(body: dict):
    store = _store()
    device_ids = body.get("device_ids", [])
    subnets_raw = store.list_subnets()
    zones_raw = store.list_zones()
    subnets = [Subnet(**s) for s in subnets_raw]
    zones = [Zone(**z) for z in zones_raw]
    results = []
    for did in device_ids:
        ifaces_raw = store.list_interfaces(device_id=did)
        ifaces = [Interface(**i) for i in ifaces_raw]
        errors = validate_device_interfaces(did, ifaces, subnets, zones)
        results.append({"device_id": did, "errors": errors, "interface_count": len(ifaces)})
    return results
```

IMPORTANT: Place `validate/bulk` and `validate/{device_id}` routes carefully to avoid conflicts with other resource endpoints. Also read the actual models to verify dict-to-model conversion works.

**Step 4:** Run tests, verify pass
**Step 5:** Commit: `git commit -m "feat(api): add interface validation endpoint and bulk validation"`

---

### Task 3: Final Verification

**Step 1:** Run all Phase 14 tests:
```bash
cd backend && python3 -m pytest tests/test_discovery_endpoints.py tests/test_validation_endpoint.py -v
```

**Step 2:** Run full suite:
```bash
python3 -m pytest tests/ --tb=line -q 2>&1 | tail -5
```

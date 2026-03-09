# Phase 10: Operations APIs & Test Coverage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose SNMP configuration, link metrics, and HA validation via API endpoints; add test coverage for SNMP collector and HA validation.

**Architecture:** New endpoints on existing routers. SNMP config stored on KG nodes (already used by monitor). Link metrics already in TopologyStore — just need API exposure. HA validation logic already complete — just needs an endpoint wrapper.

**Tech Stack:** FastAPI (existing), SQLite (existing), pysnmp (optional runtime dep)

---

### Task 1: SNMP Configuration Endpoints & Tests

**Files:**
- Create: `backend/src/api/snmp_endpoints.py`
- Modify: `backend/src/api/main.py` (register snmp_router)
- Create: `backend/tests/test_snmp_endpoints.py`

**Context:**
- SNMP config lives on KG graph nodes: `snmp_enabled`, `snmp_version`, `snmp_community`, `snmp_port`
- The monitor's `_snmp_pass()` reads these from `self.kg.graph.nodes[device_id]`
- We need CRUD endpoints to manage SNMP config per device
- The `NetworkKnowledgeGraph` is available in `network_endpoints.py` as `_knowledge_graph`
- SNMPCollector rate computation and counter wraparound is pure logic — easy to unit test

**Step 1: Write the failing tests**

Create `backend/tests/test_snmp_endpoints.py`:

```python
"""Tests for SNMP configuration endpoints and collector logic."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

from src.network.snmp_collector import SNMPCollector, SNMPDeviceConfig


class TestSNMPCollectorRates:
    def test_first_poll_returns_none(self):
        collector = SNMPCollector(MagicMock())
        result = collector._compute_rates("d1", 1, {"ifInOctets": 1000, "ifOutOctets": 2000, "ifSpeed": 1_000_000_000})
        assert result is None

    def test_second_poll_returns_rates(self):
        collector = SNMPCollector(MagicMock())
        collector._compute_rates("d1", 1, {"ifInOctets": 1000, "ifOutOctets": 2000, "ifSpeed": 1_000_000_000})
        import time
        collector._prev_counters[("d1", 1)] = (
            {"ifInOctets": 1000, "ifOutOctets": 2000, "ifSpeed": 1_000_000_000},
            time.time() - 10,
        )
        result = collector._compute_rates("d1", 1, {"ifInOctets": 2000, "ifOutOctets": 3000, "ifSpeed": 1_000_000_000})
        assert result is not None
        assert result["bps_in"] > 0
        assert result["bps_out"] > 0
        assert 0 <= result["utilization"] <= 1

    def test_counter_wraparound_32bit(self):
        collector = SNMPCollector(MagicMock())
        import time
        collector._prev_counters[("d1", 1)] = (
            {"ifInOctets": 2**32 - 100, "ifOutOctets": 0, "ifSpeed": 1_000_000_000},
            time.time() - 10,
        )
        result = collector._compute_rates("d1", 1, {"ifInOctets": 100, "ifOutOctets": 0, "ifSpeed": 1_000_000_000})
        assert result is not None
        assert result["bps_in"] > 0  # Should handle wraparound

    def test_error_rate_calculation(self):
        collector = SNMPCollector(MagicMock())
        import time
        collector._prev_counters[("d1", 1)] = (
            {"ifInOctets": 0, "ifOutOctets": 0, "ifInErrors": 0, "ifOutErrors": 0, "ifSpeed": 1_000_000_000},
            time.time() - 10,
        )
        result = collector._compute_rates("d1", 1, {
            "ifInOctets": 1000, "ifOutOctets": 1000,
            "ifInErrors": 5, "ifOutErrors": 5, "ifSpeed": 1_000_000_000,
        })
        assert result is not None
        assert result["error_rate"] > 0

    def test_hc_counters_preferred(self):
        collector = SNMPCollector(MagicMock())
        import time
        collector._prev_counters[("d1", 1)] = (
            {"ifHCInOctets": 0, "ifHCOutOctets": 0, "ifInOctets": 0, "ifOutOctets": 0, "ifSpeed": 1_000_000_000},
            time.time() - 10,
        )
        result = collector._compute_rates("d1", 1, {
            "ifHCInOctets": 5000, "ifHCOutOctets": 3000,
            "ifInOctets": 100, "ifOutOctets": 100, "ifSpeed": 1_000_000_000,
        })
        assert result is not None
        # HC counters should be used, giving higher bps than 32-bit values
        assert result["bps_in"] > 0


class TestSNMPConfigEndpoints:
    def test_get_snmp_config(self):
        from src.api.main import app
        from src.api import snmp_endpoints
        mock_kg = MagicMock()
        mock_kg.graph.nodes = {"d1": {"snmp_enabled": True, "snmp_version": "v2c", "snmp_community": "public", "snmp_port": 161}}
        mock_kg.graph.__contains__ = lambda self, x: x == "d1"
        original = snmp_endpoints._knowledge_graph
        snmp_endpoints._knowledge_graph = mock_kg
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/snmp/d1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["snmp_enabled"] is True
            assert data["snmp_version"] == "v2c"
        finally:
            snmp_endpoints._knowledge_graph = original

    def test_update_snmp_config(self):
        from src.api.main import app
        from src.api import snmp_endpoints
        import networkx as nx
        mock_kg = MagicMock()
        g = nx.DiGraph()
        g.add_node("d1", device_type="router")
        mock_kg.graph = g
        original = snmp_endpoints._knowledge_graph
        snmp_endpoints._knowledge_graph = mock_kg
        try:
            client = TestClient(app)
            resp = client.put("/api/v4/network/snmp/d1", json={
                "snmp_enabled": True, "snmp_version": "v2c",
                "snmp_community": "private", "snmp_port": 161,
            })
            assert resp.status_code == 200
            assert g.nodes["d1"]["snmp_enabled"] is True
            assert g.nodes["d1"]["snmp_community"] == "private"
        finally:
            snmp_endpoints._knowledge_graph = original

    def test_get_snmp_config_not_found(self):
        from src.api.main import app
        from src.api import snmp_endpoints
        mock_kg = MagicMock()
        mock_kg.graph.nodes = {}
        mock_kg.graph.__contains__ = lambda self, x: False
        original = snmp_endpoints._knowledge_graph
        snmp_endpoints._knowledge_graph = mock_kg
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/snmp/nonexistent")
            assert resp.status_code == 404
        finally:
            snmp_endpoints._knowledge_graph = original
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_snmp_endpoints.py -v`
Expected: FAIL — snmp_endpoints module doesn't exist.

**Step 3: Implement**

**Create `backend/src/api/snmp_endpoints.py`:**

```python
"""SNMP configuration endpoints."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from src.utils.logger import get_logger

logger = get_logger(__name__)

snmp_router = APIRouter(prefix="/api/v4/network/snmp", tags=["snmp"])

_knowledge_graph = None


def init_snmp_endpoints(knowledge_graph):
    global _knowledge_graph
    _knowledge_graph = knowledge_graph


@snmp_router.get("/{device_id}")
def get_snmp_config(device_id: str):
    kg = _knowledge_graph
    if not kg or device_id not in kg.graph:
        raise HTTPException(status_code=404, detail="Device not found")
    node = dict(kg.graph.nodes[device_id])
    return {
        "device_id": device_id,
        "snmp_enabled": node.get("snmp_enabled", False),
        "snmp_version": node.get("snmp_version", "v2c"),
        "snmp_community": node.get("snmp_community", "public"),
        "snmp_port": node.get("snmp_port", 161),
    }


@snmp_router.put("/{device_id}")
def update_snmp_config(device_id: str, config: dict):
    kg = _knowledge_graph
    if not kg or device_id not in kg.graph:
        raise HTTPException(status_code=404, detail="Device not found")
    allowed = {"snmp_enabled", "snmp_version", "snmp_community", "snmp_port"}
    for key in allowed:
        if key in config:
            kg.graph.nodes[device_id][key] = config[key]
    return {"status": "updated", "device_id": device_id}
```

**Modify `backend/src/api/main.py`:**

Add import and register router:
```python
from .snmp_endpoints import snmp_router, init_snmp_endpoints
app.include_router(snmp_router)
```

In startup, after KG is available:
```python
init_snmp_endpoints(kg)
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_snmp_endpoints.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/snmp_endpoints.py tests/test_snmp_endpoints.py src/api/main.py
git commit -m "feat(snmp): add SNMP config endpoints and collector unit tests"
```

---

### Task 2: Link Metrics Endpoint

**Files:**
- Modify: `backend/src/api/monitor_endpoints.py` (add link-metrics endpoint)
- Create: `backend/tests/test_link_metrics_endpoint.py`

**Context:**
- `TopologyStore.list_link_metrics()` returns `list[dict]` with keys: src_id, dst_id, latency_ms, bandwidth_bps, error_rate, utilization, updated_at
- `TopologyStore.upsert_link_metric(src_id, dst_id, latency_ms, bandwidth_bps, error_rate, utilization)` already exists
- Need a simple GET endpoint to list all link metrics with optional filtering by src_id or dst_id

**Step 1: Write the failing tests**

Create `backend/tests/test_link_metrics_endpoint.py`:

```python
"""Tests for link metrics endpoint."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import DeviceType


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.upsert_device("r1", "Router1", "cisco", DeviceType.ROUTER, "10.0.0.1")
    store.upsert_device("r2", "Router2", "cisco", DeviceType.ROUTER, "10.0.0.2")
    store.upsert_link_metric("r1", "r2", 5.0, 1_000_000_000, 0.001, 0.45)
    store.upsert_link_metric("r2", "r1", 6.0, 1_000_000_000, 0.002, 0.30)

    from src.api.main import app
    import src.api.monitor_endpoints as mon_ep
    orig = mon_ep._topology_store
    mon_ep._topology_store = store
    client = TestClient(app)
    yield store, client
    mon_ep._topology_store = orig


class TestLinkMetrics:
    def test_list_all_link_metrics(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/link-metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_filter_by_src(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/link-metrics?src_id=r1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["src_id"] == "r1"

    def test_filter_by_dst(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/link-metrics?dst_id=r1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["dst_id"] == "r1"

    def test_empty_when_no_store(self):
        from src.api.main import app
        import src.api.monitor_endpoints as mon_ep
        orig = mon_ep._topology_store
        mon_ep._topology_store = None
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/monitor/link-metrics")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            mon_ep._topology_store = orig
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_link_metrics_endpoint.py -v`
Expected: FAIL — endpoint doesn't exist.

**Step 3: Implement**

**Modify `backend/src/api/monitor_endpoints.py`:**

Add a new endpoint (read the file first to find the correct insertion point):

```python
@monitor_router.get("/link-metrics")
def list_link_metrics(src_id: str | None = None, dst_id: str | None = None):
    store = _topology_store
    if not store:
        return []
    metrics = store.list_link_metrics()
    if src_id:
        metrics = [m for m in metrics if m.get("src_id") == src_id]
    if dst_id:
        metrics = [m for m in metrics if m.get("dst_id") == dst_id]
    return metrics
```

IMPORTANT: Place this BEFORE any `/{param}` catch-all route to avoid route shadowing.

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_link_metrics_endpoint.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/monitor_endpoints.py tests/test_link_metrics_endpoint.py
git commit -m "feat(monitor): add link-metrics endpoint with src/dst filtering"
```

---

### Task 3: HA Group Validation Endpoint

**Files:**
- Modify: `backend/src/api/network_endpoints.py` (add validation endpoint)
- Create: `backend/tests/test_ha_validation_endpoint.py`

**Context:**
- `validate_ha_group(store, group)` in `backend/src/network/ha_validation.py` is fully implemented
- Returns list of error strings
- HA group CRUD already exists in network_endpoints.py
- TopologyStore has `get_ha_group(group_id)` returning an HAGroup model
- Need `GET /api/v4/network/ha-groups/{group_id}/validate`

**Step 1: Write the failing tests**

Create `backend/tests/test_ha_validation_endpoint.py`:

```python
"""Tests for HA group validation endpoint."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import DeviceType, HAMode


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    # Create 2 devices in same subnet
    store.upsert_device("fw1", "Firewall1", "paloalto", DeviceType.FIREWALL, "10.0.0.1")
    store.upsert_device("fw2", "Firewall2", "paloalto", DeviceType.FIREWALL, "10.0.0.2")
    store.upsert_subnet("s1", "10.0.0.0/24", "FW Subnet")
    # Create HA group
    store.upsert_ha_group("ha1", "FW-HA", HAMode.ACTIVE_PASSIVE, ["fw1", "fw2"],
                          virtual_ips=["10.0.0.100"], active_member_id="fw1")

    from src.api.main import app
    from src.api import network_endpoints
    orig_store = network_endpoints._get_topology_store
    network_endpoints._get_topology_store = lambda: store
    client = TestClient(app)
    yield store, client
    network_endpoints._get_topology_store = orig_store


class TestHAValidation:
    def test_validate_valid_group(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/ha-groups/ha1/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_nonexistent_group(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/ha-groups/nonexistent/validate")
        assert resp.status_code == 404

    def test_validate_mixed_device_types(self, store_and_client):
        store, client = store_and_client
        store.upsert_device("sw1", "Switch1", "cisco", DeviceType.SWITCH, "10.0.0.3")
        store.upsert_ha_group("ha2", "Mixed-HA", HAMode.ACTIVE_PASSIVE, ["fw1", "sw1"],
                              virtual_ips=["10.0.0.101"], active_member_id="fw1")
        resp = client.get("/api/v4/network/ha-groups/ha2/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_missing_active_member(self, store_and_client):
        store, client = store_and_client
        store.upsert_ha_group("ha3", "No-Active", HAMode.ACTIVE_PASSIVE, ["fw1", "fw2"],
                              virtual_ips=[], active_member_id="")
        resp = client.get("/api/v4/network/ha-groups/ha3/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_ha_validation_endpoint.py -v`
Expected: FAIL — endpoint doesn't exist.

**Step 3: Implement**

**Modify `backend/src/api/network_endpoints.py`:**

First read the file to find where the HA group endpoints are. Then add a validation endpoint nearby:

```python
from src.network.ha_validation import validate_ha_group

@network_router.get("/ha-groups/{group_id}/validate")
def validate_ha(group_id: str):
    store = _get_topology_store()
    group = store.get_ha_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="HA group not found")
    errors = validate_ha_group(store, group)
    return {"group_id": group_id, "valid": len(errors) == 0, "errors": errors}
```

IMPORTANT: This route MUST be placed BEFORE any `/{group_id}` catch-all GET route for HA groups. Read the file to verify routing order.

Also check if `_get_topology_store` is a function or variable. If it's a module-level variable `_topology_store`, use that instead.

Check the actual `upsert_ha_group` and `get_ha_group` method signatures in topology_store.py and match exactly.

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_ha_validation_endpoint.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/network_endpoints.py tests/test_ha_validation_endpoint.py
git commit -m "feat(ha): add HA group validation endpoint"
```

---

### Task 4: Final Verification

**Files:** None (read-only verification)

**Step 1: Run all Phase 10 tests**

```bash
cd backend && python3 -m pytest tests/test_snmp_endpoints.py tests/test_link_metrics_endpoint.py tests/test_ha_validation_endpoint.py -v
```

**Step 2: Run full test suite**

```bash
python3 -m pytest tests/ --tb=line -q 2>&1 | tail -5
```

**Step 3: Verify imports**

```bash
python3 -c "
from src.api.snmp_endpoints import snmp_router
from src.network.snmp_collector import SNMPCollector
from src.network.ha_validation import validate_ha_group
print('SNMP router endpoints:', [r.path for r in snmp_router.routes])
print('All Phase 10 imports verified')
"
```

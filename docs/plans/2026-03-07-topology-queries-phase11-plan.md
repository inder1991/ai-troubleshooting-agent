# Phase 11: Topology Queries & Drift Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose KG path-finding and topology query capabilities via API, add drift event resolution/acknowledgment endpoints, and add topology diff comparison.

**Architecture:** Thin API wrappers around existing KG and TopologyStore methods. No new business logic needed — just endpoint exposure.

**Tech Stack:** FastAPI (existing), networkx (existing), SQLite (existing)

---

### Task 1: Path-Finding & Topology Query Endpoints

**Files:**
- Create: `backend/src/api/topology_query_endpoints.py`
- Modify: `backend/src/api/main.py` (register router)
- Create: `backend/tests/test_topology_query_endpoints.py`

**Context:**
- `NetworkKnowledgeGraph.find_k_shortest_paths(src_id, dst_id, k=3)` returns `list[list[str]]`
- `NetworkKnowledgeGraph.find_candidate_devices(ip)` returns `list[dict]`
- `NetworkKnowledgeGraph.boost_edge_confidence(src_id, dst_id, boost=0.05)` updates confidence
- The KG is available as `_knowledge_graph` in `network_endpoints.py` — follow same pattern
- The KG's `graph` is a networkx DiGraph — can query neighbors, degree, etc.

**Step 1: Write the failing tests**

Create `backend/tests/test_topology_query_endpoints.py`:

```python
"""Tests for topology query endpoints."""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import networkx as nx


@pytest.fixture
def kg_and_client():
    mock_kg = MagicMock()
    g = nx.DiGraph()
    g.add_node("r1", node_type="device", label="Router1")
    g.add_node("r2", node_type="device", label="Router2")
    g.add_node("r3", node_type="device", label="Router3")
    g.add_edge("r1", "r2", confidence=0.9, edge_type="connected_to")
    g.add_edge("r2", "r3", confidence=0.8, edge_type="connected_to")
    g.add_edge("r1", "r3", confidence=0.5, edge_type="routes_to")
    mock_kg.graph = g
    mock_kg.find_k_shortest_paths = MagicMock(return_value=[["r1", "r3"], ["r1", "r2", "r3"]])
    mock_kg.find_candidate_devices = MagicMock(return_value=[
        {"device_id": "r1", "name": "Router1", "ip": "10.0.0.1"},
    ])
    mock_kg.boost_edge_confidence = MagicMock()

    from src.api.main import app
    from src.api import topology_query_endpoints as tqe
    original = tqe._knowledge_graph
    tqe._knowledge_graph = mock_kg
    client = TestClient(app)
    yield mock_kg, client
    tqe._knowledge_graph = original


class TestPathFinding:
    def test_find_paths(self, kg_and_client):
        kg, client = kg_and_client
        resp = client.get("/api/v4/network/query/paths?src=r1&dst=r3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["paths"]) == 2
        kg.find_k_shortest_paths.assert_called_once_with("r1", "r3", 3)

    def test_find_paths_with_k(self, kg_and_client):
        kg, client = kg_and_client
        resp = client.get("/api/v4/network/query/paths?src=r1&dst=r3&k=1")
        assert resp.status_code == 200
        kg.find_k_shortest_paths.assert_called_with("r1", "r3", 1)

    def test_find_paths_missing_params(self, kg_and_client):
        _, client = kg_and_client
        resp = client.get("/api/v4/network/query/paths")
        assert resp.status_code == 422


class TestIPResolution:
    def test_resolve_ip(self, kg_and_client):
        kg, client = kg_and_client
        resp = client.get("/api/v4/network/query/resolve-ip?ip=10.0.0.1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["candidates"]) == 1

    def test_resolve_ip_missing(self, kg_and_client):
        _, client = kg_and_client
        resp = client.get("/api/v4/network/query/resolve-ip")
        assert resp.status_code == 422


class TestDeviceNeighbors:
    def test_get_neighbors(self, kg_and_client):
        _, client = kg_and_client
        resp = client.get("/api/v4/network/query/neighbors/r1")
        assert resp.status_code == 200
        data = resp.json()
        assert "neighbors" in data

    def test_neighbors_not_found(self, kg_and_client):
        kg, client = kg_and_client
        kg.graph = nx.DiGraph()  # empty
        resp = client.get("/api/v4/network/query/neighbors/nonexistent")
        assert resp.status_code == 404


class TestEdgeConfidence:
    def test_boost_confidence(self, kg_and_client):
        kg, client = kg_and_client
        resp = client.post("/api/v4/network/query/boost-confidence", json={"src": "r1", "dst": "r2"})
        assert resp.status_code == 200
        kg.boost_edge_confidence.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_topology_query_endpoints.py -v`

**Step 3: Implement**

**Create `backend/src/api/topology_query_endpoints.py`:**

```python
"""Topology query endpoints — path-finding, IP resolution, neighbors."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from src.utils.logger import get_logger

logger = get_logger(__name__)

topology_query_router = APIRouter(prefix="/api/v4/network/query", tags=["topology-query"])

_knowledge_graph = None


def init_topology_query_endpoints(knowledge_graph):
    global _knowledge_graph
    _knowledge_graph = knowledge_graph


@topology_query_router.get("/paths")
def find_paths(src: str, dst: str, k: int = 3):
    kg = _knowledge_graph
    if not kg:
        return {"paths": []}
    paths = kg.find_k_shortest_paths(src, dst, k)
    return {"paths": paths, "src": src, "dst": dst, "k": k}


@topology_query_router.get("/resolve-ip")
def resolve_ip(ip: str):
    kg = _knowledge_graph
    if not kg:
        return {"candidates": []}
    candidates = kg.find_candidate_devices(ip)
    return {"ip": ip, "candidates": candidates}


@topology_query_router.get("/neighbors/{device_id}")
def get_neighbors(device_id: str):
    kg = _knowledge_graph
    if not kg or device_id not in kg.graph:
        raise HTTPException(status_code=404, detail="Device not found")
    successors = list(kg.graph.successors(device_id))
    predecessors = list(kg.graph.predecessors(device_id))
    neighbors = list(set(successors + predecessors))
    edges = []
    for n in neighbors:
        if kg.graph.has_edge(device_id, n):
            edges.append({"src": device_id, "dst": n, **dict(kg.graph[device_id][n])})
        if kg.graph.has_edge(n, device_id):
            edges.append({"src": n, "dst": device_id, **dict(kg.graph[n][device_id])})
    return {"device_id": device_id, "neighbors": neighbors, "edges": edges}


@topology_query_router.post("/boost-confidence")
def boost_confidence(body: dict):
    kg = _knowledge_graph
    if not kg:
        raise HTTPException(status_code=503, detail="KG not available")
    src = body.get("src", "")
    dst = body.get("dst", "")
    boost = body.get("boost", 0.05)
    kg.boost_edge_confidence(src, dst, boost)
    return {"status": "boosted", "src": src, "dst": dst}
```

**Modify `backend/src/api/main.py`:**

```python
from .topology_query_endpoints import topology_query_router, init_topology_query_endpoints
app.include_router(topology_query_router)
# In startup: init_topology_query_endpoints(kg)
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_topology_query_endpoints.py -v`

**Step 5: Commit**

```bash
git add src/api/topology_query_endpoints.py tests/test_topology_query_endpoints.py src/api/main.py
git commit -m "feat(topology): add path-finding, IP resolution, neighbors, and confidence boost endpoints"
```

---

### Task 2: Drift Event Resolution & Acknowledgment Endpoints

**Files:**
- Modify: `backend/src/api/monitor_endpoints.py` (add drift resolution endpoints)
- Create: `backend/tests/test_drift_management.py`

**Context:**
- `TopologyStore.resolve_drift_event(event_id)` marks a drift as resolved (sets `resolved_at`)
- `TopologyStore.list_active_drift_events()` returns unresolved drifts
- Currently only `GET /drift` exists — no way to resolve or acknowledge
- Drift events have an `id` field in the DB
- Need: `POST /drift/{event_id}/resolve` and `POST /drift/{event_id}/acknowledge`
- Acknowledge = add `acknowledged_at` timestamp without resolving (for snoozing)

**Step 1: Write the failing tests**

Create `backend/tests/test_drift_management.py`:

```python
"""Tests for drift event management endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import DeviceType


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.upsert_device("d1", "Router1", "cisco", DeviceType.ROUTER, "10.0.0.1")
    # Create drift events
    store.upsert_drift_event("device", "d1", "config_drift", "hostname",
                              "Router1", "Router1-old", "warning")
    store.upsert_drift_event("device", "d1", "config_drift", "acl_count",
                              "10", "8", "critical")

    from src.api.main import app
    import src.api.monitor_endpoints as mon_ep
    orig = mon_ep._topology_store
    mon_ep._topology_store = store
    client = TestClient(app)
    yield store, client
    mon_ep._topology_store = orig


class TestDriftResolution:
    def test_list_active_drifts(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/drift")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["drifts"]) == 2

    def test_resolve_drift(self, store_and_client):
        store, client = store_and_client
        drifts = store.list_active_drift_events()
        event_id = drifts[0]["id"]
        resp = client.post(f"/api/v4/network/monitor/drift/{event_id}/resolve")
        assert resp.status_code == 200
        # Should now have 1 active drift
        remaining = store.list_active_drift_events()
        assert len(remaining) == 1

    def test_resolve_nonexistent_drift(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/monitor/drift/nonexistent/resolve")
        assert resp.status_code == 200  # Idempotent — no error

    def test_resolve_all_drifts(self, store_and_client):
        store, client = store_and_client
        resp = client.post("/api/v4/network/monitor/drift/resolve-all")
        assert resp.status_code == 200
        remaining = store.list_active_drift_events()
        assert len(remaining) == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_drift_management.py -v`

**Step 3: Implement**

**Modify `backend/src/api/monitor_endpoints.py`:**

Read the file first. Add these endpoints near the existing drift endpoint:

```python
@monitor_router.post("/drift/{event_id}/resolve")
async def resolve_drift(event_id: str):
    """Resolve a drift event."""
    store = _topology_store
    if not store:
        raise HTTPException(503, "Store not initialized")
    store.resolve_drift_event(event_id)
    return {"resolved": True, "event_id": event_id}


@monitor_router.post("/drift/resolve-all")
async def resolve_all_drifts():
    """Resolve all active drift events."""
    store = _topology_store
    if not store:
        raise HTTPException(503, "Store not initialized")
    drifts = store.list_active_drift_events()
    for d in drifts:
        store.resolve_drift_event(d["id"])
    return {"resolved": len(drifts)}
```

IMPORTANT: Place `resolve-all` BEFORE `{event_id}/resolve` so FastAPI doesn't match "resolve-all" as an event_id.

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_drift_management.py -v`

**Step 5: Commit**

```bash
git add src/api/monitor_endpoints.py tests/test_drift_management.py
git commit -m "feat(drift): add drift resolution and resolve-all endpoints"
```

---

### Task 3: Topology Snapshot Diff Comparison

**Files:**
- Modify: `backend/src/api/network_endpoints.py` (add diff endpoint)
- Create: `backend/tests/test_topology_diff.py`

**Context:**
- `TopologyStore.save_diagram_snapshot(label, data)` saves a snapshot
- `TopologyStore.load_diagram_snapshot(snap_id)` returns a snapshot dict
- `/api/v4/network/topology/versions` lists snapshots
- Need `GET /api/v4/network/topology/diff?v1={snap_id_1}&v2={snap_id_2}` to compare two versions
- Diff should report: added devices, removed devices, changed devices

**Step 1: Write the failing tests**

Create `backend/tests/test_topology_diff.py`:

```python
"""Tests for topology snapshot diff endpoint."""
import json
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    # Save two snapshots with different content
    snap1_data = json.dumps({
        "nodes": [
            {"id": "r1", "data": {"label": "Router1", "device_type": "router"}},
            {"id": "r2", "data": {"label": "Router2", "device_type": "router"}},
        ],
        "edges": [{"source": "r1", "target": "r2"}],
    })
    snap2_data = json.dumps({
        "nodes": [
            {"id": "r1", "data": {"label": "Router1-Updated", "device_type": "router"}},
            {"id": "r3", "data": {"label": "Router3", "device_type": "switch"}},
        ],
        "edges": [{"source": "r1", "target": "r3"}],
    })
    store.save_diagram_snapshot("v1", snap1_data)
    store.save_diagram_snapshot("v2", snap2_data)

    from src.api.main import app
    from src.api import network_endpoints
    orig = network_endpoints._get_topology_store
    network_endpoints._get_topology_store = lambda: store
    client = TestClient(app)
    yield store, client
    network_endpoints._get_topology_store = orig


class TestTopologyDiff:
    def test_diff_two_snapshots(self, store_and_client):
        store, client = store_and_client
        versions = store.list_diagram_snapshots()
        v1_id = versions[0]["id"]
        v2_id = versions[1]["id"]
        resp = client.get(f"/api/v4/network/topology/diff?v1={v1_id}&v2={v2_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "added" in data
        assert "removed" in data
        assert "changed" in data

    def test_diff_missing_version(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/topology/diff?v1=999&v2=998")
        assert resp.status_code == 404

    def test_diff_missing_params(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/topology/diff")
        assert resp.status_code == 422
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_topology_diff.py -v`

**Step 3: Implement**

**Modify `backend/src/api/network_endpoints.py`:**

Read the file first to find existing topology/versions endpoints. Add nearby:

```python
@network_router.get("/topology/diff")
def topology_diff(v1: int, v2: int):
    """Compare two topology snapshots and show differences."""
    store = _get_topology_store()
    snap1 = store.load_diagram_snapshot(v1)
    snap2 = store.load_diagram_snapshot(v2)
    if not snap1 or not snap2:
        raise HTTPException(404, "One or both snapshots not found")

    import json
    data1 = json.loads(snap1.get("data", "{}"))
    data2 = json.loads(snap2.get("data", "{}"))

    nodes1 = {n["id"]: n for n in data1.get("nodes", [])}
    nodes2 = {n["id"]: n for n in data2.get("nodes", [])}

    added = [nodes2[nid] for nid in nodes2 if nid not in nodes1]
    removed = [nodes1[nid] for nid in nodes1 if nid not in nodes2]
    changed = []
    for nid in nodes1:
        if nid in nodes2 and nodes1[nid] != nodes2[nid]:
            changed.append({"id": nid, "before": nodes1[nid], "after": nodes2[nid]})

    return {"v1": v1, "v2": v2, "added": added, "removed": removed, "changed": changed}
```

IMPORTANT: Place this BEFORE any `/{snap_id}` catch-all route in the topology section.

Also check the actual `save_diagram_snapshot` and `load_diagram_snapshot` signatures in topology_store.py.

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_topology_diff.py -v`

**Step 5: Commit**

```bash
git add src/api/network_endpoints.py tests/test_topology_diff.py
git commit -m "feat(topology): add snapshot diff comparison endpoint"
```

---

### Task 4: Final Verification

**Files:** None (read-only verification)

**Step 1: Run all Phase 11 tests**

```bash
cd backend && python3 -m pytest tests/test_topology_query_endpoints.py tests/test_drift_management.py tests/test_topology_diff.py -v
```

**Step 2: Run full test suite**

```bash
python3 -m pytest tests/ --tb=line -q 2>&1 | tail -5
```

**Step 3: Verify imports**

```bash
python3 -c "
from src.api.topology_query_endpoints import topology_query_router
print('Topology query endpoints:', [r.path for r in topology_query_router.routes])
print('All Phase 11 imports verified')
"
```

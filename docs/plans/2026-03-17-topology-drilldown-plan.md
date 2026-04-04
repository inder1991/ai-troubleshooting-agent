# Two-Level Drill-Down Topology — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the unreadable single-canvas topology with a two-level drill-down: Level 1 shows 5 environment cards + WAN links, Level 2 shows devices in clean tiers within one environment.

**Architecture:** New backend endpoint `GET /api/v5/topology/overview` returns environment summaries + WAN connections. Existing V5 endpoint gets `?group=X` filter for Level 2. Frontend: `TopologyOverview.tsx` (Level 1) + `TopologyDetail.tsx` (Level 2). Parent `LiveTopologyViewV2.tsx` manages which level is shown.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/ReactFlow (frontend), existing TopologyStore + EdgeBuilderService.

---

## Task 1: Backend — Overview Endpoint

**Files:**
- Modify: `backend/src/api/topology_v5.py`
- Test: `backend/tests/test_topology_overview.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_topology_overview.py
"""Tests for topology overview endpoint."""
import pytest
from src.api.topology_v5 import build_topology_overview
from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.models import Device as PD, DeviceType


@pytest.fixture
def repo(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    return SQLiteRepository(store)


@pytest.fixture
def seeded_repo(repo):
    store = repo._store
    store.add_device(PD(id="rtr-01", name="rtr-01", device_type=DeviceType.router,
                        management_ip="10.0.0.1", vendor="cisco", role="core"))
    store.add_device(PD(id="csr-01", name="csr-aws-01", device_type=DeviceType.router,
                        management_ip="10.10.0.1", vendor="cisco", role="cloud_gateway",
                        location="us-east-1"))
    store.upsert_neighbor_link(
        link_id="rtr-01:Gi0/0--csr-01:Gi0/0",
        device_id="rtr-01", local_interface="Gi0/0",
        remote_device="csr-01", remote_interface="Gi0/0",
        protocol="bgp", confidence=0.9,
    )
    return repo


class TestTopologyOverview:
    def test_returns_environments(self, seeded_repo):
        result = build_topology_overview(seeded_repo)
        assert "environments" in result
        assert len(result["environments"]) >= 1

    def test_environment_has_required_fields(self, seeded_repo):
        result = build_topology_overview(seeded_repo)
        env = result["environments"][0]
        assert "id" in env
        assert "label" in env
        assert "accent" in env
        assert "device_count" in env
        assert "health_summary" in env

    def test_wan_connections_detected(self, seeded_repo):
        result = build_topology_overview(seeded_repo)
        assert "wan_connections" in result
        assert len(result["wan_connections"]) >= 1

    def test_wan_connection_has_fields(self, seeded_repo):
        result = build_topology_overview(seeded_repo)
        wan = result["wan_connections"][0]
        assert "source" in wan
        assert "target" in wan
        assert "connection_types" in wan
        assert "status" in wan

    def test_empty_topology(self, repo):
        result = build_topology_overview(repo)
        assert result["environments"] == []
        assert result["wan_connections"] == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_topology_overview.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_topology_overview'`

**Step 3: Write implementation**

Add to `backend/src/api/topology_v5.py`:

```python
def build_topology_overview(repo: SQLiteRepository) -> dict:
    """Build Level 1 overview: environment summaries + WAN connections."""
    store = repo._store
    pydantic_devices = store.list_devices()

    # Classify devices into groups
    group_devices: dict[str, list] = {}
    dev_groups: dict[str, str] = {}
    for pdev in pydantic_devices:
        dd = {
            "site_id": pdev.site_id or "", "hostname": pdev.name or "",
            "cloud_provider": pdev.cloud_provider or "",
            "location": pdev.location or "", "region": pdev.region or "",
        }
        g = classify_group(dd)
        group_devices.setdefault(g, []).append(pdev)
        dev_groups[pdev.id] = g

    # Build environment summaries
    environments = []
    for gid, devs in group_devices.items():
        meta = GROUP_META.get(gid, {"label": gid, "accent": "#64748b"})
        health = {"healthy": 0, "degraded": 0, "critical": 0, "initializing": 0}
        # All demo devices start as initializing
        health["initializing"] = len(devs)

        environments.append({
            "id": gid,
            "label": meta["label"],
            "accent": meta["accent"],
            "device_count": len(devs),
            "health_summary": health,
        })

    # Build WAN connections from cross-group edges
    from src.network.repository.edge_builder import EdgeBuilderService
    edge_builder = EdgeBuilderService(store)
    all_edges = edge_builder.build_all()

    # Aggregate cross-group connections by group pair
    pair_data: dict[tuple, dict] = {}
    for e in all_edges:
        g1 = dev_groups.get(e.device_id)
        g2 = dev_groups.get(e.remote_device)
        if g1 and g2 and g1 != g2:
            pair = tuple(sorted([g1, g2]))
            if pair not in pair_data:
                pair_data[pair] = {"types": set(), "devices": []}
            pair_data[pair]["types"].add(e.protocol)
            pair_data[pair]["devices"].append({
                "source": e.device_id, "target": e.remote_device,
            })

    WAN_TYPE_LABELS = {
        "bgp": "BGP", "MPLS": "MPLS", "gre": "GRE Tunnel",
        "ipsec": "IPSec", "l3_p2p": "Direct Connect",
    }

    wan_connections = []
    for (g1, g2), data in pair_data.items():
        type_labels = []
        for t in data["types"]:
            label = WAN_TYPE_LABELS.get(t, t.upper())
            if label not in type_labels:
                type_labels.append(label)
        wan_connections.append({
            "source": g1,
            "target": g2,
            "connection_types": type_labels,
            "status": "up",
            "device_pairs": data["devices"][:3],  # limit to 3
        })

    return {
        "environments": environments,
        "wan_connections": wan_connections,
    }
```

Also add the endpoint:

```python
@router.get("/topology/overview")
def get_topology_overview():
    """Level 1: environment summaries + WAN connections."""
    repo = _get_repo()
    return build_topology_overview(repo)
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_topology_overview.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/api/topology_v5.py backend/tests/test_topology_overview.py
git commit -m "feat(api): topology overview endpoint — environment summaries + WAN links"
```

---

## Task 2: Backend — Group Filter on V5 Endpoint

**Files:**
- Modify: `backend/src/api/topology_v5.py`
- Test: `backend/tests/test_topology_group_filter.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_topology_group_filter.py
"""Tests for group filter on V5 topology endpoint."""
import pytest
from src.api.topology_v5 import build_topology_export
from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.models import Device as PD, DeviceType


@pytest.fixture
def repo_multi_group(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)
    store.add_device(PD(id="rtr-01", name="rtr-01", device_type=DeviceType.router,
                        management_ip="10.0.0.1", vendor="cisco", role="core"))
    store.add_device(PD(id="csr-01", name="csr-aws-01", device_type=DeviceType.router,
                        management_ip="10.10.0.1", vendor="cisco", role="cloud_gateway",
                        location="us-east-1"))
    return repo


class TestGroupFilter:
    def test_filter_onprem_only(self, repo_multi_group):
        result = build_topology_export(repo_multi_group, group="onprem")
        device_nodes = [n for n in result["nodes"] if n.get("type") == "device"]
        assert all(n["data"]["group"] == "onprem" for n in device_nodes)

    def test_filter_aws_only(self, repo_multi_group):
        result = build_topology_export(repo_multi_group, group="aws")
        device_nodes = [n for n in result["nodes"] if n.get("type") == "device"]
        assert all(n["data"]["group"] == "aws" for n in device_nodes)

    def test_no_filter_returns_all(self, repo_multi_group):
        result = build_topology_export(repo_multi_group)
        device_nodes = [n for n in result["nodes"] if n.get("type") == "device"]
        assert len(device_nodes) == 2

    def test_filter_returns_intra_group_edges_only(self, repo_multi_group):
        result = build_topology_export(repo_multi_group, group="onprem")
        # Cross-group edges should be excluded
        device_ids = {n["id"] for n in result["nodes"] if n.get("type") == "device"}
        for edge in result["edges"]:
            assert edge["source"] in device_ids
            assert edge["target"] in device_ids

    def test_filter_includes_cross_group_metadata(self, repo_multi_group):
        """Filtered export should include WAN exit info for navigation badges."""
        result = build_topology_export(repo_multi_group, group="onprem")
        assert "wan_exits" in result
```

**Step 2: Run to verify fail**

**Step 3: Implementation**

Update `build_topology_export()` signature to accept `group` parameter:

```python
def build_topology_export(repo: SQLiteRepository, site_id: str | None = None,
                          group: str | None = None) -> dict:
```

When `group` is set:
1. Filter `pydantic_devices` to only those in the specified group
2. Filter edges to only those between devices in the group
3. Add `wan_exits` list showing cross-group connections from this group's devices
4. Tier layout only within this one group (simpler, cleaner)

The `wan_exits` field:
```python
wan_exits = []
for e in all_edges:
    g1 = dev_groups.get(e.device_id)
    g2 = dev_groups.get(e.remote_device)
    if g1 == group and g2 != group:
        wan_exits.append({
            "target_group": g2,
            "target_group_label": GROUP_META.get(g2, {}).get("label", g2),
            "target_group_accent": GROUP_META.get(g2, {}).get("accent", "#64748b"),
            "source_device": e.device_id,
            "target_device": e.remote_device,
            "connection_type": e.protocol,
        })
    elif g2 == group and g1 != group:
        wan_exits.append({
            "target_group": g1,
            "target_group_label": GROUP_META.get(g1, {}).get("label", g1),
            "target_group_accent": GROUP_META.get(g1, {}).get("accent", "#64748b"),
            "source_device": e.remote_device,
            "target_device": e.device_id,
            "connection_type": e.protocol,
        })
```

Also update the endpoint:
```python
@router.get("/topology")
def get_topology_v5(site_id: str = None, group: str = None):
    repo = _get_repo()
    return build_topology_export(repo, site_id=site_id, group=group)
```

**Step 4: Run tests, Step 5: Commit**

```bash
git commit -m "feat(api): group filter on V5 topology — returns intra-group edges + wan_exits"
```

---

## Task 3: Frontend — TopologyOverview Component (Level 1)

**Files:**
- Create: `frontend/src/components/Observatory/topology/TopologyOverview.tsx`

This is a simple React component — NOT ReactFlow. Just styled divs for environment cards + SVG lines for WAN connections.

**Implementation:**

```typescript
// TopologyOverview.tsx
interface Environment {
  id: string;
  label: string;
  accent: string;
  device_count: number;
  health_summary: { healthy: number; degraded: number; critical: number; initializing: number };
}

interface WanConnection {
  source: string;
  target: string;
  connection_types: string[];
  status: string;
}

interface Props {
  environments: Environment[];
  wanConnections: WanConnection[];
  onSelectEnvironment: (envId: string) => void;
}
```

**Layout:** The 5 environment cards positioned in a hub-spoke pattern:
- On-prem at center (largest card — most devices)
- AWS, Azure, OCI, Branch around it
- SVG lines between cards with WAN type labels

Each card is a clickable div showing:
- Name + accent-colored left border
- Device count
- Health bar (green/amber/red segments proportional to healthy/degraded/critical counts)

WAN lines: straight SVG `<line>` elements with text labels at midpoint.

**Commit:**
```bash
git commit -m "feat(frontend): TopologyOverview — Level 1 environment cards + WAN links"
```

---

## Task 4: Frontend — TopologyDetail Component (Level 2)

**Files:**
- Create: `frontend/src/components/Observatory/topology/TopologyDetail.tsx`

This IS a ReactFlow canvas, but showing only ONE group's devices with intra-group edges.

**Key differences from current LiveTopologyViewV2:**
- Header with back button + environment name
- Tier labels as horizontal dividers (PERIMETER, CORE, DISTRIBUTION, ACCESS)
- Only intra-group edges (no cross-group spaghetti)
- Navigation badges on devices that have cross-group connections
- WAN connections panel at the bottom

**Tier layout:** Simple vertical stack — no force-directed, no radial. Devices sorted by tier, 2 per row, fixed spacing. This is the layout that worked correctly in the two-phase approach but was ruined by cross-group edges. Without cross-group edges, it's clean.

**Navigation badges:** For each device that has `wan_exits`, render small colored pills:
```tsx
{wanExits
  .filter(w => w.source_device === node.id)
  .map(w => (
    <button
      key={w.target_group}
      onClick={() => onNavigate(w.target_group)}
      style={{ background: w.target_group_accent + '20', color: w.target_group_accent,
               border: `1px solid ${w.target_group_accent}40`,
               borderRadius: 3, padding: '1px 5px', fontSize: 9, cursor: 'pointer' }}
    >
      {w.target_group_label}
    </button>
  ))}
```

**WAN connections panel:** Fixed panel at the bottom of the view:
```
── WAN CONNECTIONS ──────────────────────────────
→ AWS via DirectConnect + GRE (rtr-dc-edge-01 → csr-aws-01)    [Go →]
→ Azure via ExpressRoute (rtr-dc-edge-01 → er-gw-01)           [Go →]
→ Branch NY via MPLS (rtr-core-01 → rtr-branch-ny)             [Go →]
```

Each line is clickable → navigates to that environment.

**Commit:**
```bash
git commit -m "feat(frontend): TopologyDetail — Level 2 tier view + navigation badges"
```

---

## Task 5: Frontend — Wire Parent Component + Navigation

**Files:**
- Modify: `frontend/src/components/Observatory/topology/LiveTopologyViewV2.tsx`

Replace the current single-canvas with a level manager:

```typescript
const LiveTopologyViewV2: React.FC = () => {
  const [level, setLevel] = useState<'overview' | 'detail'>('overview');
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [highlightDevice, setHighlightDevice] = useState<string | null>(null);

  // Level 1 data
  const { data: overviewData } = useQuery({
    queryKey: ['topology-overview'],
    queryFn: () => fetch('/api/v5/topology/overview').then(r => r.json()),
    refetchInterval: 60000,
  });

  // Level 2 data (only fetch when a group is selected)
  const { data: detailData } = useQuery({
    queryKey: ['topology-detail', selectedGroup],
    queryFn: () => fetch(`/api/v5/topology?group=${selectedGroup}`).then(r => r.json()),
    enabled: !!selectedGroup,
    refetchInterval: 60000,
  });

  if (level === 'overview') {
    return (
      <TopologyOverview
        environments={overviewData?.environments || []}
        wanConnections={overviewData?.wan_connections || []}
        onSelectEnvironment={(envId) => {
          setSelectedGroup(envId);
          setLevel('detail');
        }}
      />
    );
  }

  return (
    <TopologyDetail
      groupId={selectedGroup!}
      data={detailData}
      highlightDevice={highlightDevice}
      onBack={() => { setLevel('overview'); setSelectedGroup(null); setHighlightDevice(null); }}
      onNavigate={(targetGroup, targetDevice) => {
        setSelectedGroup(targetGroup);
        setHighlightDevice(targetDevice);
        // Level stays 'detail' — just switches group
      }}
    />
  );
};
```

**Keyboard shortcuts:**
- Escape → if in detail, go back to overview. If in overview, close topology.

**Commit:**
```bash
git commit -m "feat(frontend): wire drill-down navigation — overview ↔ detail transitions"
```

---

## Task 6: Full Regression Test

Run all backend tests + manually verify:
1. `/api/v5/topology/overview` returns environment summaries
2. `/api/v5/topology?group=onprem` returns only on-prem devices
3. Frontend overview shows 5 cards with WAN links
4. Click "On-Premises DC" → shows tiered detail view
5. Click `[AWS]` badge on rtr-dc-edge-01 → shows AWS detail
6. Click back → returns to overview

---

## Summary

| Task | What | Layer |
|------|------|-------|
| 1 | Overview endpoint | Backend |
| 2 | Group filter on V5 | Backend |
| 3 | TopologyOverview component | Frontend |
| 4 | TopologyDetail component | Frontend |
| 5 | Wire navigation | Frontend |
| 6 | Regression test | Both |

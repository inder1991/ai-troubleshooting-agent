# Intelligent Cluster Diagnostics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Extend the cluster diagnostic LangGraph pipeline with topology-aware correlation, deterministic causal guard rails, on-demand proactive health scanning, and unified War Room dashboard rendering.

**Architecture:** 4 new LangGraph nodes inserted into the existing fan-out/fan-in graph. Topology snapshot resolver → alert correlator → causal firewall run before the 4 domain agents. Guard formatter runs after synthesize (guard mode only). All new state fields have defaults for backward compatibility. Frontend renders cluster results in the existing War Room grid with conditional rendering based on capability and scan_mode.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, LangGraph, pytest, React 18, TypeScript, Tailwind CSS, Recharts

**Branch:** `feature/intelligent-cluster-diagnostics` (from `main`)

---

## Task 1: New Pydantic State Models

**Files:**
- Modify: `backend/src/agents/cluster/state.py`
- Create: `backend/tests/test_intelligent_state.py`

**Context:** All new pipeline nodes need shared data models. Add them to the existing `state.py` which already has `DomainReport`, `CausalChain`, `ClusterHealthReport`, etc. (lines 1-117). Every new model must have defaults so existing tests don't break.

**Changes:**

Add after `ClusterDiagnosticState` (line 117):

```python
# --- Topology Models ---

class TopologyNode(BaseModel):
    """A node in the K8s resource dependency graph."""
    kind: str                       # pod, deployment, service, node, operator, pvc
    name: str
    namespace: Optional[str] = None
    status: Optional[str] = None    # Ready, NotReady, Running, Pending, Degraded
    node_name: Optional[str] = None # which K8s node hosts this (for pods)
    labels: dict[str, str] = Field(default_factory=dict)

class TopologyEdge(BaseModel):
    """A directed edge in the resource dependency graph."""
    from_key: str                   # "node/worker-1"
    to_key: str                     # "pod/payments/auth-5b6q"
    relation: str                   # hosts, owns, routes_to, mounted_by, manages, depends_on

class TopologySnapshot(BaseModel):
    """Cached K8s resource dependency graph."""
    nodes: dict[str, TopologyNode] = Field(default_factory=dict)
    edges: list[TopologyEdge] = Field(default_factory=list)
    built_at: str = ""              # ISO timestamp
    stale: bool = False
    resource_version: str = ""      # for incremental refresh

# --- Alert Correlator Models ---

class ClusterAlert(BaseModel):
    """A normalized alert/event from the cluster."""
    resource_key: str               # "pod/payments/auth-5b6q"
    alert_type: str                 # "CrashLoopBackOff", "NodeNotReady"
    severity: str = "medium"        # "critical", "warning", "info"
    timestamp: str = ""             # ISO timestamp
    raw_event: dict = Field(default_factory=dict)

class RootCandidate(BaseModel):
    """A hypothesis seed for the synthesizer."""
    resource_key: str               # "node/worker-1"
    hypothesis: str                 # "Node CPU spike caused kubelet unresponsiveness"
    supporting_signals: list[str] = Field(default_factory=list)
    confidence: float = 0.5

class IssueCluster(BaseModel):
    """A group of correlated alerts with root cause hypothesis."""
    cluster_id: str                 # "ic-001"
    alerts: list[ClusterAlert] = Field(default_factory=list)
    root_candidates: list[RootCandidate] = Field(default_factory=list)
    confidence: float = 0.5
    correlation_basis: list[str] = Field(default_factory=list)  # ["topology", "temporal"]
    affected_resources: list[str] = Field(default_factory=list)

# --- Causal Firewall Models ---

class BlockedLink(BaseModel):
    """A causal link hard-blocked by K8s invariant."""
    from_resource: str
    to_resource: str
    reason_code: str                # "violates_topology_direction"
    invariant_id: str               # "INV-CP-006"
    invariant_description: str
    timestamp: str = ""

class CausalAnnotation(BaseModel):
    """A soft annotation on an unlikely causal link."""
    from_resource: str
    to_resource: str
    rule_id: str                    # "SOFT-001"
    confidence_hint: float = 0.5
    reason: str = ""
    supporting_evidence: list[str] = Field(default_factory=list)

class CausalSearchSpace(BaseModel):
    """The constrained causal graph after firewall processing."""
    valid_links: list[dict] = Field(default_factory=list)
    annotated_links: list[dict] = Field(default_factory=list)
    blocked_links: list[BlockedLink] = Field(default_factory=list)
    total_evaluated: int = 0
    total_blocked: int = 0
    total_annotated: int = 0

# --- Guard Mode Models ---

class CurrentRisk(BaseModel):
    """Layer 1: What is broken right now."""
    category: str                   # "operator", "pod", "node", "storage", "network", "cert"
    severity: str = "warning"       # "critical", "warning", "info"
    resource: str = ""              # "operator/dns"
    description: str = ""
    affected_count: int = 0
    issue_cluster_id: Optional[str] = None

class PredictiveRisk(BaseModel):
    """Layer 2: What will break soon."""
    category: str                   # "cert_expiry", "disk_pressure", "cpu_saturation", "quota", "capacity"
    severity: str = "warning"
    resource: str = ""
    description: str = ""
    predicted_impact: str = ""
    time_horizon: str = ""          # "9 days", "~3 days at current growth"
    trend_data: list[dict] = Field(default_factory=list)

class ScanDelta(BaseModel):
    """Layer 3: What changed since last scan."""
    new_risks: list[str] = Field(default_factory=list)
    resolved_risks: list[str] = Field(default_factory=list)
    worsened: list[str] = Field(default_factory=list)
    improved: list[str] = Field(default_factory=list)
    previous_scan_id: Optional[str] = None
    previous_scanned_at: Optional[str] = None

class GuardScanResult(BaseModel):
    """Complete Guard Mode output."""
    scan_id: str = ""
    scanned_at: str = ""
    platform: str = ""
    platform_version: str = ""
    current_risks: list[CurrentRisk] = Field(default_factory=list)
    predictive_risks: list[PredictiveRisk] = Field(default_factory=list)
    delta: ScanDelta = Field(default_factory=ScanDelta)
    overall_health: str = "UNKNOWN"  # "HEALTHY", "DEGRADED", "CRITICAL"
    risk_score: float = 0.0
```

**Tests:** `backend/tests/test_intelligent_state.py`

```python
import pytest
from src.agents.cluster.state import (
    TopologyNode, TopologyEdge, TopologySnapshot,
    ClusterAlert, RootCandidate, IssueCluster,
    BlockedLink, CausalAnnotation, CausalSearchSpace,
    CurrentRisk, PredictiveRisk, ScanDelta, GuardScanResult,
)

def test_topology_snapshot_defaults():
    snap = TopologySnapshot()
    assert snap.nodes == {}
    assert snap.edges == []
    assert snap.stale is False

def test_topology_snapshot_with_data():
    snap = TopologySnapshot(
        nodes={"node/w1": TopologyNode(kind="node", name="w1", status="Ready")},
        edges=[TopologyEdge(from_key="node/w1", to_key="pod/ns/p1", relation="hosts")],
        built_at="2026-03-01T00:00:00Z",
    )
    assert len(snap.nodes) == 1
    assert snap.edges[0].relation == "hosts"

def test_issue_cluster_with_root_candidates():
    ic = IssueCluster(
        cluster_id="ic-001",
        alerts=[ClusterAlert(resource_key="pod/ns/p1", alert_type="CrashLoopBackOff", severity="high")],
        root_candidates=[RootCandidate(resource_key="node/w1", hypothesis="Node failure", confidence=0.82)],
        confidence=0.82,
        correlation_basis=["topology", "temporal"],
    )
    assert len(ic.root_candidates) == 1
    assert ic.root_candidates[0].confidence == 0.82

def test_blocked_link_justification():
    bl = BlockedLink(
        from_resource="pod/ns/p1",
        to_resource="node/w1",
        reason_code="violates_topology_direction",
        invariant_id="INV-CP-006",
        invariant_description="Pod failure cannot cause node failure",
    )
    assert bl.invariant_id == "INV-CP-006"

def test_causal_search_space_counts():
    css = CausalSearchSpace(
        valid_links=[{"from": "a", "to": "b"}],
        blocked_links=[BlockedLink(from_resource="c", to_resource="d", reason_code="x", invariant_id="INV-1", invariant_description="y")],
        total_evaluated=5, total_blocked=1, total_annotated=0,
    )
    assert css.total_evaluated == 5
    assert len(css.blocked_links) == 1

def test_guard_scan_result_defaults():
    gsr = GuardScanResult()
    assert gsr.overall_health == "UNKNOWN"
    assert gsr.current_risks == []
    assert gsr.predictive_risks == []
    assert gsr.delta.new_risks == []

def test_guard_scan_result_three_layers():
    gsr = GuardScanResult(
        scan_id="gs-001",
        current_risks=[CurrentRisk(category="operator", severity="critical", resource="operator/dns", description="DNS degraded", affected_count=3)],
        predictive_risks=[PredictiveRisk(category="cert_expiry", severity="warning", resource="secret/tls", description="Cert expires in 9 days", time_horizon="9 days")],
        delta=ScanDelta(new_risks=["DNS degraded"], resolved_risks=["Memory pressure"]),
        overall_health="DEGRADED",
        risk_score=0.7,
    )
    assert len(gsr.current_risks) == 1
    assert len(gsr.predictive_risks) == 1
    assert len(gsr.delta.new_risks) == 1

def test_existing_models_unaffected():
    """Ensure existing models still work after additions."""
    from src.agents.cluster.state import DomainReport, DomainStatus, CausalChain, ClusterHealthReport
    report = DomainReport(domain="ctrl_plane")
    assert report.status == DomainStatus.PENDING
    hr = ClusterHealthReport(diagnostic_id="test")
    assert hr.platform_health == "UNKNOWN"
```

Run: `cd backend && python3 -m pytest tests/test_intelligent_state.py -v`

---

## Task 2: Topology Snapshot Resolver

**Files:**
- Modify: `backend/src/agents/cluster_client/base.py` (add `build_topology_snapshot` method)
- Modify: `backend/src/agents/cluster_client/mock_client.py` (implement mock topology)
- Create: `backend/src/agents/cluster/topology_resolver.py`
- Create: `backend/tests/test_topology_resolver.py`

**Context:** This is the first new LangGraph node. It queries the cluster client for resource relationships and builds an adjacency-list graph. Uses caching with 5-minute TTL. The `@traced_node` decorator (from `traced_node.py`) handles timeout and error reporting.

**Changes to `base.py`:** Add after `get_routes()` (line ~79):

```python
async def build_topology_snapshot(self) -> "TopologySnapshot":
    """Build resource dependency graph from cluster state."""
    from src.agents.cluster.state import TopologySnapshot
    return TopologySnapshot()
```

**Changes to `mock_client.py`:** Add implementation that builds a mock topology from existing fixture data (nodes, pods, services from the fixtures).

```python
async def build_topology_snapshot(self) -> "TopologySnapshot":
    from src.agents.cluster.state import TopologySnapshot, TopologyNode, TopologyEdge
    nodes_result = await self.list_nodes()
    pods_result = await self.list_pods()

    topo_nodes: dict[str, TopologyNode] = {}
    edges: list[TopologyEdge] = []

    for n in nodes_result.data:
        key = f"node/{n['name']}"
        topo_nodes[key] = TopologyNode(kind="node", name=n["name"], status=n.get("status", "Unknown"))

    for p in pods_result.data:
        ns = p.get("namespace", "default")
        key = f"pod/{ns}/{p['name']}"
        node_name = p.get("node", "")
        topo_nodes[key] = TopologyNode(kind="pod", name=p["name"], namespace=ns, status=p.get("status", "Unknown"), node_name=node_name)
        if node_name:
            edges.append(TopologyEdge(from_key=f"node/{node_name}", to_key=key, relation="hosts"))

    # OpenShift operators
    if self._platform == "openshift":
        ops = await self.get_cluster_operators()
        for op in ops.data:
            key = f"operator/{op['name']}"
            status = "Degraded" if op.get("degraded") else ("Available" if op.get("available") else "Unavailable")
            topo_nodes[key] = TopologyNode(kind="operator", name=op["name"], status=status)

    from datetime import datetime, timezone
    return TopologySnapshot(
        nodes=topo_nodes,
        edges=edges,
        built_at=datetime.now(timezone.utc).isoformat(),
    )
```

**New file `topology_resolver.py`:**

```python
"""Topology Snapshot Resolver — LangGraph node that reads or builds cached topology."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from src.agents.cluster.state import TopologySnapshot
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Module-level cache: session_id -> (TopologySnapshot, timestamp)
_topology_cache: dict[str, tuple[TopologySnapshot, float]] = {}
TOPOLOGY_TTL_SECONDS = 300  # 5 minutes


def _is_fresh(session_id: str) -> bool:
    """Check if cached topology is within TTL."""
    if session_id not in _topology_cache:
        return False
    _, cached_at = _topology_cache[session_id]
    return (time.monotonic() - cached_at) < TOPOLOGY_TTL_SECONDS


def clear_topology_cache(session_id: str) -> None:
    """Clear cached topology for a session. Called on session cleanup."""
    _topology_cache.pop(session_id, None)


@traced_node(timeout_seconds=30)
async def topology_snapshot_resolver(state: dict, config: dict) -> dict:
    """LangGraph node: resolve or build topology snapshot."""
    session_id = state.get("diagnostic_id", "")
    client = config.get("configurable", {}).get("cluster_client")

    if not client:
        logger.warning("No cluster_client in config, skipping topology")
        return {
            "topology_graph": TopologySnapshot(stale=True).model_dump(mode="json"),
            "topology_freshness": {"timestamp": "", "stale": True},
        }

    # Check cache
    if _is_fresh(session_id):
        snapshot, _ = _topology_cache[session_id]
        logger.info("Using cached topology", extra={"action": "cache_hit", "node_count": len(snapshot.nodes)})
        return {
            "topology_graph": snapshot.model_dump(mode="json"),
            "topology_freshness": {"timestamp": snapshot.built_at, "stale": False},
        }

    # Build fresh
    snapshot = await client.build_topology_snapshot()
    _topology_cache[session_id] = (snapshot, time.monotonic())

    logger.info("Built fresh topology", extra={
        "action": "topology_built",
        "node_count": len(snapshot.nodes),
        "edge_count": len(snapshot.edges),
    })

    return {
        "topology_graph": snapshot.model_dump(mode="json"),
        "topology_freshness": {"timestamp": snapshot.built_at, "stale": False},
    }
```

**Tests:** `backend/tests/test_topology_resolver.py`

```python
import pytest
import time
from unittest.mock import AsyncMock, patch

from src.agents.cluster.topology_resolver import (
    topology_snapshot_resolver, _topology_cache, clear_topology_cache, TOPOLOGY_TTL_SECONDS,
)
from src.agents.cluster.state import TopologySnapshot, TopologyNode, TopologyEdge
from src.agents.cluster_client.mock_client import MockClusterClient


def _make_config(client):
    return {"configurable": {"cluster_client": client}}


def _make_state(session_id="test-session"):
    return {"diagnostic_id": session_id, "platform": "openshift"}


@pytest.fixture(autouse=True)
def _clear_cache():
    _topology_cache.clear()
    yield
    _topology_cache.clear()


@pytest.mark.asyncio
async def test_builds_topology_from_client():
    client = MockClusterClient(platform="openshift")
    result = await topology_snapshot_resolver(_make_state(), _make_config(client))
    topo = result["topology_graph"]
    assert len(topo["nodes"]) > 0
    assert result["topology_freshness"]["stale"] is False


@pytest.mark.asyncio
async def test_cache_hit_returns_same_snapshot():
    client = MockClusterClient()
    state = _make_state("cached-session")
    r1 = await topology_snapshot_resolver(state, _make_config(client))
    r2 = await topology_snapshot_resolver(state, _make_config(client))
    assert r1["topology_graph"]["built_at"] == r2["topology_graph"]["built_at"]


@pytest.mark.asyncio
async def test_cache_miss_after_ttl():
    client = MockClusterClient()
    state = _make_state("ttl-session")
    await topology_snapshot_resolver(state, _make_config(client))
    # Manually expire cache
    _topology_cache["ttl-session"] = (_topology_cache["ttl-session"][0], time.monotonic() - TOPOLOGY_TTL_SECONDS - 1)
    r2 = await topology_snapshot_resolver(state, _make_config(client))
    assert r2["topology_freshness"]["stale"] is False


@pytest.mark.asyncio
async def test_no_client_returns_stale():
    result = await topology_snapshot_resolver(_make_state(), {"configurable": {}})
    assert result["topology_freshness"]["stale"] is True


@pytest.mark.asyncio
async def test_clear_cache():
    client = MockClusterClient()
    await topology_snapshot_resolver(_make_state("clear-test"), _make_config(client))
    assert "clear-test" in _topology_cache
    clear_topology_cache("clear-test")
    assert "clear-test" not in _topology_cache


@pytest.mark.asyncio
async def test_openshift_includes_operators():
    client = MockClusterClient(platform="openshift")
    result = await topology_snapshot_resolver(_make_state(), _make_config(client))
    nodes = result["topology_graph"]["nodes"]
    operator_keys = [k for k in nodes if k.startswith("operator/")]
    assert len(operator_keys) > 0


@pytest.mark.asyncio
async def test_edges_have_valid_relations():
    client = MockClusterClient()
    result = await topology_snapshot_resolver(_make_state(), _make_config(client))
    valid_relations = {"hosts", "owns", "routes_to", "mounted_by", "manages", "depends_on"}
    for edge in result["topology_graph"]["edges"]:
        assert edge["relation"] in valid_relations


@pytest.mark.asyncio
async def test_kubernetes_no_operators():
    client = MockClusterClient(platform="kubernetes")
    result = await topology_snapshot_resolver(_make_state(), _make_config(client))
    nodes = result["topology_graph"]["nodes"]
    operator_keys = [k for k in nodes if k.startswith("operator/")]
    assert len(operator_keys) == 0
```

Run: `cd backend && python3 -m pytest tests/test_topology_resolver.py -v`

---

## Task 3: Alert Correlator

**Files:**
- Create: `backend/src/agents/cluster/alert_correlator.py`
- Create: `backend/tests/test_alert_correlator.py`

**Context:** This node takes the topology graph + cluster events and groups alerts into `IssueCluster[]` with root candidate hypothesis seeds. All logic is deterministic — no LLM calls. Uses `@traced_node` for timeout/tracing.

**New file `alert_correlator.py`:**

```python
"""Alert Correlator — groups cluster events into IssueCluster with root candidates."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from src.agents.cluster.state import (
    ClusterAlert, IssueCluster, RootCandidate, TopologySnapshot, TopologyEdge,
)
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Temporal correlation window (seconds)
TEMPORAL_WINDOW = 300  # 5 minutes

# Alert types that indicate problems
_PROBLEM_STATUSES = frozenset({
    "NotReady", "CrashLoopBackOff", "Evicted", "OOMKilled", "Pending",
    "Degraded", "Unavailable", "ImagePullBackOff", "Error", "Failed",
    "DiskPressure", "MemoryPressure", "PIDPressure",
})


def _extract_alerts(state: dict) -> list[ClusterAlert]:
    """Extract problem alerts from topology nodes."""
    topo = state.get("topology_graph", {})
    nodes = topo.get("nodes", {})
    alerts: list[ClusterAlert] = []

    for key, node in nodes.items():
        status = node.get("status", "")
        if status in _PROBLEM_STATUSES:
            alerts.append(ClusterAlert(
                resource_key=key,
                alert_type=status,
                severity="critical" if status in ("NotReady", "OOMKilled", "Degraded", "Unavailable") else "warning",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
    return alerts


def _build_adjacency(edges: list[dict]) -> dict[str, set[str]]:
    """Build bidirectional adjacency map from topology edges."""
    adj: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adj[edge["from_key"]].add(edge["to_key"])
        adj[edge["to_key"]].add(edge["from_key"])
    return adj


def _find_connected_component(start: str, adj: dict[str, set[str]], visited: set[str]) -> set[str]:
    """BFS to find all resources connected to start."""
    component: set[str] = set()
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        component.add(current)
        for neighbor in adj.get(current, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return component


def _pick_root_candidate(cluster_alerts: list[ClusterAlert], adj: dict[str, set[str]]) -> list[RootCandidate]:
    """Pick the most likely root cause from a cluster of alerts."""
    candidates: list[RootCandidate] = []

    # Heuristic: resource with most connections to other alerts is likely root
    alert_keys = {a.resource_key for a in cluster_alerts}
    for alert in cluster_alerts:
        connected_alerts = alert_keys & adj.get(alert.resource_key, set())
        # Nodes and operators are more likely roots than pods
        kind = alert.resource_key.split("/")[0]
        kind_weight = {"node": 0.3, "operator": 0.25, "deployment": 0.1, "service": 0.1}.get(kind, 0.0)
        confidence = min(1.0, 0.4 + len(connected_alerts) * 0.15 + kind_weight)

        signals = [a.alert_type for a in cluster_alerts if a.resource_key in connected_alerts or a.resource_key == alert.resource_key]

        candidates.append(RootCandidate(
            resource_key=alert.resource_key,
            hypothesis=f"{alert.alert_type} on {alert.resource_key} cascading to connected resources",
            supporting_signals=signals,
            confidence=round(confidence, 2),
        ))

    # Return top 2 by confidence
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates[:2]


@traced_node(timeout_seconds=15)
async def alert_correlator(state: dict, config: dict) -> dict:
    """LangGraph node: correlate alerts into IssueCluster groups."""
    topo = state.get("topology_graph", {})
    edges = topo.get("edges", [])

    # Extract alerts from topology
    alerts = _extract_alerts(state)

    if not alerts:
        logger.info("No problem alerts found", extra={"action": "no_alerts"})
        return {"issue_clusters": []}

    # Build adjacency map
    adj = _build_adjacency(edges)

    # Group alerts by topology connectivity
    visited: set[str] = set()
    clusters: list[IssueCluster] = []
    cluster_idx = 0

    # Sort alerts for deterministic ordering
    alerts.sort(key=lambda a: a.resource_key)

    for alert in alerts:
        if alert.resource_key in visited:
            continue

        # Find all connected resources
        component = _find_connected_component(alert.resource_key, adj, set())
        # Filter to only resources that have alerts
        alert_keys_in_component = [a for a in alerts if a.resource_key in component]

        if not alert_keys_in_component:
            alert_keys_in_component = [alert]

        visited.update(a.resource_key for a in alert_keys_in_component)

        # Determine correlation basis
        basis = ["topology"] if len(component) > 1 else []

        # Check namespace affinity
        namespaces = {a.resource_key.split("/")[1] for a in alert_keys_in_component if a.resource_key.count("/") >= 2}
        if len(namespaces) == 1 and len(alert_keys_in_component) > 1:
            basis.append("namespace")

        # Check node affinity
        node_keys = {a.resource_key for a in alert_keys_in_component if a.resource_key.startswith("node/")}
        if node_keys:
            basis.append("node_affinity")

        # Check control plane fan-out
        operator_alerts = [a for a in alert_keys_in_component if a.resource_key.startswith("operator/")]
        if operator_alerts:
            basis.append("control_plane_fan_out")

        if not basis:
            basis = ["temporal"]

        root_candidates = _pick_root_candidate(alert_keys_in_component, adj)

        cluster_idx += 1
        clusters.append(IssueCluster(
            cluster_id=f"ic-{cluster_idx:03d}",
            alerts=alert_keys_in_component,
            root_candidates=root_candidates,
            confidence=root_candidates[0].confidence if root_candidates else 0.5,
            correlation_basis=basis,
            affected_resources=[a.resource_key for a in alert_keys_in_component],
        ))

    logger.info("Alert correlation complete", extra={
        "action": "correlation_complete",
        "total_alerts": len(alerts),
        "cluster_count": len(clusters),
    })

    return {"issue_clusters": [c.model_dump(mode="json") for c in clusters]}
```

**Tests:** `backend/tests/test_alert_correlator.py`

```python
import pytest
from src.agents.cluster.alert_correlator import (
    alert_correlator, _extract_alerts, _build_adjacency,
    _find_connected_component, _pick_root_candidate,
)
from src.agents.cluster.state import ClusterAlert, TopologyNode


def _topo_with_alerts():
    """Topology with 6 alerts: should cluster into 2 groups."""
    return {
        "nodes": {
            "node/worker-1": {"kind": "node", "name": "worker-1", "status": "NotReady"},
            "pod/payments/auth-5b6q": {"kind": "pod", "name": "auth-5b6q", "namespace": "payments", "status": "CrashLoopBackOff", "node_name": "worker-1"},
            "pod/payments/api-7x2": {"kind": "pod", "name": "api-7x2", "namespace": "payments", "status": "Evicted", "node_name": "worker-1"},
            "operator/dns": {"kind": "operator", "name": "dns", "status": "Degraded"},
            "pod/kube-system/coredns-abc": {"kind": "pod", "name": "coredns-abc", "namespace": "kube-system", "status": "CrashLoopBackOff"},
            "pod/monitoring/prom-0": {"kind": "pod", "name": "prom-0", "namespace": "monitoring", "status": "Running"},
        },
        "edges": [
            {"from_key": "node/worker-1", "to_key": "pod/payments/auth-5b6q", "relation": "hosts"},
            {"from_key": "node/worker-1", "to_key": "pod/payments/api-7x2", "relation": "hosts"},
            {"from_key": "operator/dns", "to_key": "pod/kube-system/coredns-abc", "relation": "manages"},
        ],
    }


@pytest.mark.asyncio
async def test_six_alerts_become_two_clusters():
    state = {"topology_graph": _topo_with_alerts(), "diagnostic_id": "test"}
    result = await alert_correlator(state, {})
    clusters = result["issue_clusters"]
    assert len(clusters) == 2  # node cluster + operator cluster


@pytest.mark.asyncio
async def test_no_alerts_returns_empty():
    state = {
        "topology_graph": {
            "nodes": {"pod/ns/p1": {"kind": "pod", "name": "p1", "status": "Running"}},
            "edges": [],
        },
        "diagnostic_id": "test",
    }
    result = await alert_correlator(state, {})
    assert result["issue_clusters"] == []


@pytest.mark.asyncio
async def test_root_candidate_prefers_nodes():
    state = {"topology_graph": _topo_with_alerts(), "diagnostic_id": "test"}
    result = await alert_correlator(state, {})
    # Find the cluster with node/worker-1
    node_cluster = [c for c in result["issue_clusters"] if "node/worker-1" in c["affected_resources"]]
    assert len(node_cluster) == 1
    # Node should be top root candidate
    assert node_cluster[0]["root_candidates"][0]["resource_key"] == "node/worker-1"


@pytest.mark.asyncio
async def test_cluster_has_correlation_basis():
    state = {"topology_graph": _topo_with_alerts(), "diagnostic_id": "test"}
    result = await alert_correlator(state, {})
    for cluster in result["issue_clusters"]:
        assert len(cluster["correlation_basis"]) > 0


@pytest.mark.asyncio
async def test_no_topology_still_works():
    state = {"topology_graph": {}, "diagnostic_id": "test"}
    result = await alert_correlator(state, {})
    assert result["issue_clusters"] == []


@pytest.mark.asyncio
async def test_operator_cluster_has_control_plane_basis():
    state = {"topology_graph": _topo_with_alerts(), "diagnostic_id": "test"}
    result = await alert_correlator(state, {})
    op_cluster = [c for c in result["issue_clusters"] if any("operator/" in r for r in c["affected_resources"])]
    assert len(op_cluster) == 1
    assert "control_plane_fan_out" in op_cluster[0]["correlation_basis"]


def test_extract_alerts_filters_healthy():
    topo = {
        "nodes": {
            "pod/ns/healthy": {"kind": "pod", "name": "healthy", "status": "Running"},
            "pod/ns/sick": {"kind": "pod", "name": "sick", "status": "CrashLoopBackOff"},
        },
    }
    alerts = _extract_alerts({"topology_graph": topo})
    assert len(alerts) == 1
    assert alerts[0].resource_key == "pod/ns/sick"


def test_build_adjacency_bidirectional():
    edges = [{"from_key": "a", "to_key": "b", "relation": "hosts"}]
    adj = _build_adjacency(edges)
    assert "b" in adj["a"]
    assert "a" in adj["b"]
```

Run: `cd backend && python3 -m pytest tests/test_alert_correlator.py -v`

---

## Task 4: Causal Invariants Registry

**Files:**
- Create: `backend/src/agents/cluster/causal_invariants.py`
- Create: `backend/tests/test_causal_invariants.py`

**Context:** The invariant registry defines which causal links are structurally impossible in Kubernetes. This is a pure data + lookup module — no LLM calls, no async. Separated from the firewall node for testability.

**New file `causal_invariants.py`:**

```python
"""K8s causal invariant registry — structurally impossible causal links."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Invariant:
    id: str
    blocked_from_kind: str
    blocked_to_kind: str
    description: str


# Tier 1: Hard blocks — topology direction violations
CAUSAL_INVARIANTS: tuple[Invariant, ...] = (
    Invariant("INV-CP-001", "pod",         "etcd",           "Pod failure cannot cause etcd disk pressure"),
    Invariant("INV-CP-002", "service",     "node",           "Service misconfiguration cannot cause Node NotReady"),
    Invariant("INV-CP-003", "namespace",   "control_plane",  "Namespace deletion cannot crash control plane"),
    Invariant("INV-CP-004", "pvc",         "api_server",     "PVC pending cannot cause API server latency"),
    Invariant("INV-CP-005", "ingress",     "etcd",           "Ingress error cannot cause etcd issues"),
    Invariant("INV-CP-006", "pod",         "node",           "Pod failure cannot cause node failure"),
    Invariant("INV-CP-007", "configmap",   "node",           "ConfigMap change cannot cause node failure"),
    Invariant("INV-NET-001","pod",         "network_plugin", "Pod cannot degrade network plugin"),
    Invariant("INV-STG-001","pod",         "storage_class",  "Pod cannot degrade storage backend"),
    Invariant("INV-STG-002","deployment",  "pv",             "Deployment cannot cause PV failure"),
)

# Pre-built lookup for O(1) checking
_INVARIANT_LOOKUP: dict[tuple[str, str], Invariant] = {
    (inv.blocked_from_kind, inv.blocked_to_kind): inv
    for inv in CAUSAL_INVARIANTS
}


def check_hard_block(from_kind: str, to_kind: str) -> Optional[Invariant]:
    """Check if a causal link from_kind -> to_kind is blocked by an invariant.

    Returns the matching Invariant if blocked, None if allowed.
    """
    return _INVARIANT_LOOKUP.get((from_kind, to_kind))


# Tier 2: Soft rules — context-dependent annotations
@dataclass(frozen=True)
class SoftRule:
    rule_id: str
    description: str
    confidence_hint: float


SOFT_RULES: tuple[SoftRule, ...] = (
    SoftRule("SOFT-001", "Node failure as root cause unlikely — transient blip, no cascading effects observed", 0.2),
    SoftRule("SOFT-002", "CrashLoop unlikely caused by resource exhaustion — usage metrics normal", 0.3),
    SoftRule("SOFT-003", "PVC pending unlikely caused by storage failure — backend responding normally", 0.25),
    SoftRule("SOFT-004", "Certificate expiry not imminent — low urgency", 0.1),
)


def get_soft_rule(rule_id: str) -> Optional[SoftRule]:
    """Look up a soft rule by ID."""
    for rule in SOFT_RULES:
        if rule.rule_id == rule_id:
            return rule
    return None
```

**Tests:** `backend/tests/test_causal_invariants.py`

```python
import pytest
from src.agents.cluster.causal_invariants import (
    check_hard_block, CAUSAL_INVARIANTS, get_soft_rule, SOFT_RULES,
)


def test_pod_to_node_blocked():
    inv = check_hard_block("pod", "node")
    assert inv is not None
    assert inv.id == "INV-CP-006"
    assert "Pod failure cannot cause node failure" in inv.description


def test_node_to_pod_not_blocked():
    """Node failure CAN cause pod failure — this is valid."""
    inv = check_hard_block("node", "pod")
    assert inv is None


def test_pod_to_etcd_blocked():
    inv = check_hard_block("pod", "etcd")
    assert inv is not None
    assert inv.id == "INV-CP-001"


def test_service_to_node_blocked():
    inv = check_hard_block("service", "node")
    assert inv is not None


def test_deployment_to_pod_not_blocked():
    inv = check_hard_block("deployment", "pod")
    assert inv is None


def test_all_invariants_have_unique_ids():
    ids = [inv.id for inv in CAUSAL_INVARIANTS]
    assert len(ids) == len(set(ids))


def test_all_invariants_have_descriptions():
    for inv in CAUSAL_INVARIANTS:
        assert len(inv.description) > 10


def test_soft_rule_lookup():
    rule = get_soft_rule("SOFT-001")
    assert rule is not None
    assert rule.confidence_hint == 0.2


def test_soft_rule_unknown():
    assert get_soft_rule("SOFT-999") is None


def test_all_soft_rules_have_unique_ids():
    ids = [r.rule_id for r in SOFT_RULES]
    assert len(ids) == len(set(ids))


def test_soft_rule_confidence_hints_bounded():
    for rule in SOFT_RULES:
        assert 0.0 <= rule.confidence_hint <= 1.0
```

Run: `cd backend && python3 -m pytest tests/test_causal_invariants.py -v`

---

## Task 5: Causal Firewall Node

**Files:**
- Create: `backend/src/agents/cluster/causal_firewall.py`
- Create: `backend/tests/test_causal_firewall.py`

**Context:** This LangGraph node takes `issue_clusters` + `topology_graph` and produces `causal_search_space`. Uses the invariant registry from Task 4. Checks every potential causal link against Tier 1 (hard block) and Tier 2 (soft annotate). All deterministic.

**New file `causal_firewall.py`:**

```python
"""Causal Firewall — two-tier pre-LLM filtering of causal links."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agents.cluster.causal_invariants import check_hard_block, SOFT_RULES
from src.agents.cluster.state import BlockedLink, CausalAnnotation, CausalSearchSpace
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _extract_kind(resource_key: str) -> str:
    """Extract kind from resource key like 'pod/namespace/name' or 'node/name'."""
    return resource_key.split("/")[0]


def _generate_candidate_links(clusters: list[dict], topo_edges: list[dict]) -> list[dict]:
    """Generate all potential causal links from issue clusters + topology."""
    links: list[dict] = []

    for cluster in clusters:
        alerts = cluster.get("alerts", [])
        # Every pair of alerts in a cluster is a potential causal link
        for i, a in enumerate(alerts):
            for j, b in enumerate(alerts):
                if i >= j:
                    continue
                links.append({
                    "from": a["resource_key"],
                    "to": b["resource_key"],
                    "cluster_id": cluster["cluster_id"],
                })
                links.append({
                    "from": b["resource_key"],
                    "to": a["resource_key"],
                    "cluster_id": cluster["cluster_id"],
                })

    return links


def _check_soft_rules(from_key: str, to_key: str, state: dict) -> CausalAnnotation | None:
    """Check Tier 2 soft rules based on context."""
    topo_nodes = state.get("topology_graph", {}).get("nodes", {})
    from_node = topo_nodes.get(from_key, {})
    to_node = topo_nodes.get(to_key, {})
    from_kind = _extract_kind(from_key)
    to_kind = _extract_kind(to_key)

    # SOFT-001: Node transient — no cascading effects
    if from_kind == "node" and from_node.get("status") == "NotReady":
        # Check if any pods on this node were actually affected
        topo_edges = state.get("topology_graph", {}).get("edges", [])
        hosted_pods = [e["to_key"] for e in topo_edges if e["from_key"] == from_key and e["relation"] == "hosts"]
        problem_pods = [p for p in hosted_pods if topo_nodes.get(p, {}).get("status") in ("Evicted", "CrashLoopBackOff", "OOMKilled")]
        if not problem_pods:
            return CausalAnnotation(
                from_resource=from_key, to_resource=to_key,
                rule_id="SOFT-001", confidence_hint=0.2,
                reason="Node issue with no observed cascading effects on hosted pods",
                supporting_evidence=["no_evictions", "no_pod_failures"],
            )

    # SOFT-003: PVC pending but storage backend healthy
    if from_kind == "pvc" and from_node.get("status") == "Pending":
        return CausalAnnotation(
            from_resource=from_key, to_resource=to_key,
            rule_id="SOFT-003", confidence_hint=0.25,
            reason="PVC pending — check if provisioner or quota issue rather than storage failure",
            supporting_evidence=["pvc_pending_status"],
        )

    return None


@traced_node(timeout_seconds=10)
async def causal_firewall(state: dict, config: dict) -> dict:
    """LangGraph node: two-tier causal link filtering."""
    clusters = state.get("issue_clusters", [])
    topo_edges = state.get("topology_graph", {}).get("edges", [])

    # Generate all candidate links
    candidate_links = _generate_candidate_links(clusters, topo_edges)

    valid: list[dict] = []
    annotated: list[dict] = []
    blocked: list[BlockedLink] = []
    now = datetime.now(timezone.utc).isoformat()

    for link in candidate_links:
        from_kind = _extract_kind(link["from"])
        to_kind = _extract_kind(link["to"])

        # Tier 1: Hard block check
        invariant = check_hard_block(from_kind, to_kind)
        if invariant:
            blocked.append(BlockedLink(
                from_resource=link["from"],
                to_resource=link["to"],
                reason_code="violates_topology_direction",
                invariant_id=invariant.id,
                invariant_description=invariant.description,
                timestamp=now,
            ))
            continue

        # Tier 2: Soft annotation check
        annotation = _check_soft_rules(link["from"], link["to"], state)
        if annotation:
            link_with_annotation = {**link, "annotation": annotation.model_dump(mode="json")}
            annotated.append(link_with_annotation)
            continue

        # Passed both tiers
        valid.append(link)

    search_space = CausalSearchSpace(
        valid_links=valid,
        annotated_links=annotated,
        blocked_links=blocked,
        total_evaluated=len(candidate_links),
        total_blocked=len(blocked),
        total_annotated=len(annotated),
    )

    logger.info("Causal firewall complete", extra={
        "action": "firewall_complete",
        "evaluated": search_space.total_evaluated,
        "blocked": search_space.total_blocked,
        "annotated": search_space.total_annotated,
        "valid": len(valid),
    })

    return {"causal_search_space": search_space.model_dump(mode="json")}
```

**Tests:** `backend/tests/test_causal_firewall.py`

```python
import pytest
from src.agents.cluster.causal_firewall import (
    causal_firewall, _extract_kind, _generate_candidate_links, _check_soft_rules,
)


def _state_with_pod_node_cluster():
    return {
        "diagnostic_id": "test",
        "topology_graph": {
            "nodes": {
                "node/worker-1": {"kind": "node", "name": "worker-1", "status": "NotReady"},
                "pod/ns/p1": {"kind": "pod", "name": "p1", "status": "CrashLoopBackOff", "node_name": "worker-1"},
            },
            "edges": [
                {"from_key": "node/worker-1", "to_key": "pod/ns/p1", "relation": "hosts"},
            ],
        },
        "issue_clusters": [
            {
                "cluster_id": "ic-001",
                "alerts": [
                    {"resource_key": "pod/ns/p1", "alert_type": "CrashLoopBackOff", "severity": "high", "timestamp": "", "raw_event": {}},
                    {"resource_key": "node/worker-1", "alert_type": "NotReady", "severity": "critical", "timestamp": "", "raw_event": {}},
                ],
                "root_candidates": [],
                "confidence": 0.8,
                "correlation_basis": ["topology"],
                "affected_resources": ["pod/ns/p1", "node/worker-1"],
            }
        ],
    }


@pytest.mark.asyncio
async def test_pod_to_node_is_blocked():
    state = _state_with_pod_node_cluster()
    result = await causal_firewall(state, {})
    css = result["causal_search_space"]
    # pod -> node should be blocked
    blocked_pairs = [(b["from_resource"], b["to_resource"]) for b in css["blocked_links"]]
    assert ("pod/ns/p1", "node/worker-1") in blocked_pairs


@pytest.mark.asyncio
async def test_node_to_pod_is_valid():
    state = _state_with_pod_node_cluster()
    result = await causal_firewall(state, {})
    css = result["causal_search_space"]
    # node -> pod should pass (either valid or annotated, not blocked)
    blocked_froms = [b["from_resource"] for b in css["blocked_links"]]
    # node/worker-1 -> pod/ns/p1 should NOT be in blocked
    node_to_pod_blocked = any(
        b["from_resource"] == "node/worker-1" and b["to_resource"] == "pod/ns/p1"
        for b in css["blocked_links"]
    )
    assert not node_to_pod_blocked


@pytest.mark.asyncio
async def test_blocked_link_has_justification():
    state = _state_with_pod_node_cluster()
    result = await causal_firewall(state, {})
    css = result["causal_search_space"]
    for bl in css["blocked_links"]:
        assert bl["invariant_id"].startswith("INV-")
        assert len(bl["invariant_description"]) > 0
        assert bl["reason_code"] == "violates_topology_direction"
        assert bl["timestamp"] != ""


@pytest.mark.asyncio
async def test_empty_clusters_returns_empty_search_space():
    state = {"diagnostic_id": "test", "topology_graph": {"nodes": {}, "edges": []}, "issue_clusters": []}
    result = await causal_firewall(state, {})
    css = result["causal_search_space"]
    assert css["total_evaluated"] == 0
    assert css["total_blocked"] == 0


@pytest.mark.asyncio
async def test_counts_are_consistent():
    state = _state_with_pod_node_cluster()
    result = await causal_firewall(state, {})
    css = result["causal_search_space"]
    total = len(css["valid_links"]) + len(css["annotated_links"]) + len(css["blocked_links"])
    assert css["total_evaluated"] == total


def test_extract_kind():
    assert _extract_kind("pod/ns/name") == "pod"
    assert _extract_kind("node/worker-1") == "node"
    assert _extract_kind("operator/dns") == "operator"
```

Run: `cd backend && python3 -m pytest tests/test_causal_firewall.py -v`

---

## Task 6: Guard Mode Formatter

**Files:**
- Create: `backend/src/agents/cluster/guard_formatter.py`
- Create: `backend/tests/test_guard_formatter.py`

**Context:** This LangGraph node runs only in guard mode (`scan_mode == "guard"`). It takes the synthesizer output + issue clusters + topology and structures the result into the 3-layer `GuardScanResult` (Current Risks / Predictive Risks / Delta). For diagnostic mode, it passes through unchanged.

**New file `guard_formatter.py`:**

```python
"""Guard Mode Formatter — structures diagnostic output into 3-layer health scan."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.agents.cluster.state import (
    GuardScanResult, CurrentRisk, PredictiveRisk, ScanDelta, DomainReport, DomainStatus,
)
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _extract_current_risks(state: dict) -> list[CurrentRisk]:
    """Layer 1: What is broken right now."""
    risks: list[CurrentRisk] = []
    reports = [DomainReport(**r) for r in state.get("domain_reports", [])]

    for report in reports:
        for anomaly in report.anomalies:
            risks.append(CurrentRisk(
                category=report.domain,
                severity=anomaly.severity,
                resource=anomaly.evidence_ref,
                description=anomaly.description,
                affected_count=1,
            ))

    # Add risks from issue clusters
    for cluster in state.get("issue_clusters", []):
        cluster_id = cluster.get("cluster_id", "")
        for alert in cluster.get("alerts", []):
            # Avoid duplicating anomalies already captured from domain reports
            desc = f"{alert.get('alert_type', '')} on {alert.get('resource_key', '')}"
            if not any(r.description == desc for r in risks):
                risks.append(CurrentRisk(
                    category=alert.get("resource_key", "").split("/")[0],
                    severity=alert.get("severity", "warning"),
                    resource=alert.get("resource_key", ""),
                    description=desc,
                    affected_count=1,
                    issue_cluster_id=cluster_id,
                ))

    return risks


def _extract_predictive_risks(state: dict) -> list[PredictiveRisk]:
    """Layer 2: What will break soon. Based on domain report analysis."""
    risks: list[PredictiveRisk] = []
    health_report = state.get("health_report", {})
    if not health_report:
        return risks

    # Extract from remediation long_term items (these hint at future risks)
    remediation = health_report.get("remediation", {})
    for item in remediation.get("long_term", []):
        risks.append(PredictiveRisk(
            category="capacity",
            severity="warning",
            description=item.get("description", ""),
            predicted_impact=item.get("description", ""),
            time_horizon=item.get("effort_estimate", "unknown"),
        ))

    return risks


def _compute_delta(current: GuardScanResult, previous: dict | None) -> ScanDelta:
    """Layer 3: What changed since last scan."""
    if not previous:
        return ScanDelta()

    prev_descriptions = {r.get("description", "") for r in previous.get("current_risks", [])}
    curr_descriptions = {r.description for r in current.current_risks}

    return ScanDelta(
        new_risks=sorted(curr_descriptions - prev_descriptions),
        resolved_risks=sorted(prev_descriptions - curr_descriptions),
        worsened=[],  # TODO: compare severity levels
        improved=[],
        previous_scan_id=previous.get("scan_id"),
        previous_scanned_at=previous.get("scanned_at"),
    )


def _compute_overall_health(risks: list[CurrentRisk]) -> str:
    """Determine overall health from current risks."""
    if any(r.severity == "critical" for r in risks):
        return "CRITICAL"
    if any(r.severity == "warning" for r in risks):
        return "DEGRADED"
    return "HEALTHY"


def _compute_risk_score(current: list[CurrentRisk], predictive: list[PredictiveRisk]) -> float:
    """Simple risk score: 0.0 (healthy) to 1.0 (critical)."""
    score = 0.0
    for r in current:
        score += {"critical": 0.3, "warning": 0.15, "info": 0.05}.get(r.severity, 0.05)
    for r in predictive:
        score += {"critical": 0.2, "warning": 0.1, "info": 0.03}.get(r.severity, 0.03)
    return min(1.0, round(score, 2))


@traced_node(timeout_seconds=15)
async def guard_formatter(state: dict, config: dict) -> dict:
    """LangGraph node: format output for Guard Mode (skip in diagnostic mode)."""
    scan_mode = state.get("scan_mode", "diagnostic")

    if scan_mode != "guard":
        return {}  # No-op for diagnostic mode

    now = datetime.now(timezone.utc).isoformat()
    current_risks = _extract_current_risks(state)
    predictive_risks = _extract_predictive_risks(state)

    scan = GuardScanResult(
        scan_id=f"gs-{uuid.uuid4().hex[:8]}",
        scanned_at=now,
        platform=state.get("platform", ""),
        platform_version=state.get("platform_version", ""),
        current_risks=current_risks,
        predictive_risks=predictive_risks,
        overall_health=_compute_overall_health(current_risks),
        risk_score=_compute_risk_score(current_risks, predictive_risks),
    )

    # Compute delta against previous scan
    previous = state.get("previous_scan")
    scan.delta = _compute_delta(scan, previous)

    logger.info("Guard scan formatted", extra={
        "action": "guard_format",
        "current_risks": len(current_risks),
        "predictive_risks": len(predictive_risks),
        "overall_health": scan.overall_health,
    })

    return {"guard_scan_result": scan.model_dump(mode="json")}
```

**Tests:** `backend/tests/test_guard_formatter.py`

```python
import pytest
from src.agents.cluster.guard_formatter import (
    guard_formatter, _extract_current_risks, _compute_overall_health,
    _compute_risk_score, _compute_delta,
)
from src.agents.cluster.state import CurrentRisk, GuardScanResult


def _state_with_anomalies():
    return {
        "diagnostic_id": "test",
        "scan_mode": "guard",
        "platform": "openshift",
        "platform_version": "4.14",
        "domain_reports": [
            {
                "domain": "ctrl_plane", "status": "SUCCESS", "confidence": 80,
                "anomalies": [
                    {"domain": "ctrl_plane", "anomaly_id": "cp-1", "description": "DNS operator degraded", "evidence_ref": "ev-1", "severity": "critical"},
                ],
                "ruled_out": [], "evidence_refs": [], "truncation_flags": {}, "duration_ms": 500,
            }
        ],
        "issue_clusters": [],
        "health_report": {"remediation": {"immediate": [], "long_term": [{"description": "Increase etcd disk", "effort_estimate": "1 week"}]}},
        "previous_scan": None,
    }


@pytest.mark.asyncio
async def test_guard_mode_produces_result():
    result = await guard_formatter(_state_with_anomalies(), {})
    assert "guard_scan_result" in result
    gsr = result["guard_scan_result"]
    assert gsr["overall_health"] == "CRITICAL"
    assert len(gsr["current_risks"]) > 0


@pytest.mark.asyncio
async def test_diagnostic_mode_is_noop():
    state = {"scan_mode": "diagnostic", "diagnostic_id": "test"}
    result = await guard_formatter(state, {})
    assert result == {}


@pytest.mark.asyncio
async def test_no_scan_mode_defaults_to_noop():
    state = {"diagnostic_id": "test"}
    result = await guard_formatter(state, {})
    assert result == {}


@pytest.mark.asyncio
async def test_predictive_risks_from_remediation():
    result = await guard_formatter(_state_with_anomalies(), {})
    gsr = result["guard_scan_result"]
    assert len(gsr["predictive_risks"]) > 0


@pytest.mark.asyncio
async def test_delta_first_scan_is_empty():
    result = await guard_formatter(_state_with_anomalies(), {})
    delta = result["guard_scan_result"]["delta"]
    assert delta["new_risks"] == []
    assert delta["resolved_risks"] == []
    assert delta["previous_scan_id"] is None


@pytest.mark.asyncio
async def test_delta_detects_new_risks():
    state = _state_with_anomalies()
    state["previous_scan"] = {
        "scan_id": "gs-prev",
        "scanned_at": "2026-03-01T00:00:00Z",
        "current_risks": [],  # no risks before
    }
    result = await guard_formatter(state, {})
    delta = result["guard_scan_result"]["delta"]
    assert len(delta["new_risks"]) > 0


def test_overall_health_critical():
    risks = [CurrentRisk(category="operator", severity="critical", description="x")]
    assert _compute_overall_health(risks) == "CRITICAL"


def test_overall_health_healthy():
    assert _compute_overall_health([]) == "HEALTHY"


def test_risk_score_bounded():
    risks = [CurrentRisk(category="x", severity="critical") for _ in range(10)]
    score = _compute_risk_score(risks, [])
    assert score <= 1.0
```

Run: `cd backend && python3 -m pytest tests/test_guard_formatter.py -v`

---

## Task 7: Rewire LangGraph + Update State

**Files:**
- Modify: `backend/src/agents/cluster/graph.py`
- Modify: `backend/tests/test_cluster_graph.py`

**Context:** Insert the 4 new nodes into the graph. The new flow is: `START → topology_snapshot_resolver → alert_correlator → causal_firewall → [4 agents parallel] → synthesize → guard_formatter → conditional re-dispatch or END`. The `State` TypedDict needs the new fields with `operator.add` where appropriate.

**Changes to `graph.py`:**

Replace the entire file with:

```python
"""LangGraph StateGraph for cluster diagnostics with fan-out/fan-in."""

from __future__ import annotations

import operator
from typing import Any, Annotated, Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from src.agents.cluster.topology_resolver import topology_snapshot_resolver
from src.agents.cluster.alert_correlator import alert_correlator
from src.agents.cluster.causal_firewall import causal_firewall
from src.agents.cluster.ctrl_plane_agent import ctrl_plane_agent
from src.agents.cluster.node_agent import node_agent
from src.agents.cluster.network_agent import network_agent
from src.agents.cluster.storage_agent import storage_agent
from src.agents.cluster.synthesizer import synthesize
from src.agents.cluster.guard_formatter import guard_formatter
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Graph-level ceiling (seconds)
GRAPH_TIMEOUT = 180


class State(TypedDict):
    # Existing fields
    diagnostic_id: str
    platform: str
    platform_version: str
    namespaces: list[str]
    exclude_namespaces: list[str]
    domain_reports: Annotated[list[dict], operator.add]
    causal_chains: Annotated[list[dict], operator.add]
    uncorrelated_findings: Annotated[list[dict], operator.add]
    health_report: Optional[dict]
    phase: str
    re_dispatch_count: int
    re_dispatch_domains: list[str]
    data_completeness: float
    error: Optional[str]
    _trace: Annotated[list[dict], operator.add]
    # New fields
    topology_graph: dict
    topology_freshness: dict
    issue_clusters: list[dict]
    causal_search_space: dict
    scan_mode: str
    previous_scan: Optional[dict]
    guard_scan_result: Optional[dict]


def _should_redispatch(state: dict) -> list[str]:
    """Conditional edge: re-dispatch to all 4 agents or proceed to guard formatter."""
    re_dispatch = state.get("re_dispatch_domains", [])
    count = state.get("re_dispatch_count", 0)
    if re_dispatch and count < 1:
        return ["dispatch_ctrl_plane", "dispatch_node", "dispatch_network", "dispatch_storage"]
    return ["to_guard_formatter"]


def build_cluster_diagnostic_graph():
    """Build and compile the cluster diagnostic LangGraph."""

    graph = StateGraph(State)

    # Add all nodes
    graph.add_node("topology_snapshot_resolver", topology_snapshot_resolver)
    graph.add_node("alert_correlator", alert_correlator)
    graph.add_node("causal_firewall", causal_firewall)
    graph.add_node("ctrl_plane_agent", ctrl_plane_agent)
    graph.add_node("node_agent", node_agent)
    graph.add_node("network_agent", network_agent)
    graph.add_node("storage_agent", storage_agent)
    graph.add_node("synthesize", synthesize)
    graph.add_node("guard_formatter", guard_formatter)

    # Sequential pre-processing: topology -> correlator -> firewall
    graph.add_edge(START, "topology_snapshot_resolver")
    graph.add_edge("topology_snapshot_resolver", "alert_correlator")
    graph.add_edge("alert_correlator", "causal_firewall")

    # Fan-out: firewall -> all 4 agents in parallel
    graph.add_edge("causal_firewall", "ctrl_plane_agent")
    graph.add_edge("causal_firewall", "node_agent")
    graph.add_edge("causal_firewall", "network_agent")
    graph.add_edge("causal_firewall", "storage_agent")

    # All agents fan-in to synthesize
    graph.add_edge("ctrl_plane_agent", "synthesize")
    graph.add_edge("node_agent", "synthesize")
    graph.add_edge("network_agent", "synthesize")
    graph.add_edge("storage_agent", "synthesize")

    # After synthesis: check confidence and optionally re-dispatch
    graph.add_conditional_edges(
        "synthesize",
        _should_redispatch,
        {
            "dispatch_ctrl_plane": "ctrl_plane_agent",
            "dispatch_node": "node_agent",
            "dispatch_network": "network_agent",
            "dispatch_storage": "storage_agent",
            "to_guard_formatter": "guard_formatter",
        },
    )

    # Guard formatter -> END
    graph.add_edge("guard_formatter", END)

    compiled = graph.compile()
    return compiled
```

**Update `routes_v4.py`:** In `run_cluster_diagnosis()` (line ~408), add the new state fields to `initial_state`:

```python
initial_state = {
    # ... existing fields ...
    # New fields
    "topology_graph": {},
    "topology_freshness": {},
    "issue_clusters": [],
    "causal_search_space": {},
    "scan_mode": "diagnostic",  # or "guard" when triggered
    "previous_scan": None,
    "guard_scan_result": None,
}
```

**Tests:** Update `test_cluster_graph.py` to verify the new graph structure:

```python
def test_graph_has_new_nodes():
    graph = build_cluster_diagnostic_graph()
    # The compiled graph should contain all 9 nodes
    assert graph is not None

@pytest.mark.asyncio
async def test_graph_runs_with_new_pipeline():
    """Full pipeline: topology -> correlator -> firewall -> agents -> synthesize -> guard."""
    # Patch all LLM calls
    # Run with MockClusterClient
    # Verify result contains new state fields
    ...
```

Run: `cd backend && python3 -m pytest tests/test_cluster_graph.py -v`

---

## Task 8: Synthesizer Update (Root Candidates + Search Space)

**Files:**
- Modify: `backend/src/agents/cluster/synthesizer.py`
- Create: `backend/tests/test_synthesizer_enhanced.py`

**Context:** Modify the synthesizer's Stage 2 (`_llm_causal_reasoning`) to receive root candidates as anchors and the causal search space instead of raw anomalies. The synthesizer should include annotated links with their confidence hints in the LLM prompt, and exclude blocked links entirely. Stage 1 (merge) and Stage 3 (verdict) stay mostly unchanged.

**Changes to `synthesizer.py`:**

1. Modify `_llm_causal_reasoning()` signature to accept `search_space` and `root_candidates` parameters
2. Update the prompt to include root candidates as hypothesis anchors
3. Include annotated links with `confidence_hint` in the prompt
4. Add `blocked_count` and `annotated_count` to `execution_metadata` in `synthesize()`

**Key prompt change in `_llm_causal_reasoning()`:**

```python
# Add to prompt after anomalies section:
## Pre-Correlated Issue Clusters
{json.dumps(issue_clusters_summary, indent=2)}

## Root Cause Hypothesis Seeds (from deterministic correlator)
{json.dumps(root_candidates, indent=2)}
Use these as starting anchors. Refine or adjust confidence, but do NOT invent new root causes unless evidence strongly supports it.

## Annotated Links (low confidence — investigate carefully)
{json.dumps(annotated_links, indent=2)}
These links passed structural validation but have low confidence based on observed evidence. Weight them accordingly.

## Blocked Links (excluded — do NOT propose these)
{blocked_count} causal links were blocked by structural invariants and excluded from your input.
```

**Tests:** `backend/tests/test_synthesizer_enhanced.py`

Verify:
- Root candidates appear in LLM prompt
- Annotated links appear with confidence hints
- Blocked links are NOT in the prompt
- execution_metadata includes firewall counts

Run: `cd backend && python3 -m pytest tests/test_synthesizer_enhanced.py -v`

---

## Task 9: API Routes Update (Guard Mode + New State)

**Files:**
- Modify: `backend/src/api/routes_v4.py`
- Create: `backend/tests/test_guard_mode_api.py`

**Context:** Add `scan_mode` parameter to `StartSessionRequest`. Update `run_cluster_diagnosis()` to pass new state fields. Update findings endpoint to return guard scan results when in guard mode. Add cleanup for topology cache on session expiry.

**Changes:**

1. Add `scan_mode: str = "diagnostic"` to `StartSessionRequest` model
2. Pass `scan_mode` through to `initial_state` in `run_cluster_diagnosis()`
3. In findings endpoint: if `scan_mode == "guard"` and `guard_scan_result` exists, return it
4. In `_session_cleanup_loop()`: call `clear_topology_cache(session_id)`

**Tests:** `backend/tests/test_guard_mode_api.py`

```python
- test_start_guard_session: POST /session/start with scan_mode="guard"
- test_guard_findings_returns_scan_result: GET /findings returns GuardScanResult
- test_diagnostic_findings_unchanged: existing findings format preserved
- test_default_scan_mode_is_diagnostic: no scan_mode → diagnostic
```

Run: `cd backend && python3 -m pytest tests/test_guard_mode_api.py -v`

---

## Task 10: Frontend TypeScript Types

**Files:**
- Modify: `frontend/src/types/index.ts`

**Context:** Add TypeScript interfaces matching the new backend models. Add after the existing cluster types (around line 629).

**Changes:** Add interfaces for:

```typescript
// --- Topology ---
export interface TopologyNode {
  kind: string;
  name: string;
  namespace?: string;
  status?: string;
  node_name?: string;
}

export interface TopologySnapshot {
  nodes: Record<string, TopologyNode>;
  edges: Array<{ from_key: string; to_key: string; relation: string }>;
  built_at: string;
  stale: boolean;
}

// --- Alert Correlation ---
export interface RootCandidate {
  resource_key: string;
  hypothesis: string;
  supporting_signals: string[];
  confidence: number;
}

export interface IssueCluster {
  cluster_id: string;
  alerts: Array<{ resource_key: string; alert_type: string; severity: string }>;
  root_candidates: RootCandidate[];
  confidence: number;
  correlation_basis: string[];
  affected_resources: string[];
}

// --- Causal Firewall ---
export interface BlockedLink {
  from_resource: string;
  to_resource: string;
  reason_code: string;
  invariant_id: string;
  invariant_description: string;
}

export interface CausalSearchSpace {
  valid_links: Array<Record<string, unknown>>;
  annotated_links: Array<Record<string, unknown>>;
  blocked_links: BlockedLink[];
  total_evaluated: number;
  total_blocked: number;
  total_annotated: number;
}

// --- Guard Mode ---
export interface CurrentRisk {
  category: string;
  severity: 'critical' | 'warning' | 'info';
  resource: string;
  description: string;
  affected_count: number;
  issue_cluster_id?: string;
}

export interface PredictiveRisk {
  category: string;
  severity: 'critical' | 'warning' | 'info';
  resource: string;
  description: string;
  predicted_impact: string;
  time_horizon: string;
  trend_data: Array<Record<string, unknown>>;
}

export interface ScanDelta {
  new_risks: string[];
  resolved_risks: string[];
  worsened: string[];
  improved: string[];
  previous_scan_id?: string;
  previous_scanned_at?: string;
}

export interface GuardScanResult {
  scan_id: string;
  scanned_at: string;
  platform: string;
  platform_version: string;
  current_risks: CurrentRisk[];
  predictive_risks: PredictiveRisk[];
  delta: ScanDelta;
  overall_health: 'HEALTHY' | 'DEGRADED' | 'CRITICAL' | 'UNKNOWN';
  risk_score: number;
}
```

Run: `cd frontend && npx tsc --noEmit`

---

## Task 11: ClusterInfoBanner + DomainAgentStatus Components

**Files:**
- Create: `frontend/src/components/Investigation/cluster/ClusterInfoBanner.tsx`
- Create: `frontend/src/components/Investigation/cluster/DomainAgentStatus.tsx`

**Context:** Left column components for cluster diagnostics. `ClusterInfoBanner` shows platform info and scan mode badge. `DomainAgentStatus` shows 4 domain agent cards with status, duration, and anomaly count. Follow existing War Room design patterns: dark theme (#0f2023), cyan primary (#07b6d5), Material Symbols icons.

**ClusterInfoBanner:** Platform name + version, namespace count, scan mode badge (DIAGNOSTIC blue, GUARD amber). Uses `deployed_code_account` icon.

**DomainAgentStatus:** 4 cards (ctrl_plane, node, network, storage) with:
- Left border: green=SUCCESS, amber=PARTIAL, red=FAILED, gray=PENDING
- Duration in ms
- Anomaly count badge
- Uses `monitor_heart` icon

Run: `cd frontend && npx tsc --noEmit`

---

## Task 12: DomainHealthGrid + FirewallAuditBadge Components

**Files:**
- Create: `frontend/src/components/Investigation/cluster/DomainHealthGrid.tsx`
- Create: `frontend/src/components/Investigation/cluster/FirewallAuditBadge.tsx`

**Context:** Right column (Navigator) components. `DomainHealthGrid` shows 4 compact domain cards with health indicators. `FirewallAuditBadge` shows firewall statistics (evaluated/blocked/annotated) and expands to show blocked link details.

**DomainHealthGrid:** 2x2 grid of compact cards (CP, ND, NW, ST). Each shows: status dot (green/amber/red), confidence bar (0-100), anomaly count.

**FirewallAuditBadge:** Collapsed: "12 evaluated, 3 blocked, 2 annotated". Expanded: list of blocked links with invariant ID and description. Uses `shield` icon.

Run: `cd frontend && npx tsc --noEmit`

---

## Task 13: GuardScanView (3-Layer Health Scan)

**Files:**
- Create: `frontend/src/components/Investigation/cluster/GuardScanView.tsx`
- Create: `frontend/src/components/Investigation/cluster/CurrentRiskCard.tsx`
- Create: `frontend/src/components/Investigation/cluster/PredictiveRiskCard.tsx`
- Create: `frontend/src/components/Investigation/cluster/DeltaSection.tsx`

**Context:** Center column component for Guard Mode. Three collapsible sections with distinct visual identity:
- Current Risks (red header): severity-colored left border cards
- Predictive Risks (amber header): time horizon badge + NeuralChart sparkline
- Delta (blue header): new/resolved/worsened/improved with visual indicators

**GuardScanView:** Container with 3 collapsible sections. Overall health badge (HEALTHY green / DEGRADED amber / CRITICAL red) and risk score bar at top.

**CurrentRiskCard:** Severity left border (critical=red, warning=amber, info=slate). Resource key with `parseResourceEntities`. Affected count badge. Issue cluster link if available.

**PredictiveRiskCard:** Time horizon badge ("9 days", "~3d"). NeuralChart sparkline (mini, 80px height) for trend data. Predicted impact text.

**DeltaSection:** Four subsections: New (+, green), Resolved (strikethrough, gray), Worsened (arrow up, red), Improved (arrow down, green).

Run: `cd frontend && npx tsc --noEmit`

---

## Task 14: IssueClusterView Component

**Files:**
- Create: `frontend/src/components/Investigation/cluster/IssueClusterView.tsx`

**Context:** Center column component for diagnostic mode. Renders pre-correlated issue clusters with root candidates. Shown above the existing CausalForestView.

**IssueClusterView:** Card per cluster with:
- Header: cluster ID + confidence bar + correlation basis badges (topology, temporal, namespace)
- Root candidates section: resource key + hypothesis + confidence
- Alerts list: compact rows with severity dot + resource + alert type
- "Affected resources" count badge

Uses `hub` icon for cluster header. `parseResourceEntities` on hypothesis text.

Run: `cd frontend && npx tsc --noEmit`

---

## Task 15: Layout Integration (Conditional Rendering)

**Files:**
- Modify: `frontend/src/components/Investigation/InvestigationView.tsx`
- Modify: `frontend/src/components/Investigation/EvidenceFindings.tsx`
- Modify: `frontend/src/components/Investigation/Navigator.tsx`
- Modify: `frontend/src/services/api.ts`

**Context:** Wire everything together. The War Room conditionally renders cluster components based on `capability` and `scan_mode`. Add API methods for guard mode sessions.

**Changes to `InvestigationView.tsx`:**
- Pass `capability` and `scanMode` as props to Investigator, EvidenceFindings, Navigator
- Import and render `ClusterInfoBanner` + `DomainAgentStatus` in left column when `capability === 'cluster_diagnostics'`

**Changes to `EvidenceFindings.tsx`:**
- If `scanMode === 'guard'`: render `<GuardScanView />`
- If `capability === 'cluster_diagnostics'`: render `<IssueClusterView />` above `<CausalForestView />`
- Default: existing app diagnostics view (unchanged)

**Changes to `Navigator.tsx`:**
- If `capability === 'cluster_diagnostics'`: render `<DomainHealthGrid />` and `<FirewallAuditBadge />` in right column
- Existing topology SVG and NeuralChart remain

**Changes to `api.ts`:**
- Add `startGuardScan(profileId: string)` method that calls `/session/start` with `scan_mode: "guard"`
- Add guard scan result parsing in `getFindings()`

Run: `cd frontend && npx tsc --noEmit`

---

## Verification

After all 15 tasks:
1. `cd backend && python3 -m pytest --tb=short -q` — all tests pass (existing + ~60 new)
2. `cd frontend && npx tsc --noEmit` — no TypeScript errors
3. Manual: Start cluster diagnostic session → topology resolves → alerts correlate → firewall runs → agents analyze → synthesizer produces causal chains with root candidates
4. Manual: Start guard mode scan → 3-layer output (Current / Predictive / Delta)
5. Manual: Run guard scan twice → delta section shows changes
6. Manual: Check firewall audit badge → shows blocked link count with invariant IDs
7. Manual: Verify existing app diagnostic workflow unchanged

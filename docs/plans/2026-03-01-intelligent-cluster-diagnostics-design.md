# Intelligent Cluster Diagnostics Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan.

**Goal:** Evolve the cluster diagnostic workflow from a reactive debugger into an intelligent SRE companion with graph-based correlation, deterministic guard rails, proactive health scanning, and a unified War Room dashboard.

**Architecture:** Extend the existing LangGraph cluster diagnostic pipeline with 4 new nodes (topology snapshot resolver, alert correlator, causal firewall, guard formatter) inserted before and after the existing domain agents. No new orchestrator — additive extension of the current graph.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, LangGraph, pytest, React 18, TypeScript, Tailwind CSS, Recharts

---

## 1. Capabilities

### 1.1 Multi-Issue Correlation Engine

Transform 6 simultaneous alerts into 2 root cause clusters using a hybrid approach: deterministic topology graph first, LLM refines causality.

**Problem solved:** Naive systems process alerts one-by-one, trigger independent LLM calls, generate conflicting recommendations. This engine groups alerts by topology proximity, temporal correlation, and namespace/node affinity before any LLM reasoning.

### 1.2 Deterministic Guard Rails (Causal Firewall)

Two-tier pre-LLM filtering that reduces hallucination surface area:

- **Tier 1 (Hard Block):** K8s topology invariant violations — structurally impossible causal links removed before LLM sees them.
- **Tier 2 (Soft Annotate):** Context-dependent weak hypotheses annotated with `confidence_hint` and `reason`. LLM sees annotations and reasons with bounded flexibility. LLM can override soft signals — overrides logged for audit.

### 1.3 Proactive Guard Mode (On-Demand Health Scan)

Full health audit triggered on demand from the dashboard. Three-layer output:

- **Current State Risks (What is broken?):** Degraded operators, unhealthy pods, pending PVCs, node issues, cert expiry, network policy gaps.
- **Predictive Risks (What will break?):** Cert expiry countdown, disk/CPU/memory saturation trends, quota nearing limit, etcd disk growth.
- **Delta Since Last Scan (What changed?):** New risks, resolved risks, worsened, improved.

### 1.4 Cluster Dashboard UI (Unified War Room)

Cluster diagnostic results render in the existing War Room grid — no separate page. The War Room adapts based on `capability` and `scan_mode`.

---

## 2. Enhanced Pipeline Architecture

### 2.1 Current Pipeline

```
START → [4 agents parallel] → synthesize → conditional re-dispatch → END
```

### 2.2 New Pipeline

```
START
  ↓
topology_snapshot_resolver    ← Reads cached topology. Validates freshness.
  ↓                             Enriches if stale. No full rebuild per run.
alert_correlator              ← Clusters alerts by topology proximity +
  ↓                             temporal + namespace/node affinity.
                                Emits: IssueCluster[] with root_candidates[]
                                and per-cluster confidence.
causal_firewall               ← Tier 1: Hard-block with justification
  ↓                             {from, to, reason_code, invariant_id, ts}
                                Tier 2: Soft-annotate with confidence_hint
                                Output: causal_search_space (constrained graph)
  ↓
[4 domain agents]             ← Receive: topology snapshot +
  ↓                             issue clusters with root candidates +
                                causal_search_space (not raw topology)
synthesize                    ← Stage 2 LLM receives root_candidates as
  ↓                             anchors + causal_search_space.
                                Refines, doesn't invent.
guard_formatter               ← Guard Mode only: 3-layer output.
  ↓                             Diagnostic mode skips via conditional edge.
END
```

### 2.3 Impact on Existing Workflow

The 4 domain agents don't change their core behavior. They still query cluster_client, send data to LLM, return DomainReport. New context is additive — agents can use pre-clustered alerts or ignore them. If new nodes fail, agents fall back to current blind-query behavior (graceful degradation).

### 2.4 State Additions

All new fields have defaults — backward compatible with existing tests.

```python
# Added to State(TypedDict) in graph.py
topology_graph: dict                    # raw resource dependency adjacency list (preserved)
topology_freshness: dict                # {timestamp, stale: bool}
issue_clusters: list[dict]              # pre-correlated alert groups with root_candidates[]
blocked_links: list[dict]               # Tier 1 audit log with justifications
annotations: list[dict]                 # Tier 2 soft annotations with confidence_hint
causal_search_space: dict               # constrained graph after firewall (what agents see)
previous_scan: Optional[dict]           # last Guard Mode result (for delta)
scan_mode: str                          # "diagnostic" | "guard"
```

---

## 3. Topology Snapshot Resolver

### 3.1 Strategy

Build on first request, cache with TTL, refresh if stale. No full rebuild per diagnostic run.

### 3.2 Graph Structure

```python
{
  "nodes": {
    "node/worker-1": {"kind": "node", "name": "worker-1", "status": "Ready"},
    "pod/payments/auth-5b6q": {"kind": "pod", "name": "auth-5b6q", "namespace": "payments", "node": "worker-1"},
    "deployment/payments/auth": {"kind": "deployment", "name": "auth", "namespace": "payments"},
    "service/payments/auth-svc": {"kind": "service", "name": "auth-svc", "namespace": "payments"},
    "pvc/payments/data-vol": {"kind": "pvc", "name": "data-vol", "namespace": "payments"},
    "operator/dns": {"kind": "operator", "name": "dns", "status": "Degraded"},
  },
  "edges": [
    {"from": "node/worker-1", "to": "pod/payments/auth-5b6q", "relation": "hosts"},
    {"from": "deployment/payments/auth", "to": "pod/payments/auth-5b6q", "relation": "owns"},
    {"from": "service/payments/auth-svc", "to": "pod/payments/auth-5b6q", "relation": "routes_to"},
    {"from": "pvc/payments/data-vol", "to": "pod/payments/auth-5b6q", "relation": "mounted_by"},
    {"from": "operator/dns", "to": "deployment/openshift-dns/dns-default", "relation": "manages"},
  ]
}
```

### 3.3 Edge Types

`hosts`, `owns`, `routes_to`, `mounted_by`, `manages`, `depends_on`

### 3.4 Data Sources

- Nodes → pods (scheduling)
- Deployments/ReplicaSets → pods (ownership via ownerReferences)
- Services → endpoints → pods (routing)
- PVCs → pods (volume mounts)
- ClusterOperators → managed deployments (OpenShift only)

### 3.5 Caching

- Stored in-memory per session with `topology_freshness` timestamp
- TTL: 5 minutes (configurable)
- If stale: incremental refresh via `resourceVersion`
- If cluster unreachable: use last cached snapshot with staleness warning

### 3.6 New ClusterClient Method

```python
async def build_topology_snapshot(self) -> TopologySnapshot:
    """Build resource dependency graph from cluster state."""
```

---

## 4. Alert Correlator

### 4.1 Correlation Strategy (All Deterministic, No LLM)

1. **Topology proximity** — Alerts on resources connected in the dependency graph get grouped.
2. **Temporal correlation** — Events within a configurable window (default 5 minutes) are candidates.
3. **Namespace/Node affinity** — Multiple failures in the same namespace or node are correlated.
4. **Control plane fan-out** — A degraded operator affecting multiple namespaces creates a single cluster with the operator as root candidate.

### 4.2 Data Models

```python
class IssueCluster(BaseModel):
    cluster_id: str                          # "ic-001"
    alerts: list[ClusterAlert]               # grouped alerts/events
    root_candidates: list[RootCandidate]     # hypothesis seeds
    confidence: float                        # 0.0-1.0
    correlation_basis: list[str]             # ["topology", "temporal", "namespace"]
    affected_resources: list[str]            # resource keys from topology

class RootCandidate(BaseModel):
    resource_key: str                        # "node/worker-1"
    hypothesis: str                          # "Node CPU spike caused kubelet unresponsiveness"
    supporting_signals: list[str]            # ["node_not_ready", "pod_evictions"]
    confidence: float                        # 0.72

class ClusterAlert(BaseModel):
    resource_key: str                        # "pod/payments/auth-5b6q"
    alert_type: str                          # "CrashLoopBackOff"
    severity: str                            # "high"
    timestamp: str                           # ISO timestamp
    raw_event: dict                          # original event data
```

### 4.3 Example: 6 Alerts → 2 Clusters

```
Alert 1: Node worker-1 NotReady
Alert 2: Pod auth-5b6q CrashLoop (on worker-1)
Alert 3: Pod payment-api-7x2 evicted (on worker-1)
Alert 4: etcd disk pressure
Alert 5: Ingress 503 errors
Alert 6: PVC data-vol pending

Correlator output:
  Cluster A (confidence: 0.82):
    alerts: [1, 2, 3]
    root_candidates: [{resource: "node/worker-1",
                       hypothesis: "Node failure cascading to hosted pods"}]
    correlation_basis: ["topology", "temporal"]

  Cluster B (confidence: 0.65):
    alerts: [4, 5, 6]
    root_candidates: [{resource: "etcd",
                       hypothesis: "etcd pressure causing API latency,
                                    cascading to ingress + storage"}]
    correlation_basis: ["temporal", "control_plane_fan_out"]
```

---

## 5. Causal Firewall (Two-Tier)

### 5.1 Tier 1: Hard Block (K8s Invariants)

Structural impossibilities — effects cannot cause their own causes.

```python
CAUSAL_INVARIANTS = [
    ("INV-CP-001", "pod",         "etcd",           "Pod failure cannot cause etcd disk pressure"),
    ("INV-CP-002", "service",     "node",           "Service misconfig cannot cause Node NotReady"),
    ("INV-CP-003", "namespace",   "control_plane",  "Namespace deletion cannot crash control plane"),
    ("INV-CP-004", "pvc",         "api_server",     "PVC pending cannot cause API server latency"),
    ("INV-CP-005", "ingress",     "etcd",           "Ingress error cannot cause etcd issues"),
    ("INV-CP-006", "pod",         "node",           "Pod failure cannot cause node failure"),
    ("INV-CP-007", "configmap",   "node",           "ConfigMap change cannot cause node failure"),
    ("INV-NET-001","pod",         "network_plugin",  "Pod cannot degrade network plugin"),
    ("INV-STG-001","pod",         "storage_class",   "Pod cannot degrade storage backend"),
    ("INV-STG-002","deployment",  "pv",             "Deployment cannot cause PV failure"),
]
```

Each blocked link is logged:

```python
class BlockedLink(BaseModel):
    from_resource: str          # "pod/payments/auth-5b6q"
    to_resource: str            # "node/worker-1"
    reason_code: str            # "violates_topology_direction"
    invariant_id: str           # "INV-CP-006"
    invariant_description: str  # "Pod failure cannot cause node failure"
    timestamp: str              # ISO
```

### 5.2 Tier 2: Soft Annotate (Context-Dependent)

```python
SOFT_RULES = [
    {
        "rule_id": "SOFT-001",
        "condition": "node_not_ready_duration < 10s AND no_pod_evictions AND no_rescheduling",
        "annotation": "Node failure as root cause unlikely — transient, no cascading effects",
        "confidence_hint": 0.2,
    },
    {
        "rule_id": "SOFT-002",
        "condition": "crashloop_present AND resource_usage_stable",
        "annotation": "CrashLoop unlikely caused by resource exhaustion — usage normal",
        "confidence_hint": 0.3,
    },
    {
        "rule_id": "SOFT-003",
        "condition": "pvc_pending AND storage_backend_healthy",
        "annotation": "PVC pending unlikely caused by storage failure — backend healthy",
        "confidence_hint": 0.25,
    },
    {
        "rule_id": "SOFT-004",
        "condition": "cert_expiry > 30d",
        "annotation": "Certificate expiry not imminent — low urgency",
        "confidence_hint": 0.1,
    },
]
```

Each annotation:

```python
class CausalAnnotation(BaseModel):
    from_resource: str
    to_resource: str
    rule_id: str                    # "SOFT-001"
    confidence_hint: float          # 0.2
    reason: str                     # "no correlated state transition observed"
    supporting_evidence: list[str]  # what signals the rule checked
```

### 5.3 Output: Causal Search Space

```python
class CausalSearchSpace(BaseModel):
    valid_links: list[dict]         # links that passed both tiers
    annotated_links: list[dict]     # Tier 2 flagged (passed with warnings)
    blocked_links: list[BlockedLink]  # Tier 1 removed (audit only)
    total_evaluated: int
    total_blocked: int
    total_annotated: int
```

The synthesizer's Stage 2 LLM receives `valid_links` + `annotated_links` (with annotations inline). `blocked_links` are excluded from LLM input — audit only.

---

## 6. Guard Mode (On-Demand Health Scan)

### 6.1 Trigger

New parameter on existing `/api/v4/sessions` endpoint:

```python
scan_mode: Literal["diagnostic", "guard"] = "diagnostic"
```

### 6.2 Output Models

```python
class GuardScanResult(BaseModel):
    scan_id: str
    scanned_at: str
    platform: str
    platform_version: str
    current_risks: list[CurrentRisk]        # Layer 1: What is broken?
    predictive_risks: list[PredictiveRisk]  # Layer 2: What will break?
    delta: ScanDelta                        # Layer 3: What changed?
    overall_health: str                     # "HEALTHY" | "DEGRADED" | "CRITICAL"
    risk_score: float                       # 0.0-1.0

class CurrentRisk(BaseModel):
    category: str           # "operator", "pod", "node", "storage", "network", "cert"
    severity: str           # "critical", "warning", "info"
    resource: str           # "operator/dns"
    description: str        # "DNS operator degraded: CoreDNS pods unavailable"
    affected_count: int
    issue_cluster_id: Optional[str]

class PredictiveRisk(BaseModel):
    category: str           # "cert_expiry", "disk_pressure", "cpu_saturation", "quota", "capacity"
    severity: str
    resource: str
    description: str        # "Certificate expires in 9 days"
    predicted_impact: str   # "TLS handshake failures for all ingress routes"
    time_horizon: str       # "9 days", "~3 days at current growth"
    trend_data: list[dict]  # time series for NeuralChart rendering

class ScanDelta(BaseModel):
    new_risks: list[str]
    resolved_risks: list[str]
    worsened: list[str]
    improved: list[str]
    previous_scan_id: Optional[str]
    previous_scanned_at: Optional[str]
```

### 6.3 Predictive Data Sources

| Forecast | Data Source | Method |
|----------|-----------|--------|
| Cert expiry | TLS secret annotations | Direct date comparison |
| Disk pressure | `node_filesystem_avail_bytes` | Linear regression (24h) |
| CPU saturation | `node_cpu_seconds_total` | Trendline extrapolation |
| Memory saturation | `node_memory_MemAvailable_bytes` | Trendline extrapolation |
| Quota exhaustion | `kubectl get resourcequota` | Usage / limit ratio |
| etcd disk growth | `etcd_mvcc_db_total_size_in_bytes` | Linear regression |
| Node capacity | Scheduled vs allocatable | Headroom percentage |

### 6.4 Delta Tracking

- Each `GuardScanResult` stored in `previous_scan` state field
- Subsequent scans compare current vs previous
- First scan: empty delta

---

## 7. Cluster Dashboard UI (Unified War Room)

### 7.1 Layout

Same 3-column War Room grid, adapted by `capability` and `scan_mode`:

```
┌─────────────────┬──────────────────────┬───────────────────┐
│  Investigator   │  Evidence Findings   │    Navigator      │
│  (col-3)        │  (col-5)             │    (col-4)        │
│                 │                      │                   │
│  ClusterInfo    │  Guard Mode:         │  Topology SVG     │
│  - Platform     │   Current Risks      │                   │
│  - Version      │   Predictive Risks   │  DomainHealthGrid │
│  - Namespaces   │   Delta              │  ┌──┬──┬──┬──┐    │
│                 │                      │  │CP│ND│NW│ST│    │
│  DomainAgent    │  Diagnostic Mode:    │  └──┴──┴──┴──┘    │
│  Status         │   Issue Clusters     │                   │
│  ┌──────────┐   │   Causal Forest      │  NeuralChart      │
│  │ctrl_plane│   │                      │  (trend forecasts)│
│  │node      │   │                      │                   │
│  │network   │   │                      │  FirewallAudit    │
│  │storage   │   │                      │  Badge            │
│  └──────────┘   │                      │                   │
│                 │                      │                   │
│  Chat Drawer    │                      │                   │
└─────────────────┴──────────────────────┴───────────────────┘
```

### 7.2 New Components

**Left column:**
- `ClusterInfoBanner` — platform, version, namespace count, scan mode badge
- `DomainAgentStatus` — 4 agent cards (running/success/failed, duration, anomaly count)

**Center column:**
- Guard Mode: `GuardScanView` with 3 collapsible sections
  - `CurrentRiskCard` — severity-colored border, resource ref, affected count
  - `PredictiveRiskCard` — time horizon badge, NeuralChart sparkline, predicted impact
  - `DeltaSection` — new/resolved/worsened/improved with visual indicators
- Diagnostic Mode: `IssueClusterView` + existing `CausalForestView`

**Right column:**
- `DomainHealthGrid` — 4 compact cards with health indicator and confidence bar
- `FirewallAuditBadge` — "12 evaluated, 3 blocked, 2 annotated" (expandable)

### 7.3 Conditional Rendering

```tsx
if (scanMode === 'guard') return <GuardScanView />;
if (capability === 'cluster_diagnostics') return <><IssueClusterView /><CausalForestView /></>;
return <>{/* existing app diagnostics */}</>;
```

---

## 8. Error Handling

| Failure | Behavior |
|---------|----------|
| Topology resolver can't reach cluster | Use stale cache with warning. No cache → agents run blind (current behavior). |
| Alert correlator finds no alerts | `issue_clusters = []`. Agents run normally. Guard Mode: "No current risks." |
| Causal firewall has no matching invariants | All links pass through. No degradation. |
| Domain agent times out | Existing `@traced_node` handles it. Synthesizer works with partial data. |
| No Prometheus for predictions | Skip forecasts. "Predictive analysis unavailable." |
| No previous scan for delta | "First scan — no previous data." |
| LLM overrides soft annotation | Logged in `execution_metadata.overridden_annotations[]`. |

---

## 9. Test Strategy

| Module | Tests | Focus |
|--------|-------|-------|
| `test_topology_resolver.py` | 10 | Graph construction, edge types, caching, staleness, incremental refresh |
| `test_alert_correlator.py` | 12 | Temporal grouping, topology proximity, namespace affinity, root candidates, 6→2 scenario |
| `test_causal_firewall.py` | 15 | Hard-block invariants, soft-rule annotations, audit log, justification fields |
| `test_guard_formatter.py` | 10 | 3-layer output, delta computation, empty states, predictive formatting |
| `test_causal_search_space.py` | 8 | Valid/blocked/annotated link classification, totals |
| `test_pipeline_integration.py` | 5 | Full graph run: 6 alerts → 2 clusters → firewall → agents → synthesize → guard format |
| Frontend | `tsc --noEmit` | TypeScript compilation, empty state rendering |

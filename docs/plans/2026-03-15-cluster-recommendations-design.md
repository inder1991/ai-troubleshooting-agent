# Cluster Recommendations, Proactive Analysis & Cost Optimization — Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add proactive risk detection, cost optimization, workload right-sizing, and service dependency analysis to cluster diagnostics — with a persistent Cluster Registry page and an enriched Recommendations tab in the War Room.

**Architecture:** Six new deterministic pipeline nodes (proactive_analyzer, cost_analyzer, workload_optimizer, service_dependency_builder, slo_analyzer, recommendation_engine) running after the existing diagnostic intelligence pipeline. A new Cluster Registry page reads persisted recommendations. All zero LLM cost.

---

## Pipeline Overview

```
existing diagnostic intelligence pipeline (findings, hypotheses, lifecycle)
          ↓
proactive_analyzer        → 8 extensible checks (cert, API, image, security, quota, PDB, patch, HPA)
          ↓
cost_analyzer             → per-node cost, idle capacity, namespace spend, instance optimization
          ↓
workload_optimizer        → right-size CPU/memory, HPA/VPA recommendations, burst detection
          ↓
service_dependency_builder → service topology from K8s + Prometheus + traces
          ↓
slo_analyzer              → SLO violations, error budgets, burn rate, business impact
          ↓
recommendation_engine     → combine, score, prioritize all findings into actionable recommendations
```

---

## Section 1: Data Models

### ProactiveFinding

```python
class ProactiveFinding(BaseModel):
    finding_id: str
    check_type: str           # "cert_expiry" | "deprecated_api" | "image_stale" | ...
    severity: str             # "critical" | "high" | "medium" | "low"
    lifecycle_state: str      # Reuses IssueState: ACTIVE_DISRUPTION, WORSENING, NEW, EXISTING

    title: str                # "TLS certificate expiring in 7 days"
    description: str
    affected_resources: list[str]
    affected_workloads: list[str]

    days_until_impact: int    # 7 for cert, -1 for already impacting
    estimated_savings_usd: float  # 0 for risk, 450 for cost

    recommendation: str
    commands: list[str]
    dry_run_command: str
    rollback_command: str

    confidence: float         # 0.0-1.0
    source: str               # "proactive" | "cost" | "workload" | "slo"
    cloud_provider: str       # "aws" | "gcp" | "azure" | "on_prem"
```

### CostRecommendation

```python
class CostRecommendation(BaseModel):
    recommendation_id: str
    scope: str                 # "cluster" | "namespace" | "workload"

    current_instance_types: list[dict]
    current_monthly_cost: float

    recommended_instance_types: list[dict]
    projected_monthly_cost: float
    projected_savings_usd: float
    projected_savings_pct: float

    idle_capacity_pct: float
    affected_workloads: list[str]
    constraints_respected: list[str]  # "node affinity", "taints", "PDBs"
    risk_level: str            # "safe" | "caution" | "review"
```

### WorkloadRecommendation

```python
class WorkloadRecommendation(BaseModel):
    recommendation_id: str
    workload: str              # "deployment/production/api-gateway"
    namespace: str

    current_cpu_request: str
    current_cpu_limit: str
    current_memory_request: str
    current_memory_limit: str

    recommended_cpu_request: str
    recommended_memory_request: str

    p95_cpu_usage: str
    p95_memory_usage: str
    observation_window: str    # "7d"

    cpu_reduction_pct: float
    memory_reduction_pct: float

    recommended_hpa: dict | None
    recommended_vpa: dict | None

    risk_level: str
    throttling_risk: bool
```

### ServiceDependencyGraph

```python
class ServiceNode(BaseModel):
    service_name: str
    namespace: str
    kind: str                  # "Deployment" | "StatefulSet"
    endpoints_ready: int
    endpoints_total: int
    p99_latency_ms: float
    error_rate_pct: float
    slo_target: float | None
    slo_remaining_budget: float | None

class ServiceEdge(BaseModel):
    from_service: str
    to_service: str
    call_rate_rpm: float
    p99_latency_ms: float
    error_rate_pct: float

class ServiceDependencyGraph(BaseModel):
    nodes: dict[str, ServiceNode]
    edges: list[ServiceEdge]
```

### SLOViolation

```python
class SLOViolation(BaseModel):
    service: str
    slo_type: str              # "availability" | "latency" | "error_rate"
    target: float
    current: float
    budget_remaining_pct: float
    burn_rate: float
    time_to_exhaustion: str
    impacted_upstream: list[str]
```

### ScoredRecommendation (output of recommendation_engine)

```python
class ScoredRecommendation(BaseModel):
    recommendation_id: str
    category: str              # "critical_risk" | "optimization" | "security" | "known_issue"
    score: float               # 0-100, for sorting
    title: str
    description: str
    severity: str
    source: str                # "proactive" | "cost" | "workload" | "slo"
    affected_resources: list[str]
    affected_workloads: list[str]

    # Actionable
    commands: list[str]
    dry_run_command: str
    rollback_command: str
    yaml_diff: str | None

    # Impact
    days_until_impact: int
    estimated_savings_usd: float
    risk_level: str
    confidence: float
```

---

## Section 2: Proactive Check Framework

### Extensible Check Definition

```python
PROACTIVE_CHECKS = [
    {
        "check_id": "cert_expiry",
        "name": "TLS Certificate Expiry",
        "category": "risk",
        "data_source": "list_tls_secrets",
        "severity_rules": [
            {"condition": "days_to_expiry <= 7", "severity": "critical", "state": "ACTIVE_DISRUPTION"},
            {"condition": "days_to_expiry <= 14", "severity": "high", "state": "WORSENING"},
            {"condition": "days_to_expiry <= 30", "severity": "medium", "state": "NEW"},
        ],
        "recommendation": "Renew certificate before expiry",
        "commands": ["kubectl get secret {resource} -n {namespace} -o jsonpath='{.data.tls\\.crt}' | base64 -d | openssl x509 -enddate -noout"],
    },
    # ... 7 more checks
]
```

### 8 Starter Checks

| # | Check | Category | Severity Logic |
|---|-------|----------|----------------|
| 1 | Cert expiry | risk | <=7d critical, <=14d high, <=30d medium |
| 2 | Deprecated API versions | compliance | Removed in next minor = critical, deprecated = medium |
| 3 | Image staleness | security | :latest tag = medium, no digest = low, >90d = medium |
| 4 | Security posture | security | Root = high, privileged = critical, default SA = medium |
| 5 | Quota pressure | risk | >90% used = high, >80% = medium |
| 6 | PDB blocking | risk | Blocks drain = high, blocks upgrade = critical |
| 7 | Node OS patch gap | compliance | >30d = medium, >60d = high |
| 8 | HPA/VPA at limits | risk | At max + unmet target = high |

### New Cluster Client Methods

```python
async def list_tls_secrets(self, namespace: str = "") -> QueryResult
async def list_resource_quotas(self, namespace: str = "") -> QueryResult
async def get_node_os_info(self) -> QueryResult
async def list_api_versions_in_use(self) -> QueryResult
```

### Adding a New Check

To add check #9, an engineer only needs to:
1. Add an entry to PROACTIVE_CHECKS list
2. Add a data source method to ClusterClient if needed
3. No pipeline changes, no graph changes, no frontend changes

---

## Section 3: Cost Analyzer

### Inputs

- Node list with instance types (from list_nodes)
- Pod resource requests/limits (from list_pods)
- Prometheus metrics for actual CPU/memory utilization
- Cloud provider pricing (AWS/GCP/Azure pricing tables, manual for on-prem)

### Cost Calculation

```python
MODEL_PRICING = {
    "aws": {
        "m5.large": {"cpu": 2, "memory_gi": 8, "monthly_usd": 70},
        "m5.xlarge": {"cpu": 4, "memory_gi": 16, "monthly_usd": 140},
        "m5.2xlarge": {"cpu": 8, "memory_gi": 32, "monthly_usd": 280},
        "r5.large": {"cpu": 2, "memory_gi": 16, "monthly_usd": 91},
        # ... more types
    },
    "gcp": { ... },
    "azure": { ... },
}
```

### Idle Capacity Calculation

```
idle_cpu_pct = 1 - (sum(actual_cpu_usage) / sum(node_cpu_capacity))
idle_memory_pct = 1 - (sum(actual_memory_usage) / sum(node_memory_capacity))
idle_cost = total_cost * max(idle_cpu_pct, idle_memory_pct)
```

### Instance Optimization Simulation

Like Datadog: simulate the cluster on different instance shapes, respecting:
- Node and pod affinities / anti-affinities
- Taints and tolerations
- Pod disruption budgets
- Topology spread constraints

Output: recommended instance mix with projected cost + savings.

---

## Section 4: Workload Optimizer

### Right-Sizing Logic

```python
def compute_right_size(workload, metrics, observation_window="7d"):
    p95_cpu = query_prometheus(f"quantile_over_time(0.95, container_cpu_usage[{observation_window}])")
    p95_memory = query_prometheus(f"quantile_over_time(0.95, container_memory_usage[{observation_window}])")

    # Add 20% headroom above p95
    recommended_cpu = p95_cpu * 1.2
    recommended_memory = p95_memory * 1.2

    # Check if reduction is safe
    throttling_risk = recommended_cpu < current_cpu_request * 0.5  # Aggressive reduction

    return WorkloadRecommendation(
        recommended_cpu_request=format_cpu(recommended_cpu),
        recommended_memory_request=format_memory(recommended_memory),
        risk_level="safe" if not throttling_risk else "caution",
    )
```

### HPA Recommendations

```python
def recommend_hpa(workload, metrics):
    # Only recommend if: no HPA exists AND load varies > 2x between peak/trough
    peak = max(cpu_samples)
    trough = min(cpu_samples)
    if peak / max(trough, 0.001) > 2.0:
        return {
            "min_replicas": max(1, current_replicas // 2),
            "max_replicas": current_replicas * 3,
            "target_cpu_pct": 70,
        }
    return None
```

### VPA Recommendations

```python
def recommend_vpa(workload, metrics):
    # Only recommend if: large gap between request and actual usage
    if current_request > p95_usage * 3:  # Over-provisioned by 3x
        return {
            "mode": "Auto",
            "min_cpu": format_cpu(p95_usage * 0.8),
            "max_cpu": format_cpu(p95_usage * 2.0),
        }
    return None
```

---

## Section 5: Service Dependency & SLO Analyzer

### Data Sources (graceful degradation)

| Source | Available? | What it provides |
|--------|-----------|-----------------|
| Distributed traces | Optional | Service-to-service call graph + latency |
| Prometheus | Optional | Golden signals (latency, errors, throughput) |
| K8s Services | Always | Service topology (which deployments back which services) |

Falls back gracefully: traces > Prometheus > K8s-only topology.

### SLO Analysis

If Prometheus metrics available:
- Calculate error rate, latency percentiles
- Compare against SLO targets (from annotations or config)
- Compute burn rate and time-to-exhaustion
- Link to upstream services affected

### Integration with Diagnostics

When a hypothesis says "Node memory pressure caused pod evictions", the service layer adds:
"This caused payment-api latency to spike from 50ms to 2.3s, affecting checkout-service (120 rpm). SLO budget at -0.7% (violated)."

---

## Section 6: Recommendation Engine

### Scoring Formula

```python
score = (
    SEVERITY_WEIGHT[severity] * 25        # critical=100, high=75, medium=50, low=25
    + days_factor * 15                     # Closer to impact = higher
    + savings_factor * 10                  # More savings = higher
    + confidence * 10                      # Higher confidence = higher
    + blast_radius * 5                     # More affected = higher
)

# days_factor: 1.0 if <=7 days, 0.7 if <=14, 0.4 if <=30, 0.1 if >30
# savings_factor: min(1.0, savings_usd / 500)
```

### Category Assignment

```python
if severity in ("critical", "high") and source == "proactive":
    category = "critical_risk"
elif source in ("cost", "workload"):
    category = "optimization"
elif source == "slo":
    category = "critical_risk" if budget_remaining < 0 else "optimization"
elif category_from_check == "security":
    category = "security"
else:
    category = "known_issue"
```

### Output

Top recommendations sorted by score, grouped by category for the UI:
1. Critical Risks (max 5)
2. Workload Optimization (max 10)
3. Security & Compliance (max 5)
4. Known Issues (remaining, compact)

---

## Section 7: Cluster Registry Page

### Location

New sidebar item: Infrastructure → Clusters

### Layout

Full-width rows (not card grid), one per cluster:
- Left: cluster name, provider badge (EKS/GKE/AKS/K8s), node count, pod count
- Center: health status, monthly cost, idle %, recommendation count
- Right: action buttons (Recommendations, Run Scan, ··· menu)
- Critical clusters get red left border, high idle gets amber cost text

### Fleet Summary Footer

Total clusters, total nodes, total pods, total monthly cost, total potential savings.

### Filters

By cloud provider, by health status, by cost threshold, text search. Sort by cost (default), idle %, recommendations, health.

### Data Source

Reads from Integration profiles + persisted recommendation snapshots (stored every 24h or after each scan).

---

## Section 8: War Room Enhancements

### New Tabs

```
[ Diagnostics ]  [ Recommendations ]  [ Cost Analysis ]
```

### Recommendations Tab

Tiered sections:
- **Critical Risks** — cert expiry, deprecated APIs, PDB blocking (red/amber border, prominent)
- **Workload Optimization** — right-sizing, HPA/VPA (savings badge, medium weight)
- **Security & Compliance** — root pods, :latest tags (yellow border)
- **Known Issues** — low priority, compact, muted

Per-recommendation: title, affected resources, evidence, commands, risk level, savings/days-until-impact, confidence, action buttons (Dry Run, Copy, View YAML Diff).

### Cost Analysis Tab

- Before/after instance mix comparison table
- Idle capacity bars (CPU, memory)
- Top idle namespaces list
- Constrained workloads (can't be moved) with reason
- Constraints respected list

### Export + Digest

- Dossier export (JSON + text)
- Scheduled email digest (future phase)

---

## Section 9: New Backend Files

| File | Purpose | Timeout | LLM Cost |
|------|---------|---------|----------|
| `proactive_analyzer.py` | 8 extensible checks | 15s | Zero |
| `cost_analyzer.py` | Node cost, idle capacity, instance optimization | 10s | Zero |
| `workload_optimizer.py` | Right-size, HPA/VPA recommendations | 10s | Zero |
| `service_dependency.py` | Build service graph from K8s + Prometheus + traces | 10s | Zero |
| `slo_analyzer.py` | SLO violations, burn rate, error budgets | 5s | Zero |
| `recommendation_engine.py` | Score, prioritize, categorize all findings | 5s | Zero |
| `cloud_pricing.py` | Multi-cloud instance pricing tables | N/A | Zero |

### New Frontend Files

| File | Purpose |
|------|---------|
| `ClusterRegistryPage.tsx` | Cluster fleet list with actions |
| `ClusterRegistryRow.tsx` | Individual cluster row |
| `RecommendationsTab.tsx` | Recommendations view in War Room |
| `CostAnalysisTab.tsx` | Cost breakdown view in War Room |
| `RecommendationCard.tsx` | Per-recommendation display |
| `CostComparisonTable.tsx` | Before/after instance mix |
| `IdleCapacityBars.tsx` | CPU/memory utilization bars |

### Modified Files

| File | Changes |
|------|---------|
| `state.py` | New models (ProactiveFinding, CostRecommendation, WorkloadRecommendation, etc.) |
| `graph.py` | 6 new nodes, wired after recommendation_engine |
| `ClusterWarRoom.tsx` | Tab bar, new tab views |
| `routes_v4.py` | New endpoints for cluster registry + recommendations |
| `SidebarNav.tsx` | Add "Clusters" under Infrastructure |
| `App.tsx` | Route for cluster registry page |
| `base.py` / `k8s_client.py` | 4 new cluster client methods |

---

## Section 10: Phase Plan

### Phase 1 (Ship First)

- Proactive checks framework + 8 starter checks
- Cost analysis (idle %, per-namespace, instance mix)
- Workload right-sizing (CPU/memory with p95 evidence)
- Cluster Registry page
- Recommendations tab in War Room
- Cost Analysis tab in War Room

### Phase 2 (Add Later)

- HPA/VPA auto-recommendations
- Service dependency graph (from traces)
- SLO analyzer
- Cloud pricing API integration (real-time)
- Cost trend charts (7d/30d)
- Scheduled email digests
- Custom check definitions (user-defined)
- Auto-apply (YAML generation + PR)
- Business impact scoring

---

## Expected Impact

| Metric | Improvement |
|--------|-------------|
| Proactive risk coverage | 8 checks covering cert, API, security, capacity |
| Cost visibility | Per-cluster, per-namespace, per-workload cost + idle % |
| Right-sizing accuracy | p95-based with 20% headroom, risk assessment |
| Time to detect cert expiry | 30 days before (was: after outage) |
| Operator trust | Constraints explicitly shown, dry-run before apply |
| LLM cost for recommendations | Zero (all deterministic) |

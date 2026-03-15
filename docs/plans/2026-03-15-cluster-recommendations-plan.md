# Cluster Recommendations & Cost Optimization — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add proactive risk detection, cost analysis, workload right-sizing, and a Cluster Registry page — separate from the existing diagnostic War Room which stays untouched.

**Architecture:** Six new backend pipeline nodes (all deterministic, zero LLM cost) that run independently of the diagnostic scan. New Cluster Registry page in sidebar. New Cluster Recommendations page for per-cluster proactive analysis. War Room unchanged.

**Tech Stack:** Python/Pydantic (backend), FastAPI (API), React/TypeScript/Tailwind (frontend)

**Design doc:** `docs/plans/2026-03-15-cluster-recommendations-design.md`

---

## Task 1: State Models for Recommendations

**Files:**
- Modify: `backend/src/agents/cluster/state.py`

Add all new Pydantic models after the existing models:

- `ProactiveFinding` — finding_id, check_type, severity, lifecycle_state, title, description, affected_resources, affected_workloads, days_until_impact, estimated_savings_usd, recommendation, commands, dry_run_command, rollback_command, confidence, source, cloud_provider
- `CostRecommendation` — recommendation_id, scope, current/recommended instance types, current/projected cost, savings, idle_capacity_pct, affected_workloads, constraints_respected, risk_level
- `WorkloadRecommendation` — recommendation_id, workload, namespace, current/recommended CPU/memory requests/limits, p95 usage, reduction percentages, recommended HPA/VPA, risk_level, throttling_risk
- `ScoredRecommendation` — recommendation_id, category, score, title, description, severity, source, affected_resources, affected_workloads, commands, dry_run_command, rollback_command, yaml_diff, days_until_impact, estimated_savings_usd, risk_level, confidence
- `ClusterCostSummary` — cluster_id, provider, node_count, pod_count, current_monthly_cost, projected_monthly_cost, projected_savings_usd, idle_cpu_pct, idle_memory_pct, instance_breakdown (list of dicts)
- `ClusterRecommendationSnapshot` — cluster_id, cluster_name, provider, scanned_at, proactive_findings (list), cost_summary, workload_recommendations (list), scored_recommendations (list), total_savings_usd, critical_count, optimization_count

**Commit:** `feat(state): add recommendation and cost analysis models`

---

## Task 2: Cloud Pricing Tables

**Files:**
- Create: `backend/src/agents/cluster/cloud_pricing.py`

Static pricing tables for AWS, GCP, Azure instance types. On-prem uses manual cost-per-node.

```python
CLOUD_PRICING = {
    "aws": {
        "m5.large": {"vcpu": 2, "memory_gi": 8, "monthly_usd": 70},
        "m5.xlarge": {"vcpu": 4, "memory_gi": 16, "monthly_usd": 140},
        "m5.2xlarge": {"vcpu": 8, "memory_gi": 32, "monthly_usd": 280},
        "m5.4xlarge": {"vcpu": 16, "memory_gi": 64, "monthly_usd": 560},
        "c5.large": {"vcpu": 2, "memory_gi": 4, "monthly_usd": 62},
        "c5.xlarge": {"vcpu": 4, "memory_gi": 8, "monthly_usd": 124},
        "r5.large": {"vcpu": 2, "memory_gi": 16, "monthly_usd": 91},
        "r5.xlarge": {"vcpu": 4, "memory_gi": 32, "monthly_usd": 182},
        "t3.medium": {"vcpu": 2, "memory_gi": 4, "monthly_usd": 30},
        "t3.large": {"vcpu": 2, "memory_gi": 8, "monthly_usd": 60},
    },
    "gcp": {
        "e2-standard-2": {"vcpu": 2, "memory_gi": 8, "monthly_usd": 49},
        "e2-standard-4": {"vcpu": 4, "memory_gi": 16, "monthly_usd": 97},
        "e2-standard-8": {"vcpu": 8, "memory_gi": 32, "monthly_usd": 194},
        "n2-standard-2": {"vcpu": 2, "memory_gi": 8, "monthly_usd": 71},
        "n2-standard-4": {"vcpu": 4, "memory_gi": 16, "monthly_usd": 142},
    },
    "azure": {
        "Standard_D2s_v3": {"vcpu": 2, "memory_gi": 8, "monthly_usd": 70},
        "Standard_D4s_v3": {"vcpu": 4, "memory_gi": 16, "monthly_usd": 140},
        "Standard_D8s_v3": {"vcpu": 8, "memory_gi": 32, "monthly_usd": 280},
        "Standard_E2s_v3": {"vcpu": 2, "memory_gi": 16, "monthly_usd": 91},
    },
}

def get_node_monthly_cost(provider: str, instance_type: str) -> float
def estimate_cluster_cost(provider: str, nodes: list[dict]) -> ClusterCostSummary
def detect_provider_from_node(node: dict) -> str  # Infer from labels/annotations
```

**Commit:** `feat(cluster): add multi-cloud pricing tables`

---

## Task 3: New Cluster Client Methods

**Files:**
- Modify: `backend/src/agents/cluster_client/base.py`
- Modify: `backend/src/agents/cluster_client/k8s_client.py`
- Modify: `backend/src/agents/cluster_client/mock_client.py`

Add 4 new methods to ClusterClient:

```python
async def list_tls_secrets(self, namespace: str = "") -> QueryResult:
    """List secrets of type kubernetes.io/tls with certificate expiry dates."""

async def list_resource_quotas(self, namespace: str = "") -> QueryResult:
    """List ResourceQuotas with usage vs hard limits."""

async def get_node_os_info(self) -> QueryResult:
    """List nodes with kernel version, OS image, creation date."""

async def list_api_versions_in_use(self) -> QueryResult:
    """Scan resources for apiVersion usage to detect deprecated APIs."""
```

K8s client implementations:
- `list_tls_secrets`: List secrets with `type=kubernetes.io/tls`, decode cert, extract expiry with `cryptography` or `openssl` subprocess
- `list_resource_quotas`: Use CoreV1Api `list_resource_quota_for_all_namespaces`
- `get_node_os_info`: From existing `list_nodes` data, add `kernelVersion`, `osImage`, `creationTimestamp`
- `list_api_versions_in_use`: Query common resource types and collect apiVersion values

Mock client: return realistic test data with one expiring cert, one near-quota namespace, one deprecated API.

**Commit:** `feat(cluster-client): add TLS, quota, OS info, API version methods`

---

## Task 4: Proactive Analyzer

**Files:**
- Create: `backend/src/agents/cluster/proactive_analyzer.py`

8 extensible checks, each defined as config + evaluator:

```python
PROACTIVE_CHECKS = [
    {"check_id": "cert_expiry", ...},
    {"check_id": "deprecated_api", ...},
    {"check_id": "image_staleness", ...},
    {"check_id": "security_posture", ...},
    {"check_id": "quota_pressure", ...},
    {"check_id": "pdb_blocking", ...},
    {"check_id": "node_os_patch", ...},
    {"check_id": "hpa_vpa_limits", ...},
]
```

Core functions:
- `get_enabled_checks() -> list[dict]`
- `fetch_check_data(client, check) -> list[dict]` — calls the appropriate cluster client method
- `evaluate_check(check, data) -> list[ProactiveFinding]` — applies severity rules to data
- `run_proactive_analysis(client) -> list[ProactiveFinding]` — runs all checks, returns sorted findings

Each check evaluator is a function: `_check_cert_expiry(data)`, `_check_deprecated_api(data)`, etc.

NOT a LangGraph node — this runs independently from the diagnostic pipeline, called directly by the API.

**Commit:** `feat(cluster): add proactive analyzer with 8 checks`

---

## Task 5: Cost Analyzer

**Files:**
- Create: `backend/src/agents/cluster/cost_analyzer.py`

Functions:
- `compute_cluster_cost(nodes, provider) -> ClusterCostSummary` — per-node cost using cloud_pricing, total, instance breakdown
- `compute_idle_capacity(nodes, pods, prometheus_client) -> dict` — CPU/memory requested vs used, idle percentages
- `compute_namespace_costs(pods, nodes, provider) -> list[dict]` — per-namespace cost breakdown sorted by idle %
- `simulate_instance_optimization(nodes, pods, provider) -> CostRecommendation` — simulate bin-packing on smaller instances respecting constraints (affinities, taints, PDBs)
- `run_cost_analysis(client, provider) -> dict` — orchestrates all cost functions

**Commit:** `feat(cluster): add cost analyzer with idle capacity and instance optimization`

---

## Task 6: Workload Optimizer

**Files:**
- Create: `backend/src/agents/cluster/workload_optimizer.py`

Functions:
- `compute_right_size(workload, pods, prometheus_client) -> WorkloadRecommendation` — p95 CPU/memory + 20% headroom vs current requests
- `recommend_hpa(workload, pods, prometheus_client) -> dict | None` — recommend HPA if load varies >2x
- `recommend_vpa(workload, pods) -> dict | None` — recommend VPA if over-provisioned >3x
- `detect_burst_workloads(pods, prometheus_client) -> list[dict]` — identify workloads with high variance
- `run_workload_optimization(client) -> list[WorkloadRecommendation]` — analyze all deployments/statefulsets

**Commit:** `feat(cluster): add workload optimizer with right-sizing and HPA/VPA recommendations`

---

## Task 7: Recommendation Engine

**Files:**
- Create: `backend/src/agents/cluster/recommendation_engine.py`

Functions:
- `score_recommendation(finding) -> float` — severity weight + days factor + savings factor + confidence + blast radius
- `categorize_recommendations(findings) -> dict[str, list]` — group into critical_risk, optimization, security, known_issue
- `build_recommendations(proactive_findings, cost_summary, workload_recs) -> list[ScoredRecommendation]` — combine all sources, score, sort, categorize
- `build_recommendation_snapshot(cluster_id, cluster_name, provider, proactive, cost, workload) -> ClusterRecommendationSnapshot` — full snapshot for persistence

**Commit:** `feat(cluster): add recommendation engine with scoring and categorization`

---

## Task 8: API Endpoints

**Files:**
- Modify: `backend/src/api/routes_v4.py`

New endpoints:

```python
@router_v4.get("/clusters")
async def list_clusters():
    """List all connected clusters with health and recommendation summaries."""
    # Read from integration profiles + cached recommendation snapshots

@router_v4.get("/clusters/{cluster_id}/recommendations")
async def get_cluster_recommendations(cluster_id: str):
    """Get full recommendations for a cluster (cached or fresh scan)."""

@router_v4.post("/clusters/{cluster_id}/recommendations/refresh")
async def refresh_recommendations(cluster_id: str):
    """Trigger a fresh recommendation scan for a cluster."""
    # Runs proactive_analyzer + cost_analyzer + workload_optimizer
    # Stores snapshot in memory/DB

@router_v4.get("/clusters/{cluster_id}/cost")
async def get_cluster_cost(cluster_id: str):
    """Get cost breakdown for a cluster."""
```

Also add a background scheduler that refreshes recommendations every 24h (using existing session/background task pattern).

**Commit:** `feat(api): add cluster registry and recommendation endpoints`

---

## Task 9: Frontend Types

**Files:**
- Modify: `frontend/src/types/index.ts`

Add TypeScript types:
- `ProactiveFinding`
- `CostRecommendation`
- `WorkloadRecommendation`
- `ScoredRecommendation`
- `ClusterCostSummary`
- `ClusterRecommendationSnapshot`
- `ClusterRegistryEntry` — id, name, provider, node_count, pod_count, health_status, monthly_cost, idle_pct, recommendation_count, critical_count, last_scan_at

Add to `services/api.ts`:
- `listClusters() -> ClusterRegistryEntry[]`
- `getClusterRecommendations(clusterId) -> ClusterRecommendationSnapshot`
- `refreshClusterRecommendations(clusterId) -> void`
- `getClusterCost(clusterId) -> ClusterCostSummary`

**Commit:** `feat(frontend): add recommendation and cluster registry types`

---

## Task 10: Cluster Registry Page

**Files:**
- Create: `frontend/src/components/ClusterRegistry/ClusterRegistryPage.tsx`
- Create: `frontend/src/components/ClusterRegistry/ClusterRow.tsx`

**ClusterRegistryPage.tsx:**
- Fetches from `GET /clusters`
- Header: "Cluster Fleet" with total cost and refresh button
- Filters: cloud provider, health status, cost threshold, text search
- Sort: by cost (default), idle %, recommendations, health
- Fleet summary footer: total clusters, nodes, pods, cost, potential savings

**ClusterRow.tsx:**
- Full-width row per cluster (not a card grid)
- Left: name, provider badge (EKS/GKE/AKS/K8s), node count, pod count
- Center: health status dot, monthly cost, idle %, recommendation count
- Right: [Recommendations] [Run Scan] [···] buttons
- Visual treatment: critical = red left border, high idle = amber cost text, offline = dimmed

**Empty state:** "No clusters connected. Add a Kubernetes cluster in Integrations."

**Commit:** `feat(frontend): add Cluster Registry page`

---

## Task 11: Cluster Recommendations Page

**Files:**
- Create: `frontend/src/components/ClusterRegistry/ClusterRecommendationsPage.tsx`
- Create: `frontend/src/components/ClusterRegistry/RecommendationCard.tsx`
- Create: `frontend/src/components/ClusterRegistry/CostBreakdownPanel.tsx`
- Create: `frontend/src/components/ClusterRegistry/IdleCapacityBars.tsx`

**ClusterRecommendationsPage.tsx:**
- Fetches from `GET /clusters/{id}/recommendations`
- Header: cluster name, provider, last scan time, [Refresh] [Export] [Run Diagnostic] buttons
- Top banner: "N Critical Risks | N Optimizations | $X potential savings"
- 4 tiered sections:
  1. Critical Risks — red/amber left border, prominent
  2. Workload Optimization — savings badge per item
  3. Security & Compliance — yellow border
  4. Known Issues — muted, compact
- Cost breakdown panel at bottom (or right column)

**RecommendationCard.tsx:**
- Title with severity dot
- Affected resources + workloads
- Evidence (metrics, observation window)
- Commands with [Dry Run] [Copy] buttons
- Risk level + confidence + savings/days-until-impact
- Not identical to War Room's RemediationCard — different data shape

**CostBreakdownPanel.tsx:**
- Before/after instance mix table
- Total current vs projected cost with savings
- Constraints respected list

**IdleCapacityBars.tsx:**
- CPU and memory utilization bars
- Top idle namespaces list

**Commit:** `feat(frontend): add Cluster Recommendations page with cost breakdown`

---

## Task 12: Navigation Wiring

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout/SidebarNav.tsx`

**SidebarNav.tsx:**
- Add `'cluster-registry'` to Infrastructure group children:
  ```
  { id: 'cluster-registry', label: 'Clusters', icon: 'cloud_circle' }
  ```

**App.tsx:**
- Add `'cluster-registry'` and `'cluster-recommendations'` to ViewState type
- Add routes:
  ```tsx
  {viewState === 'cluster-registry' && <ClusterRegistryPage ... />}
  {viewState === 'cluster-recommendations' && <ClusterRecommendationsPage ... />}
  ```
- Wire navigation: ClusterRow "Recommendations" → `setViewState('cluster-recommendations')` with cluster ID
- Wire navigation: ClusterRow "Run Scan" → existing cluster diagnostic flow

**Commit:** `feat(nav): wire Cluster Registry and Recommendations pages`

---

## Implementation Order

**Group A (independent, parallel):** Tasks 1, 2, 3 — models, pricing, client methods
**Group B (depends on A):** Tasks 4, 5, 6 — proactive analyzer, cost analyzer, workload optimizer
**Group C (depends on B):** Task 7 — recommendation engine
**Group D (depends on C):** Task 8 — API endpoints
**Group E (independent of backend):** Tasks 9, 10, 11 — frontend types + pages
**Group F (depends on D + E):** Task 12 — navigation wiring

Total: 12 tasks. War Room untouched.

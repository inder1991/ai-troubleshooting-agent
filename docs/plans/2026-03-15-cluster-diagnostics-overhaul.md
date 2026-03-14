# Cluster Diagnostics Complete Overhaul — Master Plan

> **For Claude:** This is a planning document covering ALL issues found in the cluster diagnostics review. Implementation will be phased.

**Goal:** Fix all bugs, close all K8s/OpenShift coverage gaps, upgrade LLM integration to tool-calling agents, improve recommendations quality, fix frontend UI gaps, and harden error handling — making the cluster diagnostic workflow production-ready for real-world Kubernetes and OpenShift troubleshooting.

**Total Issues:** 55 across 6 categories
**Estimated Phases:** 5 phases, prioritized by impact

---

## Phase 1: Critical Bugs & Error Handling (P0)

### 1.1 Surface RBAC errors instead of silent failure

**Problem:** When K8s API returns 403 Forbidden, `except ApiException` catches it and returns empty data. User sees "0 anomalies" instead of "insufficient permissions."

**Files:**
- Modify: `backend/src/integrations/kubernetes_client.py` (or equivalent K8s client)
- Modify: All domain agents (`ctrl_plane_agent.py`, `node_agent.py`, `network_agent.py`, `storage_agent.py`)

**Fix:**
- In K8s client, check `ApiException.status == 403` → return a special `PermissionDenied` result with the required RBAC role
- In domain agents, check for permission errors → emit warning event + include in domain report as a `finding` with category `rbac_error`
- In synthesizer, if any domain has RBAC errors → add to verdict: "Insufficient permissions — grant ClusterRole X"

---

### 1.2 Add pre-flight RBAC permission check

**Problem:** No verification that the service account has required permissions before running diagnostics.

**Files:**
- Create: `backend/src/agents/cluster/rbac_checker.py`
- Modify: `backend/src/agents/cluster/graph.py` (add as first node)

**Fix:**
- New node `rbac_preflight` runs before `topology_snapshot_resolver`
- Checks access to: nodes, pods, events, namespaces, PVCs, services, deployments, daemonsets, statefulsets
- For OpenShift: also checks ClusterOperators, Routes, MachineConfigPools
- Returns: `{granted: [...], denied: [...], warnings: [...]}`
- If critical permissions denied → emit error event + set low confidence
- Pass denied list to domain agents so they skip impossible checks gracefully

---

### 1.3 Add Deployment/StatefulSet/DaemonSet direct queries

**Problem:** Currently only checked via events — misses replica mismatches, stuck rollouts, update strategy issues.

**Files:**
- Modify: `backend/src/integrations/kubernetes_client.py` — add `list_deployments()`, `list_statefulsets()`, `list_daemonsets()`
- Modify: `backend/src/agents/cluster/node_agent.py` — query workloads directly

**New checks:**
- Deployment: `spec.replicas` vs `status.readyReplicas` — mismatch = stuck rollout
- Deployment: `status.conditions` where `type=Progressing` and `status=False` — failed rollout
- StatefulSet: ordered pod startup failures, PVC binding issues
- DaemonSet: `status.numberUnavailable > 0` — not running on all nodes

---

### 1.4 Add HPA/VPA checking

**Problem:** Autoscaling misconfiguration causes OOM kills, throttling, and resource waste.

**Files:**
- Modify: `backend/src/integrations/kubernetes_client.py` — add `list_hpas()`, `list_vpas()`
- Modify: `backend/src/agents/cluster/node_agent.py` — check HPA status

**New checks:**
- HPA: `status.currentReplicas` vs `spec.maxReplicas` — at max = can't scale further
- HPA: `status.currentMetrics` vs `spec.metrics` — target not met for >5min
- HPA: `status.conditions` where `type=ScalingLimited` — scaling blocked
- VPA (if installed): `status.recommendation` vs actual resources — significant drift

---

### 1.5 Add dossier/report export for cluster diagnostics

**Problem:** Unlike DB diagnostics, cluster has no export functionality.

**Files:**
- Modify: `backend/src/api/routes_v4.py` — add `/session/{id}/cluster-dossier` endpoint
- Create: `frontend/src/components/ClusterDiagnostic/ClusterDossierExport.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx` — add export button

**Dossier sections:**
1. Executive Summary (platform, version, health status, scan scope)
2. Domain Reports (per-domain findings with anomalies)
3. Causal Analysis (chains with confidence)
4. Blast Radius (affected resources)
5. Remediation Plan (immediate + long-term with commands)
6. Issue Clusters (correlated alerts)
7. Appendix (agent execution times, data completeness, truncation flags)

---

## Phase 2: K8s/OpenShift Coverage Expansion (P0-P1)

### 2.1 Add RBAC resource checking

**Problem:** ServiceAccount misconfigs, role binding issues, permission problems — ~30% of K8s troubleshooting.

**Files:**
- Modify: `backend/src/integrations/kubernetes_client.py` — add `list_roles()`, `list_role_bindings()`, `list_cluster_roles()`, `list_service_accounts()`
- Create: `backend/src/agents/cluster/rbac_agent.py` — new domain agent

**New checks:**
- ServiceAccounts with no bound roles
- RoleBindings referencing non-existent roles
- Pods running as default ServiceAccount (security risk)
- ClusterRoleBindings granting excessive permissions
- Orphaned roles (no bindings)

---

### 2.2 Add Services/Endpoints checking

**Problem:** Service with no endpoints = complete outage, currently not detected.

**Files:**
- Modify: `backend/src/integrations/kubernetes_client.py` — add `list_services()`, `list_endpoints()`
- Modify: `backend/src/agents/cluster/network_agent.py` — check service health

**New checks:**
- Services with 0 endpoints (no ready pods matching selector)
- Services with selector not matching any deployment
- Headless services with empty endpoint subsets
- ExternalName services pointing to unreachable hosts
- LoadBalancer services in Pending state (no external IP)

---

### 2.3 Add PodDisruptionBudgets checking

**Problem:** PDBs can block node drains and cluster upgrades.

**Files:**
- Modify: `backend/src/integrations/kubernetes_client.py` — add `list_pdbs()`
- Modify: `backend/src/agents/cluster/node_agent.py`

**New checks:**
- PDB `status.disruptionsAllowed == 0` — blocks all voluntary disruptions
- PDB `spec.minAvailable` set too high relative to replicas
- PDB covering pods that are already unhealthy

---

### 2.4 Add Resource Limits/Requests checking

**Problem:** Over/under-provisioned pods cause throttling, OOM, scheduling failures.

**Files:**
- Modify: `backend/src/agents/cluster/node_agent.py`

**New checks (from existing pod data):**
- Pods without resource requests (can't be scheduled predictably)
- Pods without resource limits (can consume unlimited)
- Pods with requests > limits (invalid)
- Pods with CPU throttling (from Prometheus `container_cpu_cfs_throttled_seconds_total`)
- Pods frequently OOMKilled (from events + pod status)
- Node resource overcommit ratio

---

### 2.5 Add NetworkPolicy deep analysis

**Problem:** NetworkPolicies present in topology but not analyzed for connectivity issues.

**Files:**
- Modify: `backend/src/integrations/kubernetes_client.py` — add `list_network_policies()`
- Modify: `backend/src/agents/cluster/network_agent.py`

**New checks:**
- Default deny policies blocking all traffic
- Policies with empty ingress/egress rules (blocks everything)
- Policies targeting pods that don't match any selector
- Missing policies for critical namespaces

---

### 2.6 OpenShift-specific additions

**Files:**
- Modify: `backend/src/integrations/kubernetes_client.py` — add OpenShift API calls
- Create: `backend/src/agents/cluster/openshift_agent.py` OR extend existing agents

**New checks:**
- **SCCs (SecurityContextConstraints):** Pods failing to schedule due to SCC restrictions
- **BuildConfigs:** Failed builds, stuck builds
- **ImageStreams:** Import failures, tag resolution errors
- **MachineConfigPools:** Degraded pools, stuck updates, node cordoned during MCP update
- **OperatorHub/OLM:** Operator installation failures, CSV status

---

### 2.7 Add CronJobs/Jobs checking

**Files:**
- Modify: `backend/src/integrations/kubernetes_client.py` — add `list_jobs()`, `list_cronjobs()`
- Modify: `backend/src/agents/cluster/node_agent.py`

**New checks:**
- Failed jobs (backoffLimit exceeded)
- CronJobs with `suspend: true` (intentional?)
- CronJobs that haven't run in expected schedule
- Jobs with `activeDeadlineSeconds` exceeded
- Completed jobs not cleaned up (resource waste)

---

### 2.8 Add Cluster Autoscaler status

**Files:**
- Modify: `backend/src/agents/cluster/node_agent.py`

**New checks:**
- Cluster Autoscaler pod health
- Pending pods due to insufficient nodes
- Scale-up failures (cloud provider errors)
- Node groups at max capacity

---

## Phase 3: LLM Integration Upgrade (P1)

### 3.1 Add ReAct tool-calling to domain agents

**Problem:** Domain agents do ONE pass — collect data → LLM analyzes → done. LLM can't do follow-up investigation.

**Files:**
- Create: `backend/src/agents/cluster/tools.py` — Anthropic tool schemas for K8s queries
- Create: `backend/src/agents/cluster/tool_executor.py` — tool execution with K8s client
- Modify: All 4 domain agents to use tool-calling loop

**Tools for LLM:**

| Tool | Description |
|---|---|
| `list_pods` | List pods in namespace with status |
| `describe_pod` | Get full pod spec + status + events |
| `list_deployments` | List deployments with replica status |
| `describe_deployment` | Get deployment spec + rollout status |
| `list_events` | Get events for a specific resource |
| `list_nodes` | List nodes with conditions |
| `describe_node` | Get node capacity, allocatable, conditions |
| `list_pvcs` | List PVCs with binding status |
| `list_services` | List services with endpoints count |
| `list_hpas` | List HPAs with current/target metrics |
| `get_pod_logs` | Get last N lines of pod logs |
| `query_prometheus` | Query a Prometheus metric |
| `list_network_policies` | List network policies |
| `list_rbac` | List roles and bindings in namespace |

**Max 5 tool calls per agent, 60s timeout per agent.**
**Heuristic fallback** if LLM fails (keep current code as fallback).

---

### 3.2 Add critic/validator agent

**Problem:** LLM output from domain agents goes directly to synthesizer — no validation.

**Files:**
- Create: `backend/src/agents/cluster/critic_agent.py`
- Modify: `backend/src/agents/cluster/graph.py` — add critic node between domain agents and synthesizer

**Critic validates:**
- Finding has evidence (not hallucinated)
- Severity is proportional to impact
- Recommendations are actionable (valid kubectl commands)
- Causal links follow the 6 rules
- Contradictions between domain findings flagged

---

### 3.3 Add evidence provenance to findings

**Problem:** Findings don't cite which K8s API response they came from.

**Files:**
- Modify: `backend/src/agents/cluster/models.py` — add `evidence_sources` to `Anomaly`
- Modify: All domain agents — attach K8s API response references

**Fields:**
```python
class EvidenceSource:
    api_call: str       # "list_pods(namespace='production')"
    resource: str       # "pod/order-service-abc123"
    data_snippet: str   # "status.phase=CrashLoopBackOff, restartCount=45"
```

---

### 3.4 Add version-aware prompts

**Problem:** K8s 1.28 vs 1.31 have different features/deprecations — prompts are version-agnostic.

**Files:**
- Modify: All domain agent prompts

**Fix:**
- Pass `cluster_version` to all prompts
- Include version-specific context:
  - 1.25+: PodSecurity admission instead of PodSecurityPolicy
  - 1.27+: In-place pod resize (alpha)
  - 1.29+: Sidecar containers
  - 1.30+: Recursive read-only mounts

---

### 3.5 Improve data prioritization before LLM

**Problem:** Events capped at 500, pods at 1000 — critical data may be truncated.

**Files:**
- Modify: `backend/src/integrations/kubernetes_client.py`

**Fix:**
- Prioritize: Error/Warning events first, then Normal
- Prioritize: Failed/CrashLoop pods first, then Pending, then Running
- Include truncation context in LLM prompt: "NOTE: Data truncated — {X} events omitted. Analysis may be incomplete."

---

## Phase 4: Recommendation Quality (P1)

### 4.1 Add kubectl command validation

**Problem:** LLM might generate invalid kubectl syntax.

**Files:**
- Create: `backend/src/agents/cluster/command_validator.py`

**Fix:**
- Parse kubectl command structure: `kubectl <verb> <resource> <name> [flags]`
- Validate: verb exists, resource type valid, namespace included, common flags correct
- Flag: destructive commands (delete, drain, cordon, scale to 0)
- Reject: commands with pipes, shell expansion, or multi-command chains

---

### 4.2 Add rollback commands

**Problem:** Remediation suggests forward actions but no rollback.

**Files:**
- Modify: `backend/src/agents/cluster/synthesizer.py` — update verdict prompt

**Fix:** For each remediation command, LLM must also generate:
```json
{
  "command": "kubectl scale deployment/app --replicas=0 -n production",
  "rollback": "kubectl scale deployment/app --replicas=3 -n production",
  "risk_level": "high",
  "pre_check": "kubectl get deployment/app -n production -o jsonpath='{.spec.replicas}'",
  "verify": "kubectl get pods -n production -l app=app --no-headers | wc -l"
}
```

---

### 4.3 Add verification commands

**Problem:** After fixing, how to confirm resolution?

**Fix:** Each recommendation includes:
- `pre_check`: Command to run BEFORE executing the fix
- `verify`: Command to run AFTER to confirm the fix worked
- `expected_output`: What the verify command should return if fix succeeded

---

### 4.4 Add namespace context to all commands

**Problem:** Commands missing `-n namespace` — could execute in wrong namespace.

**Fix:**
- LLM prompt instruction: "ALWAYS include -n <namespace> in kubectl commands. Never use default namespace implicitly."
- Post-validation: if command has no `-n` flag and targets a namespaced resource → add it

---

### 4.5 Add dry-run suggestions

**Problem:** No safe preview before destructive actions.

**Fix:**
- For every high-risk command, prepend a dry-run version:
  ```
  # Preview (safe):
  kubectl delete pod/stuck-pod -n production --dry-run=client

  # Execute:
  kubectl delete pod/stuck-pod -n production
  ```

---

## Phase 5: Frontend UI Fixes (P1-P2)

### 5.1 Surface truncation warnings

**Files:**
- Modify: `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx`

**Fix:** When `domain_report.truncation_flags` has entries:
```
⚠ Analysis may be incomplete: 1,247 events found, 500 analyzed. 2,340 pods found, 1,000 analyzed.
```

---

### 5.2 Add agent execution timeline

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/AgentTimeline.tsx`

**Fix:** Show horizontal timeline:
```
topology  ████░░░░░░  2.1s
alerts    ░░████░░░░  1.8s
firewall  ░░░░██░░░░  0.3s
──────────────────── parallel ───
ctrl_plane ░░░░░███░  3.2s
node       ░░░░░████  4.1s
network    ░░░░░████  3.8s
storage    ░░░░░█████ 5.2s
──────────────────── synthesis ───
synthesizer ░░░░░░░░██ 8.4s
```

---

### 5.3 Add raw event viewer

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/EventLogViewer.tsx`

**Fix:** Collapsible panel showing the K8s events that triggered findings. Searchable, filterable by severity/namespace/resource.

---

### 5.4 Add Prometheus metrics visualization

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/MetricsPanel.tsx`

**Fix:** When backend queries Prometheus metrics, return raw data points alongside analysis. Frontend renders as sparklines/charts.

---

### 5.5 Improve topology visualization

**Files:**
- Modify: `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx`

**Fix:** Full interactive topology view showing:
- Resources as nodes
- Dependencies as edges
- Color by health status
- Click to inspect resource details

---

### 5.6 Add scan comparison for Guard mode

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/ScanDiff.tsx`

**Fix:** Side-by-side comparison of current vs previous scan:
- New risks highlighted in red
- Resolved risks highlighted in green
- Worsened/improved indicators

---

### 5.7 Add remediation undo/rollback button

**Files:**
- Modify: `frontend/src/components/ClusterDiagnostic/RemediationCard.tsx`

**Fix:** After executing a command, show:
- "Rollback" button with the reverse command
- "Verify" button to run the check command
- Status indicator (success/failed)

---

## Implementation Priority Matrix

| Phase | Items | Effort | Impact |
|---|---|---|---|
| **Phase 1** | 1.1-1.5 (5 items) | 2-3 days | Critical — fixes real bugs, adds missing export |
| **Phase 2** | 2.1-2.8 (8 items) | 3-5 days | High — closes 70% of K8s coverage gaps |
| **Phase 3** | 3.1-3.5 (5 items) | 3-4 days | High — upgrades LLM quality dramatically |
| **Phase 4** | 4.1-4.5 (5 items) | 1-2 days | Medium — improves recommendation safety |
| **Phase 5** | 5.1-5.7 (7 items) | 2-3 days | Medium — surfaces hidden data in UI |

**Total: 30 items across 5 phases, ~12-17 days of work**

---

## File Impact Summary

**New files to create (11):**
- `backend/src/agents/cluster/rbac_checker.py`
- `backend/src/agents/cluster/rbac_agent.py`
- `backend/src/agents/cluster/openshift_agent.py`
- `backend/src/agents/cluster/tools.py`
- `backend/src/agents/cluster/tool_executor.py`
- `backend/src/agents/cluster/critic_agent.py`
- `backend/src/agents/cluster/command_validator.py`
- `frontend/src/components/ClusterDiagnostic/ClusterDossierExport.tsx`
- `frontend/src/components/ClusterDiagnostic/AgentTimeline.tsx`
- `frontend/src/components/ClusterDiagnostic/EventLogViewer.tsx`
- `frontend/src/components/ClusterDiagnostic/ScanDiff.tsx`

**Files to modify (15+):**
- `backend/src/integrations/kubernetes_client.py` — 10+ new K8s API methods
- `backend/src/agents/cluster/graph.py` — new nodes (rbac_preflight, critic)
- `backend/src/agents/cluster/ctrl_plane_agent.py` — tool-calling + new checks
- `backend/src/agents/cluster/node_agent.py` — workloads, HPA, PDB, resources
- `backend/src/agents/cluster/network_agent.py` — services, endpoints, network policies
- `backend/src/agents/cluster/storage_agent.py` — enhanced PVC analysis
- `backend/src/agents/cluster/synthesizer.py` — rollback commands, verification, validation
- `backend/src/api/routes_v4.py` — cluster dossier endpoint
- `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx` — truncation, export, timeline
- `frontend/src/components/ClusterDiagnostic/RemediationCard.tsx` — rollback, verify, dry-run

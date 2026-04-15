# Cluster Diagnostic Demo Mock Data — Design

**Goal:** Create rich, realistic mock data for the cluster diagnostic workflow that simulates a multi-domain OpenShift production incident for CEO/CXO demo audiences.

**Architecture:** Replace the 4 existing cluster fixture files with a comprehensive "Monday Morning Outage" scenario. Add realistic delays to MockClusterClient and LangGraph nodes so the diagnosis takes 60-90 seconds with progressive UI updates.

**Tech Stack:** Python (fixture JSON files, MockClusterClient delays, LangGraph node delays), no frontend changes.

---

## Incident Scenario: "The Monday Morning Outage"

Production OpenShift 4.14 cluster `prod-east` running an e-commerce platform. A bad MachineConfig rollout Friday night triggers a cascading multi-domain failure.

### Causal Chain

```
Root Cause: MachineConfigPool "worker" stuck Degraded (bad kernel param update)
  │
  ├─► ctrl_plane: 2/5 ClusterOperators degraded (ingress, monitoring)
  │     Etcd leader election churn → API server p99 latency 4.2s
  │
  ├─► node: worker-3 NotReady (DiskPressure 93%)
  │     12 pods evicted, order-service stuck rollout (2/4 ready)
  │     DaemonSet fluentd 1 unavailable, HPA maxed + quota exceeded
  │
  ├─► network: Ingress operator degraded → 3 routes returning 503
  │     CoreDNS pod evicted from worker-3, DNS intermittent
  │     payment-gateway service 0 ready endpoints
  │     NetworkPolicy blocking traffic to monitoring namespace
  │
  ├─► storage: PVC data-postgres-0 at 94% capacity
  │     CSI driver attach/detach timeouts on NotReady node
  │     2 PVCs stuck Pending
  │
  └─► rbac: deployer-sa missing "patch" on machineconfigs
        (why the original rollout failed silently)
```

### Fixture Files to Replace

| File | Content |
|------|---------|
| `cluster_ctrl_plane_mock.json` | Degraded operators (ingress, monitoring), etcd leader churn, API latency 4.2s, MCP worker stuck Degraded, webhook timeout warnings, OLM subscriptions |
| `cluster_node_mock.json` | 6 nodes (3 cp + 2 healthy workers + 1 NotReady), 30+ pods with evictions/crashes, stuck deployments, DaemonSet gaps, HPA maxed, quota exceeded, warning events, prometheus metrics |
| `cluster_network_mock.json` | Degraded ingress controller, CoreDNS eviction, 0-endpoint payment-gateway, restrictive NetworkPolicy, 503 routes, DNS failure events |
| `cluster_storage_mock.json` | Near-full PVC (94%), CSI timeouts, 2 pending PVCs, storage class config |

### Timing Design (60-90 seconds)

| Phase | Time | UI Effect |
|-------|------|-----------|
| Pre-flight (rbac + topology) | 0-8s | Topology SVG starts building, RBAC scan |
| ctrl_plane_agent | 8-22s | Operator status, etcd health, API latency findings |
| node_agent | 22-38s | Node conditions, pod evictions, stuck rollouts |
| network_agent | 38-50s | DNS failures, ingress 503s, endpoint gaps |
| storage_agent | 50-58s | PVC warnings, CSI timeouts |
| Intelligence pipeline | 58-70s | Signal normalization, pattern matching, hypothesis |
| Critic + Synthesis | 70-82s | Verdicts, causal chain, blast radius, remediation |

### Delay Implementation

**MockClusterClient:** 1-3s per API call category
- get_nodes: 2s
- get_pods: 2.5s (larger result set)
- get_events: 1.5s
- get_cluster_operators: 1.5s
- get_deployments/statefulsets/daemonsets: 1s each
- get_pvcs/storage_classes: 1s each
- get_services/endpoints/ingress: 1s each

**LangGraph nodes:** 2-4s thinking pauses between pipeline stages with descriptive event emissions:
- "Correlating node pressure with pod evictions..."
- "Building causal evidence graph..."
- "Validating hypotheses against temporal evidence..."
- "Generating remediation recommendations..."

### Features Exercised

| Feature | Triggered by |
|---------|-------------|
| Topology SVG with unhealthy nodes | topology_snapshot_resolver |
| Root cause identification | hypothesis_engine |
| Pod health cards (CrashLoop, OOM, evictions) | node_agent |
| Metric anomalies + saturation gauges | node_agent prometheus data |
| K8s events timeline | All agents |
| Blast radius visualization | synthesizer |
| Causal chain / evidence graph | diagnostic_graph_builder |
| Critic verdicts (validated/challenged) | critic_validator |
| Remediation recommendations | synthesizer + solution_validator |
| Agent capsules with progress | Event emissions per agent |
| Telescope drawer (YAML/events/logs) | Clickable pod/node names |
| Suggested PromQL queries | proactive_analysis |
| Confidence progression | Running average across agents |

### What Does NOT Change

- App diagnostic workflow (supervisor.py, log_agent, metrics_agent, etc.)
- Frontend components (no UI code changes)
- LangGraph structure (graph.py topology stays the same)
- API routes
- Existing test infrastructure

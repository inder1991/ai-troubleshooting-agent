# DebugDuck Cluster Diagnostic Engine — Design Document

**Date:** 2026-02-27
**Status:** Approved
**Scope:** Phase 1+2+5 (Trigger, Diagnostic Agents, Health Report UI)
**Out of scope:** GitOps PR generation (Phase 3), Upgrade Readiness runbooks (Phase 4)

---

## 1. Overview

A new capability workflow that shifts DebugDuck from "Developer looking at an App" to "Platform Engineer looking at a Fleet." Four specialized agents investigate cluster infrastructure domains in parallel, a synthesis engine identifies cross-domain causal chains, and a dedicated War Room view gives SREs real-time visibility into the diagnostic process.

### Key Architectural Decisions

- **LangGraph `StateGraph`** for orchestration (not hand-rolled async)
- **Both Kubernetes and OpenShift** from day one via platform adapter
- **Hybrid data access:** K8s API + Prometheus + ELK
- **Existing `k8s_agent` untouched** — new agents are separate, copy shared patterns
- **New dedicated Cluster War Room UI** (not reusing app Investigation View)
- **Mock fixtures from day one** for demo/dev/testing

---

## 2. Routing: Capability-Based Supervisor Selection

Deterministic, not AI-driven. The user selects "Cluster Diagnostics" from the Capability Launcher (already exists as a card in the UI). The `capability` field flows through the form to the API.

```
Frontend CapabilityForm
  capability: "cluster_diagnostics"
       |
       v
routes_v4.py (session start endpoint)
  if capability == "troubleshoot_app":
      supervisor = AppSupervisor(config)       <-- existing, untouched
  elif capability == "cluster_diagnostics":
      graph = build_cluster_diagnostic_graph() <-- new LangGraph
```

Both workflows share: session model, EventEmitter -> WebSocket pipeline, `/findings` endpoint pattern, mock fixture infrastructure.

### Why Not the Same Supervisor

The existing `AppSupervisor` is deeply coupled to the app troubleshooting domain:

1. **Phase machine is app-specific** — `DiagnosticPhase` enum assumes linear flow: logs -> metrics -> k8s -> code
2. **Agent dispatch is hardcoded** — if/else chains for app-specific sequencing
3. **State model is app-centric** — holds `log_analysis`, `code_analysis`, `repo_url`
4. **Result synthesis is app-focused** — per-agent parsers for app-domain agents

The cluster diagnostic needs parallel fan-out, different state shape, and different agents. LangGraph provides this declaratively.

---

## 3. The LangGraph Architecture

```
                         START
                           |
                    +------+------+
                    |  Pre-Flight  |  Token refresh, platform detect,
                    |  Checks      |  connectivity probe, namespace discovery
                    +------+------+
                           |
                    +------+------+
                    |  Dispatch    |
                    +--+--+--+--+-+
                       |  |  |  |
            +----------+  |  |  +----------+
            v             v  v             v
      ctrl_plane      node  network     storage     <-- Fan-Out (parallel)
         agent        agent  agent       agent
            |             |  |             |
            +----------+  |  |  +----------+
                       v  v  v  v
                    +--------------+
                    |  Synthesize   |  3-stage: Merge -> Causal -> Verdict
                    +------+------+
                           |
                     +-----+-----+
                     | Confidence |---- < 60% --> Re-dispatch (max 1 round)
                     | check      |                    |
                     +-----+-----+                     |
                           | >= 60%             +------+
                           v                    v
                    +--------------+      Back to specific
                    |     END      |      agent node
                    | Health Report|
                    +--------------+
```

**State object:** `ClusterDiagnosticState` — holds only DomainReport summaries (never raw data, never credentials).

**Config object:** Cluster tokens, client instances, platform capability map — injected via LangGraph `config["configurable"]`, never checkpointed.

---

## 4. The Four Diagnostic Agents

Each agent follows the existing two-pass LLM pattern (Plan + Analyze). Each produces a compact `DomainReport` that goes into shared state.

### Agent Roster

| Agent | Domain | Focus |
|---|---|---|
| **Control Plane & Etcd** | The Brain | Degraded operators, API latency, etcd sync, certificate expiry, leader election flaps |
| **Node & Capacity** | The Muscle | DiskPressure, MemoryPressure, CPU over-commit, NotReady nodes, noisy neighbors, scheduling failures |
| **Network & Ingress** | The Veins | DNS resolution failures, 502 spikes, IPAM exhaustion, BGP peering (on-prem), dropped packets |
| **Storage & Persistence** | The Disks | FailedMount pods, detached volumes, IOPS throttling, PVC stuck in Pending, storage class misconfiguration |

### Data Sources Per Agent

| Agent | K8s API | Prometheus | ELK |
|---|---|---|---|
| Control Plane | ClusterOperators (OCP), apiserver health, etcd members | apiserver_request_duration, etcd_disk_wal_fsync_duration | API audit logs |
| Node & Capacity | Node conditions, MachineSets (OCP), ResourceQuotas, top pods | node_cpu_utilisation, node_memory_pressure, kube_pod_container_resource_limits | Kubelet logs, autoscaler logs |
| Network & Ingress | IngressControllers/Routes (OCP), CoreDNS pods, NetworkPolicies | coredns_dns_request_duration, ingress_controller_requests | OVN-Kubernetes/Calico logs |
| Storage | StorageClasses, PVCs, CSI driver pods, VolumeAttachments | kubelet_volume_stats, csi_operations_duration | CSI driver logs, kubelet mount logs |

### Platform Capability Map

Each agent's system prompt includes what's available on the detected platform:

- **K8s:** "Focus on Ingress, RBAC, Nodes, standard resources. No Routes, SCCs, ClusterOperators."
- **OpenShift:** "Full access: Routes, SCCs, ClusterOperators, MachineSets, plus standard K8s resources."

This narrows the LLM's hypothesis space — no hallucinating about missing OpenShift components on vanilla K8s.

---

## 5. Timeout & Partial Success

Every agent node runs inside `@traced_node` decorator with hard timeout via `asyncio.wait_for`.

### Timeout Budget

```
ctrl_plane_agent:  30s  (mostly API status checks)
node_agent:        45s  (may scan many nodes)
network_agent:     45s  (DNS probes, ingress checks)
storage_agent:     60s  (PVC attachment can be slow)
Graph-level ceiling: 180s (3 minutes)
```

### Failure Classification (Standardized Enum)

```
TIMEOUT | RBAC_DENIED | API_UNREACHABLE | LLM_PARSE_ERROR | EXCEPTION
```

### Partial Success Handling

On any failure, agent produces a `PartialDomainReport` with:
- `status: FAILED`
- Classified failure reason
- `data_gathered_before_failure` (pre-timeout evidence)
- `confidence: 0` for FAILED, reduced for PARTIAL

Graph always proceeds to synthesize — never hangs.

### Data Completeness Score

Computed at synthesis. Caps synthesis confidence:
- 4 of 4 domains succeeded = no cap
- 2 of 4 domains succeeded = max 50% confidence

Surfaced explicitly in UI: "2 of 4 diagnostic domains unavailable — findings are partial."

### Zombie Prevention

All tool calls use async clients that respect `asyncio.CancelledError`:
- K8s/OpenShift: `kubernetes_asyncio` (not `kubernetes`)
- Prometheus: `aiohttp` (not `requests`)
- ELK: `elasticsearch[async]` (`AsyncElasticsearch`)
- GitHub: `httpx.AsyncClient` (already used)

When `asyncio.wait_for` cancels a timed-out agent, in-flight HTTP requests are cleanly cancelled.

---

## 6. Token Management & Summarization-on-Write

### Two-Layer Data Architecture

| Layer | Contents | Size | Where |
|---|---|---|---|
| **Shared State** (LangGraph) | DomainReport summaries, evidence_refs, causal chains | ~800 tokens per agent, ~5K total into synthesis | In-memory (MVP), Postgres (later) |
| **Raw Evidence Store** | Full K8s API responses, metric series, log lines | Unbounded | Postgres keyed by evidence_id, 72h TTL |

### Token Budget Per Agent

1,000-1,500 tokens max in shared state. Synthesis total prompt stays under ~7,500 tokens.

The LLM does the compression: Pass 1 sees all raw data. Pass 2 produces compact DomainReport. Same pattern as existing `code_agent` two-pass flow.

### Object Count Caps

| Resource | Max Objects | Rationale |
|---|---|---|
| Events | 500 | Clusters can have 200K+ events |
| Pods | 1,000 | Large clusters have 50K+ pods |
| Log lines (ELK) | 2,000 | Unbounded otherwise |
| Metric data points | 500 per query | Long time ranges explode |
| Nodes | 500 | Sufficient for most clusters |
| PVCs | 500 | Rarely exceeds this |

Every capped response carries a truncation flag:

```
QueryResult:
  data: [...]
  total_available: 47392
  returned: 500
  truncated: true
  sort_order: "severity_desc"   <-- most critical items first
```

Truncation flag flows into DomainReport. Synthesis factors incomplete evidence into confidence: "Node agent saw 500 of 47,392 events (truncated) — findings may be incomplete."

### Raw Evidence Store Schema

```
RawEvidence:
  evidence_id:    "ev-ctrl-001"
  diagnostic_id:  "DIAG-8829"
  domain:         "ctrl_plane"
  source:         "k8s_api"
  query:          "oc get clusteroperators -o json"
  raw_payload:    { ... }            <-- full JSON, unbounded
  timestamp:      2026-02-27T10:30:00Z
  ttl:            72h                <-- auto-cleanup
```

The DomainReport in shared state only references it via `evidence_refs`.

---

## 7. Causal Link Synthesis

Synthesis is a three-stage pipeline inside the synthesize node.

### Stage 1: MERGE (Deterministic, No LLM)

- Collect all DomainReports
- Deduplicate overlapping findings (e.g., two agents both saw "infra-node-03 NotReady")
- Apply data completeness score

### Stage 2: CAUSAL REASONING (LLM)

Identify cross-domain causal chains with structured output.

### Stage 3: VERDICT & REMEDIATION (LLM)

Produce `ClusterHealthReport` with platform_health, blast_radius, primary root cause, remediation steps, and re_dispatch_needed flag.

### CausalChain Schema

```
CausalChain:
  chain_id:        "cc-001"
  confidence:      0.88
  root_cause:
    domain:        "node"
    anomaly_id:    "node-003"
    description:   "infra-node-03 disk usage at 97%"
    evidence_ref:  "ev-node-003"

  cascading_effects: [
    {
      order:       1,
      domain:      "ctrl_plane",
      anomaly_id:  "cp-002",
      description: "CoreDNS pods on infra-node-03 evicted due to disk pressure",
      link_type:   "resource_exhaustion -> pod_eviction",
      evidence_ref: "ev-ctrl-002"
    },
    {
      order:       2,
      domain:      "network",
      anomaly_id:  "net-001",
      description: "DNS resolution failures across cluster - 40% of queries timing out",
      link_type:   "pod_eviction -> service_degradation",
      evidence_ref: "ev-net-001"
    }
  ]
```

### Constrained Link Types

LLM must pick from enumerated list:

```
resource_exhaustion -> pod_eviction
resource_exhaustion -> throttling
pod_eviction -> service_degradation
node_failure -> workload_rescheduling
dns_failure -> api_unreachable
certificate_expiry -> tls_handshake_failure
config_drift -> unexpected_behavior
storage_detach -> container_stuck
network_partition -> split_brain
api_latency -> timeout_cascade
quota_exceeded -> scheduling_failure
image_pull_failure -> pod_pending
unknown (requires free-text explanation, signals low confidence)
```

### Uncorrelated Findings Bucket

Not everything is causal. Independent degradations, secondary symptoms, and coincidental noise go into `uncorrelated_findings: []`. "Two independent issues detected" is a valid and honest output.

### Six Causal Reasoning Rules

1. **TEMPORAL:** A can only cause B if A started before B. Check timestamps.
2. **MECHANISM:** Must name HOW A caused B (link_type). "Same time" is correlation, not causation.
3. **DOMAIN BOUNDARY:** Explain the infrastructure mechanism for cross-domain links.
4. **SINGLE ROOT:** Each chain has exactly one root cause. Two independent roots = two chains.
5. **WEAKEST LINK:** Chain confidence = minimum of individual link confidences.
6. **OBSERVABILITY CONFIRMATION:** For cross-domain causality, require at least one piece of evidence in the effect domain that references the cause resource. If missing, downgrade confidence.

### Re-Dispatch Conditions

- Highest causal chain confidence < 60%
- Causal gap detected (A -> ??? -> C)
- Two contradictory chains with similar confidence
- A domain returned TIMEOUT/FAILED

Max 1 re-dispatch round. If second pass still ambiguous, report with honest low confidence.

---

## 8. Observability & Tracing

### Three-Layer Observability

| Layer | Purpose | Storage | Retention |
|---|---|---|---|
| **Real-time UI events** | Live progress in WebSocket | Ephemeral (in-flight) | Session lifetime |
| **Persistent trace store** | Full NodeExecution + EdgeTransition records | Postgres | 90 days |
| **Deterministic replay** (future) | Re-run synthesis with stored prompts/responses | Postgres | 90 days |

### @traced_node Decorator Captures Per Node

- Entry/exit timestamps
- Duration breakdown: `k8s_api_ms`, `prom_query_ms`, `llm_pass1_ms`, `llm_pass2_ms`
- `input_state_hash` + `input_summary` (for forensic replay)
- `output_summary` + DomainReport ID produced
- Failure classification (standardized enum)
- Token usage breakdown

### EdgeTransition Records Include

- `state_version_before`, `state_version_after`, `state_diff_summary`
- Condition that triggered the edge (for auditing re-dispatch decisions)

### Partial Failure Forensics

When a node times out, the trace includes `data_gathered_before_failure`. The UI surfaces this as "Pre-Timeout Evidence" so the human can finish the job the agent started.

### Causal Chain Storage

Causal chains stored as structured data (not narrative text):

```
[
  {"domain": "node", "anomaly": "disk_full"},
  {"domain": "control_plane", "anomaly": "router_crash"},
  {"domain": "network", "anomaly": "dns_timeout"}
]
```

Enables: UI visualization, automated learning, RCA clustering.

---

## 9. UI Synchronization & Real-Time Streaming

### GraphEventBridge: LangGraph -> EventEmitter Filter

| LangGraph Event | Action | UI Effect |
|---|---|---|
| `on_chain_start` (top-level node) | Emit `agent_started` | Domain panel turns amber |
| `on_tool_start` | Emit `tool_call` with tool name + args | "Querying: `list_nodes`" in reasoning panel |
| `on_tool_end` | Emit `tool_result` (truncated summary) | "Found 3 nodes with DiskPressure" |
| `on_chat_model_stream` | Throttle: buffer, emit every 500ms or sentence boundary | "Agent is thinking..." live text |
| `on_chain_end` (top-level node) | Emit `agent_completed` with DomainReport summary | Panel turns green, findings populate |
| `on_chain_end` (internal) | Drop | Noise — internal LangChain plumbing |

### Parallel Event Routing

Events carry `domain` tag. Each UI panel is an independent event consumer filtering by its domain. No global sorting needed — 4 parallel streams render independently.

Frontend state management: `diagnostic_id` + `domain` as primary keys in React state. Domain panels are independent state slices.

### Event Envelope Schema

```
ClusterDiagnosticEvent:
  diagnostic_id:    "DIAG-8829"
  graph_run_id:     "run-abc123"
  domain:           "ctrl_plane" | "node" | "network" | "storage" | "supervisor"
  parent_node_id:   "ctrl_plane_agent"
  event_type:       "agent_started" | "tool_call" | "tool_result" |
                    "progress" | "agent_completed" | "agent_failed" |
                    "graph_transition" | "synthesis_started" |
                    "synthesis_complete"
  timestamp:        1709012345123          <-- millisecond precision
  call_id:          "uuid-for-tool-call"   <-- stable identifier
  payload:
    message:        "Found 3 degraded cluster operators"
    details:        { ... }
    confidence:     82
    duration_ms:    2340
```

### Tool Call UUID Buffering

Every tool invocation gets a stable `call_id`. If `tool_result` arrives before `tool_start` (network jitter), the UI buffers it for up to 2 seconds before rendering.

### Progressive Updates

Domain panels populate as each agent completes. The SRE reads findings while other agents still run. By the time synthesis finishes, the SRE has context.

### Process Map DAG

Interactive visualization at top of view:
- **Pending:** gray
- **Running:** amber, pulsing
- **Completed:** green
- **Failed:** red
- **Timeout:** orange + "PARTIAL" label

Clicking a node reveals NodeExecution metadata (confidence, duration, findings, failure reason, input_state_hash).

### Re-Dispatch History Stack

When an agent runs Round 2, Round 1 findings push into a "Previous Attempt" accordion — not overwritten. Shows the AI's correction path.

---

## 10. Security & Multi-Tenant Token Injection

### Token Flow

```
Integration Store (encrypted)
  -> WorkflowRouter decrypts
    -> Injects into LangGraph config["configurable"]
      -> Agent nodes access via config, never via state
```

### Credentials Never Appear In

- LangGraph State (checkpointed)
- LLM prompts
- WebSocket events
- Structured logs

### Immutable Execution Context

Before `graph.ainvoke()`:

1. **Token refresh** — decode JWT, check exp. If `expires_in < 10 minutes`: refresh now. If refresh fails: abort with clear error.
2. **Platform detection** — call `/apis` to detect OpenShift vs vanilla K8s.
3. **Connectivity probe** — verify K8s API, Prometheus, ELK reachable.
4. **Namespace discovery** — list all namespaces, apply `exclude_namespaces` filter.

Once graph starts, context is frozen. No mid-run auth changes.

### ClusterClient Platform Adapter

Abstract base class with `KubernetesClient` and `OpenShiftClient` implementations.

- OpenShift-specific methods (`get_cluster_operators`, `get_machine_sets`, `get_routes`) return empty lists on vanilla K8s
- Namespace exclude filter enforced at client level (data never reaches agent)
- RBAC denial returns `RBACDenied` result (not exception) — becomes a finding with actionable message
- `read_only=True` enforced: only GET/LIST/WATCH verbs

Defense in depth (4 layers):
1. ClusterClient only exposes read methods
2. Agent toolset only includes read tools
3. ServiceAccount RBAC only grants read verbs
4. OpenShift SCC prevents privilege escalation

---

## 11. Idempotency & Checkpointing

### Read-Only Contract

Diagnostic phase tools only expose read verbs. LLM never sees mutating tools. Remediation tools are a separate future phase behind an Attestation Gate.

### Cache-on-First-Read

Per-diagnostic in-memory cache. Retried nodes see identical data.

```
Cache key: (diagnostic_id, method, params_hash)
TTL: lifetime of the diagnostic run
Cleanup: when diagnostic completes
```

Explicit re-dispatch by synthesis can bypass cache with `force_fresh=True`.

### Object Count Caps with Truncation Tracking

All list operations capped. Truncation flag recorded. Agents report truncation in DomainReport. Synthesis factors incomplete evidence into confidence scoring.

Sort order is always `severity_desc` — most critical items returned first within the cap.

### Checkpoint Strategy

**MVP:** `MemorySaver` (LangGraph built-in)
- In-memory checkpoints
- Lost on server restart
- Sufficient for 30-90 second diagnostics

**Production (later):** `PostgresSaver`
- Persistent checkpoints
- Resume after server crash
- Required for long-running lifecycle diagnostics (Phase 4)
- Audit trail compliance
- Deterministic replay mode

Checkpoint after each node completion (not during). A node is either fully complete or not.

---

## 12. Output Schema

```json
{
  "diagnostic_id": "DIAG-8829",
  "platform": "openshift",
  "platform_version": "4.14.2",
  "platform_health": "DEGRADED",
  "data_completeness": 0.75,

  "blast_radius": {
    "summary": "14% of production nodes under MemoryPressure",
    "affected_namespaces": 3,
    "affected_pods": 47,
    "affected_nodes": 2
  },

  "causal_chains": [
    {
      "chain_id": "cc-001",
      "confidence": 0.88,
      "root_cause": {
        "domain": "node",
        "anomaly_id": "node-003",
        "description": "infra-node-03 disk usage at 97%",
        "evidence_ref": "ev-node-003"
      },
      "cascading_effects": [
        {
          "order": 1,
          "domain": "ctrl_plane",
          "anomaly_id": "cp-002",
          "description": "CoreDNS pods evicted due to disk pressure",
          "link_type": "resource_exhaustion -> pod_eviction",
          "evidence_ref": "ev-ctrl-002"
        }
      ]
    }
  ],

  "uncorrelated_findings": [
    {
      "domain": "storage",
      "anomaly_id": "stor-005",
      "description": "gp2 StorageClass deprecated but still default",
      "severity": "low",
      "evidence_ref": "ev-stor-005"
    }
  ],

  "domain_reports": [
    {
      "domain": "ctrl_plane",
      "status": "SUCCESS",
      "failure_reason": null,
      "confidence": 85,
      "anomalies": [],
      "ruled_out": [],
      "evidence_refs": [],
      "truncation_flags": { "events": false, "pods": false }
    }
  ],

  "remediation": {
    "immediate": [
      {
        "command": "oc adm taint node infra-node-03 disk-full=true:NoSchedule",
        "description": "Stop scheduling new pods to the affected node",
        "risk_level": "low"
      }
    ],
    "long_term": [
      {
        "description": "Increase PVC size for ingress access logs from 10Gi to 50Gi",
        "effort_estimate": "30 minutes"
      }
    ]
  },

  "execution_metadata": {
    "total_duration_ms": 18340,
    "token_usage_total": 12500,
    "re_dispatch_count": 0,
    "agents_succeeded": 4,
    "agents_failed": 0
  }
}
```

---

## 13. File Structure

```
backend/src/
  agents/
    cluster/
      __init__.py
      graph.py                    # LangGraph StateGraph definition
      state.py                    # ClusterDiagnosticState, DomainReport, CausalChain
      ctrl_plane_agent.py         # Control Plane & Etcd node function
      node_agent.py               # Node & Capacity node function
      network_agent.py            # Network & Ingress node function
      storage_agent.py            # Storage & Persistence node function
      synthesizer.py              # 3-stage synthesis pipeline
      traced_node.py              # @traced_node decorator
      graph_event_bridge.py       # LangGraph events -> EventEmitter filter
    cluster_client/
      __init__.py
      base.py                     # Abstract ClusterClient
      kubernetes_client.py        # Vanilla K8s implementation
      openshift_client.py         # OpenShift implementation
      diagnostic_cache.py         # Cache-on-first-read with object caps
    fixtures/
      cluster_ctrl_plane_mock.json
      cluster_node_mock.json
      cluster_network_mock.json
      cluster_storage_mock.json
  api/
    routes_v4.py                  # Add capability routing (~5 lines)

frontend/src/
  components/
    ClusterDiagnostic/
      ClusterWarRoom.tsx          # Main view (4 domain panels + process map)
      DomainPanel.tsx             # Independent event consumer per domain
      ProcessMapDAG.tsx           # Interactive graph visualization
      ClusterHealthBanner.tsx     # HEALTHY/DEGRADED/CRITICAL status
      CausalChainView.tsx         # Visual chain: A -> B -> C
      BlastRadiusCard.tsx         # Impact quantification
      RemediationPanel.tsx        # Actionable steps
```

---

## 14. Dependencies (New)

```
langgraph >= 0.2
langgraph-checkpoint >= 0.2        # MemorySaver (MVP), PostgresSaver (later)
kubernetes-asyncio >= 30.0         # Async K8s client
aiohttp >= 3.9                     # Async Prometheus queries
elasticsearch[async] >= 8.0        # Async ELK queries
```

---

## 15. Migration & Risk

- **Zero risk to existing app flow.** AppSupervisor untouched. New code in `agents/cluster/` and `cluster_client/`.
- **Routing change is ~5 lines** in `routes_v4.py`.
- **LangGraph is additive** — no existing code depends on it.
- **Mock fixtures enable development** without live cluster access.
- **Incremental delivery:** Backend agents can be tested independently via mock before UI is built.

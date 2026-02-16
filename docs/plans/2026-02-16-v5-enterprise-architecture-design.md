# v5 Enterprise Architecture Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Evolve the AI SRE Troubleshooting System from v4 (Supervisor + ReAct multi-agent) to v5 (enterprise-grade with governance, resilience, causal intelligence, and remediation safety).

**Architecture:** Layered enhancement on v4 — adds governance gates around every agent action, resilience fallbacks for degraded environments, causal graph reasoning for root cause analysis, persistent integration registry, incident memory via RAG, and safe remediation with dry-run + rollback.

**Tech Stack:** Python 3.11+, Anthropic Claude API, Pydantic v2, FastAPI, React 18 + TypeScript + Tailwind, WebSocket (existing), OpenShift/Kubernetes client libraries, Prometheus client, ChromaDB (vector store for memory)

---

## Section 1: Governance & Safety

Every AI-generated claim must carry proof. No action without evidence. No remediation without human approval.

### 1.1 EvidencePin

Every agent finding must include structured evidence:

```python
class EvidencePin(BaseModel):
    claim: str                    # "order-service has connection timeout errors"
    supporting_evidence: list[str] # Raw log lines, metric values, API responses
    source_agent: str             # "log_analyzer", "metrics_agent", etc.
    source_tool: str              # "elasticsearch", "prometheus", "kubectl"
    confidence: float             # 0.0 - 1.0
    timestamp: datetime
    evidence_type: Literal["log", "metric", "trace", "k8s_event", "code", "change"]
```

**Rule:** Any finding without an EvidencePin is discarded by the Supervisor. Agents cannot pass unsubstantiated claims.

### 1.2 ConfidenceLedger

Per-source confidence tracking with critic adjustment:

```python
class ConfidenceLedger(BaseModel):
    log_confidence: float = 0.0
    metrics_confidence: float = 0.0
    tracing_confidence: float = 0.0
    k8s_confidence: float = 0.0
    code_confidence: float = 0.0
    change_confidence: float = 0.0

    critic_adjustment: float = 0.0     # Critic agent's modifier (-0.3 to +0.1)
    weighted_final: float = 0.0        # Weighted combination

    weights: dict[str, float] = {
        "log": 0.25, "metrics": 0.30, "tracing": 0.20,
        "k8s": 0.15, "code": 0.05, "change": 0.05
    }
```

The Supervisor computes `weighted_final` after each agent completes. If confidence drops below 0.4, the Supervisor requests additional investigation before proceeding.

### 1.3 AttestationGate

Mandatory human checkpoint between discovery and remediation:

```python
class AttestationGate(BaseModel):
    gate_type: Literal["discovery_complete", "pre_remediation", "post_remediation"]
    requires_human: bool = True
    evidence_summary: list[EvidencePin]
    proposed_action: str | None = None
    human_decision: Literal["approve", "reject", "modify"] | None = None
    human_notes: str | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None
```

**Gates:**
1. `discovery_complete` — After all agents finish evidence collection, before forming root cause hypothesis
2. `pre_remediation` — Before any fix is attempted, human reviews proposed action
3. `post_remediation` — After fix applied, human confirms resolution

### 1.4 ReasoningManifest

Full audit trail of the Supervisor's decision-making:

```python
class ReasoningManifest(BaseModel):
    session_id: str
    steps: list[ReasoningStep]

class ReasoningStep(BaseModel):
    step_number: int
    timestamp: datetime
    decision: str                    # "dispatch_log_analyzer", "form_hypothesis", etc.
    reasoning: str                   # Why this decision was made
    evidence_considered: list[str]   # EvidencePin IDs used
    confidence_at_step: float
    alternatives_rejected: list[str] # Other options considered and why rejected
```

### 1.5 TrustHierarchy

Source reliability ranking:

```
K8s API (direct cluster state)  > Prometheus (time-series metrics)
                                > Jaeger (distributed traces)
                                > ELK (log aggregation)
                                > Code analysis (static inference)
```

When evidence from different sources conflicts, higher-trust sources win. The Supervisor uses this hierarchy when computing weighted confidence.

---

## Section 2: Integration Registry

Persistent storage for cluster connections and monitoring tools. Users configure integrations once; they appear as dropdowns when starting any troubleshooting session.

### 2.1 IntegrationConfig

```python
class IntegrationConfig(BaseModel):
    id: str                          # UUID
    name: str                        # "Production OpenShift", "Staging GKE"
    cluster_type: Literal["openshift", "kubernetes"]
    cluster_url: str                 # API server URL
    auth_method: Literal["kubeconfig", "token", "service_account"]
    auth_data: str                   # Encrypted kubeconfig content or token
    prometheus_url: str | None       # Auto-discovered for OpenShift
    elasticsearch_url: str | None
    jaeger_url: str | None
    created_at: datetime
    last_verified: datetime | None
    status: Literal["active", "unreachable", "expired"]
    auto_discovered: dict            # What was auto-detected
```

### 2.2 ClusterProbe

Auto-detection logic run when adding a new integration:

```python
class ClusterProbe:
    async def probe(self, config: IntegrationConfig) -> ProbeResult:
        """
        1. Detect cluster type: try `oc whoami` → OpenShift, else kubectl
        2. If OpenShift:
           - Auto-discover Prometheus via route:
             oc get route -n openshift-monitoring prometheus-k8s
           - Auto-discover ELK via route:
             oc get route -n openshift-logging
           - Detect cluster version: oc version
        3. If Kubernetes:
           - Check for prometheus-server service in monitoring namespace
           - Check for elasticsearch service in logging namespace
        4. Verify connectivity to each discovered endpoint
        5. Return ProbeResult with discovered URLs and status
        """
```

### 2.3 Auto-Detection: oc vs kubectl

```python
def get_cluster_client(config: IntegrationConfig):
    if config.cluster_type == "openshift":
        # Use openshift-client library or subprocess oc commands
        return OpenShiftClient(config)
    else:
        # Use kubernetes-client library or subprocess kubectl commands
        return KubernetesClient(config)
```

The system detects cluster type during probe and stores it. All subsequent operations use the correct CLI tool automatically.

### 2.4 API Endpoints

```
POST   /api/v5/integrations              — Add new integration
GET    /api/v5/integrations              — List all integrations
GET    /api/v5/integrations/{id}         — Get integration details
PUT    /api/v5/integrations/{id}         — Update integration
DELETE /api/v5/integrations/{id}         — Remove integration
POST   /api/v5/integrations/{id}/probe   — Re-probe/verify integration
GET    /api/v5/integrations/{id}/health  — Health check
```

### 2.5 Settings UI

Frontend Settings page with:
- List of configured integrations with status badges (active/unreachable/expired)
- "Add Integration" form: name, cluster URL, auth method (kubeconfig upload / token paste / service account), cluster type auto-detect
- Auto-discovery results shown after probe (Prometheus URL, ELK URL, cluster version)
- Edit/delete/re-verify actions per integration
- Integrations appear as dropdown in TroubleshootApp and ClusterDiagnostics forms

### 2.6 Storage

Integrations stored in SQLite (file-based, no external DB dependency) with encrypted auth_data column (AES-256, key from environment variable).

---

## Section 3: Platform Agent Enhancement & Resilience

Make agents resilient to degraded environments. Real incidents often coincide with monitoring stack failures.

### 3.1 DiscoveryFallback

When ELK/log aggregation is unavailable:

```python
class DiscoveryFallback:
    async def discover_without_elk(self, namespace: str | None) -> DiscoveryResult:
        """
        Fallback chain:
        1. oc get namespaces → list available namespaces
        2. If namespace not specified → present to user for selection
        3. oc get pods -n <namespace> → find error/crash pods
        4. oc logs <pod> → direct pod log retrieval
        5. oc debug node/<node> → if pod logs insufficient, node-level debug
        """
```

### 3.2 TieredLogProcessing

Progressive log parsing sophistication:

```
Tier 1: ECS field parsing (structured logs)
  ↓ fails
Tier 2: LLM-generated regex patterns (cached per service)
  ↓ fails
Tier 3: Semantic inference (LLM reads raw log blocks)
```

Tier 2 regex patterns are cached per service name, so the LLM only generates them once per unique log format.

### 3.3 ReActBudget

Per-agent resource controls to prevent runaway LLM calls:

```python
class ReActBudget(BaseModel):
    max_llm_calls: int = 10          # Maximum LLM API calls per agent run
    max_tool_calls: int = 15         # Maximum tool invocations
    max_tokens: int = 50000          # Maximum tokens consumed
    timeout_seconds: int = 120       # Hard timeout

    current_llm_calls: int = 0
    current_tool_calls: int = 0
    current_tokens: int = 0
    started_at: datetime | None = None
```

When any limit is hit, the agent stops and returns whatever evidence it has collected so far. The Supervisor decides whether to continue with partial results or request more budget.

### 3.4 HeuristicLogFallback

When LLM quota is exhausted, fall back to pattern matching:

```python
HEURISTIC_PATTERNS = {
    "connection_timeout": r"(?i)(connection\s*timed?\s*out|ETIMEDOUT|connect\s+ECONNREFUSED)",
    "oom_killed": r"(?i)(OOMKilled|out\s*of\s*memory|Cannot\s+allocate\s+memory)",
    "crash_loop": r"(?i)(CrashLoopBackOff|back-off\s+restarting)",
    "permission_denied": r"(?i)(permission\s+denied|EACCES|403\s+Forbidden)",
    "dns_failure": r"(?i)(NXDOMAIN|dns\s+resolution|could\s+not\s+resolve)",
}
```

### 3.5 TelemetryPivotPriority

Reverse the v4 agent dispatch order. Start with the highest-signal sources:

```
v4 order: ELK → Metrics → K8s → Tracing → Code
v5 order: Metrics → Tracing → K8s → ELK → Code → Change
```

**Rationale:** Metrics give the fastest signal (spike? yes/no). Tracing pinpoints the service. K8s shows cluster state. ELK provides detail. Code and Change provide context.

### 3.6 Supervisor Orchestration Changes

The Supervisor's dispatch logic changes:
1. **Phase 1 (Evidence Collection):** Dispatch Metrics Agent first, then Tracing and K8s in parallel, then ELK, then Code and Change agents
2. **Phase 2 (Hypothesis Formation):** Supervisor analyzes EvidenceGraph, forms ranked hypotheses
3. **Phase 3 (Human Gate):** AttestationGate at `discovery_complete`
4. **Phase 4 (Remediation):** If approved, run Fix Generator with safety controls

---

## Section 4: Causal Intelligence

Move beyond "here are errors" to "here is the causal chain explaining why."

### 4.1 EvidenceGraph

Directed graph where nodes are evidence and edges are causal relationships:

```python
class EvidenceNode(BaseModel):
    id: str
    pin: EvidencePin              # The underlying evidence
    node_type: Literal["symptom", "cause", "contributing_factor", "context"]
    temporal_position: datetime    # When this event occurred

class CausalEdge(BaseModel):
    source_id: str                # Cause node
    target_id: str                # Effect node
    relationship: Literal["causes", "correlates", "precedes", "contributes_to"]
    confidence: float             # How confident in this causal link
    reasoning: str                # Why we believe this link exists

class EvidenceGraph(BaseModel):
    nodes: list[EvidenceNode]
    edges: list[CausalEdge]
    root_causes: list[str]        # Node IDs identified as root causes
    timeline: list[str]           # Node IDs in temporal order
```

### 4.2 Hypothesis Mode vs Evidence Mode

**Phase 1 — Evidence Mode:** Agents collect evidence without forming conclusions. Each agent adds EvidenceNodes to the graph.

**Phase 2 — Hypothesis Mode:** After all agents complete, the Supervisor:
1. Builds temporal ordering of all evidence nodes
2. Uses LLM to propose causal edges between nodes
3. Identifies candidate root causes (nodes with outgoing edges but no incoming causal edges)
4. Ranks hypotheses by evidence support (number of paths, confidence scores)
5. Presents top 3 hypotheses with supporting evidence chains

### 4.3 IncidentTimeline

Ordered reconstruction of the incident:

```python
class IncidentTimeline(BaseModel):
    events: list[TimelineEvent]

class TimelineEvent(BaseModel):
    timestamp: datetime
    source: str                   # Which agent/tool detected this
    event_type: str               # "deployment", "error_spike", "pod_restart", etc.
    description: str
    evidence_node_id: str         # Link to EvidenceGraph
    severity: Literal["info", "warning", "error", "critical"]
```

The timeline is built from evidence nodes sorted temporally, providing a "what happened, in what order" view.

### 4.4 TraceRootCauseAnalysis

When Jaeger/tracing data is available:

```python
class TraceRootCause(BaseModel):
    trace_id: str
    root_span: str                # The span where the error originates
    error_propagation: list[str]  # Span chain showing error flow
    latency_breakdown: dict[str, float]  # Service → latency contribution
    bottleneck_service: str       # Service contributing most latency
```

### 4.5 UI: Evidence Graph Visualization

Right panel card showing:
- Interactive timeline (horizontal, zoomable)
- Causal chain diagram (simplified directed graph)
- Click any node to see underlying EvidencePin details
- Color-coded by evidence type (log=blue, metrics=green, k8s=yellow, trace=purple)

---

## Section 5: Change Intelligence

Dedicated agent for correlating incidents with recent changes.

### 5.1 ChangeAgent

New specialized agent added to the agent pool:

```python
class ChangeAgent(BaseAgent):
    """
    Investigates recent changes that may correlate with the incident.

    Tools:
    - github_commits: List recent commits to affected service repos
    - github_prs: List recently merged PRs
    - argocd_syncs: List recent ArgoCD sync events (if ArgoCD integrated)
    - config_diff: Compare current vs previous ConfigMap/Secret versions
    - deployment_history: oc rollout history / kubectl rollout history
    """
```

### 5.2 ChangeRiskScoring

```python
class ChangeRiskScore(BaseModel):
    change_id: str                # Commit SHA, PR number, or sync ID
    change_type: Literal["code_deploy", "config_change", "infra_change", "dependency_update"]
    risk_score: float             # 0.0 - 1.0
    temporal_correlation: float   # How close to incident start (1.0 = exact match)
    scope_overlap: float          # How much the change touches affected components
    author: str
    description: str
    files_changed: list[str]

    @property
    def likely_related(self) -> bool:
        return self.risk_score > 0.6 and self.temporal_correlation > 0.7
```

### 5.3 Deployment Correlation

The ChangeAgent checks:
1. **Git commits** in the last 24h to affected service repos
2. **ArgoCD syncs** in the last 6h to affected namespaces
3. **ConfigMap/Secret changes** via `kubectl get cm -o yaml` diff against stored previous versions
4. **Deployment rollouts** via `oc rollout history` or `kubectl rollout history`

If a deployment occurred within the incident window and touches affected services, it gets a high risk score.

### 5.4 UI: Change Correlation Card

Right panel card showing:
- Timeline of recent changes overlaid with incident start marker
- Risk-scored list of potentially related changes
- Click to see diff/details
- "Rollback" button (triggers remediation flow with safety gates)

---

## Section 6: Post-Mortem Memory

Learn from past incidents to accelerate future investigations.

### 6.1 IncidentFingerprint

```python
class IncidentFingerprint(BaseModel):
    session_id: str
    fingerprint_id: str           # Unique identifier
    created_at: datetime

    # Signal fingerprint
    error_patterns: list[str]     # Normalized error message patterns
    affected_services: list[str]
    affected_namespaces: list[str]
    symptom_categories: list[str] # "connection_timeout", "oom", "crash_loop", etc.

    # Resolution fingerprint
    root_cause: str
    root_cause_category: str      # "deployment", "config", "resource", "dependency", "infrastructure"
    resolution_steps: list[str]
    resolution_success: bool
    time_to_resolve: float        # seconds

    # Embedding for semantic search
    embedding_text: str           # Concatenated summary for vector embedding
    embedding_vector: list[float] | None  # Computed by ChromaDB
```

### 6.2 Two-Tier Similarity Matching

When a new incident starts:

**Tier 1 — Signal Matching (fast, exact):**
```python
def signal_match(current: IncidentFingerprint, stored: list[IncidentFingerprint]) -> list[Match]:
    """
    Match on: error_patterns intersection, affected_services overlap, symptom_categories overlap.
    Score = jaccard_similarity(current.signals, stored.signals)
    Return matches with score > 0.5
    """
```

**Tier 2 — Semantic Matching (slower, fuzzy):**
```python
def semantic_match(current_summary: str, collection: ChromaCollection) -> list[Match]:
    """
    Embed current incident summary, query ChromaDB for nearest neighbors.
    Return top 5 matches with distance < threshold.
    """
```

### 6.3 MemoryStore

```python
class MemoryStore:
    def __init__(self):
        self.db = ChromaDB(persist_directory="./data/memory")
        self.collection = self.db.get_or_create_collection("incidents")

    async def store_incident(self, fingerprint: IncidentFingerprint):
        """Store fingerprint after session completes (user confirms resolution)."""

    async def find_similar(self, current: IncidentFingerprint) -> list[SimilarIncident]:
        """Two-tier search: signal match first, then semantic for remaining."""

    async def get_resolution_playbook(self, fingerprint_id: str) -> list[str]:
        """Return resolution steps from a past incident."""
```

### 6.4 Novelty Detection

Before storing a new fingerprint:
```python
def is_novel(new: IncidentFingerprint, existing: list[IncidentFingerprint]) -> bool:
    """
    Only store if signal_match score < 0.8 against all existing.
    Prevents duplicate storage of recurring identical incidents.
    If not novel, update the existing fingerprint's frequency count and last_seen.
    """
```

### 6.5 UI: Memory Card

In chat, when similar past incidents are found:
```
+--- Past Incident Match ────────── 87% similar ──+
| "order-service connection timeout" (2 weeks ago) |
| Root cause: Redis connection pool exhaustion     |
| Resolution: Increased pool size to 50            |
|                          [Apply Same Resolution] |
+--------------------------------------------------+
```

---

## Section 7: Impact & Risk Modeling

Quantify the blast radius and recommend severity.

### 7.1 BlastRadius

```python
class BlastRadius(BaseModel):
    primary_service: str           # The directly affected service
    upstream_affected: list[str]   # Services that call the primary service
    downstream_affected: list[str] # Services the primary service calls
    shared_resources: list[str]    # Databases, caches, queues shared with other services
    estimated_user_impact: str     # "~5,000 users affected" (from service tier config)
    scope: Literal["single_service", "service_group", "namespace", "cluster_wide"]
```

The BlastRadius is computed by:
1. Querying the service mesh / Kubernetes service topology
2. Checking Prometheus `up` metric for related services
3. Correlating with Jaeger dependency graph (if available)

### 7.2 SeverityRecommendation

```python
class SeverityRecommendation(BaseModel):
    recommended_severity: Literal["P1", "P2", "P3", "P4"]
    reasoning: str
    factors: dict[str, str]       # {"service_tier": "critical", "blast_radius": "namespace", ...}

SEVERITY_MATRIX = {
    # (service_tier, blast_radius_scope) → severity
    ("critical", "cluster_wide"): "P1",
    ("critical", "namespace"): "P1",
    ("critical", "service_group"): "P2",
    ("critical", "single_service"): "P2",
    ("standard", "cluster_wide"): "P2",
    ("standard", "namespace"): "P3",
    ("standard", "service_group"): "P3",
    ("standard", "single_service"): "P4",
    ("internal", "cluster_wide"): "P3",
    ("internal", "namespace"): "P4",
    ("internal", "service_group"): "P4",
    ("internal", "single_service"): "P4",
}
```

### 7.3 ServiceTier Configuration

```python
class ServiceTier(BaseModel):
    service_name: str
    tier: Literal["critical", "standard", "internal"]
    slo_target: float             # e.g., 99.95
    on_call_team: str
    escalation_channel: str       # Slack channel, PagerDuty service
```

Stored alongside integrations. Users configure service tiers in Settings.

### 7.4 UI: Impact Card

Right panel card showing:
- Blast radius diagram (primary service in center, affected services radiating out)
- Severity badge (P1-P4) with color coding
- Estimated user impact
- Affected service list with status indicators

---

## Section 8: Remediation Safety

Ensure AI-proposed fixes are safe, reversible, and human-approved.

### 8.1 RunbookMatching

```python
class RunbookMatch(BaseModel):
    runbook_id: str
    title: str
    match_score: float
    matched_symptoms: list[str]    # Which symptoms matched
    steps: list[str]
    success_rate: float            # Historical success rate
    last_used: datetime | None
    source: Literal["internal", "vendor", "ai_generated"]
```

**Rule:** Always prefer a known runbook over AI-generated fix. If a runbook matches with score > 0.7, present it as the primary recommendation.

### 8.2 RemediationDecisionTree

```python
class RemediationDecision(BaseModel):
    proposed_action: str
    action_type: Literal["restart", "scale", "rollback", "config_change", "code_fix"]
    is_destructive: bool
    requires_double_confirmation: bool  # True if destructive
    dry_run_available: bool
    rollback_plan: str
    estimated_impact: str
    pre_checks: list[str]          # Checks to run before executing
    post_checks: list[str]         # Checks to verify after executing
```

### 8.3 Execution Safety

```python
class RemediationExecution:
    async def execute(self, decision: RemediationDecision):
        """
        1. Run pre_checks — abort if any fail
        2. If dry_run_available → run dry-run first, show results, get confirmation
        3. If is_destructive → require double confirmation ("type service name to confirm")
        4. Execute single action
        5. Wait observation_period (30s default)
        6. Run post_checks
        7. If post_checks fail → automatic rollback
        8. Log everything to ReasoningManifest
        """
```

**Safety rules:**
- One action at a time (no batch remediation)
- Dry-run first when available
- Destructive actions require typing the service name to confirm
- Automatic rollback if post-checks fail
- 30-second observation period between action and verification

### 8.4 DiagnosticStateV5

Extended state that flows through the entire pipeline:

```python
class DiagnosticStateV5(BaseModel):
    # Core (from v4)
    session_id: str
    service_name: str
    namespace: str | None
    time_window: tuple[datetime, datetime]

    # Integration
    integration_id: str | None     # Which cluster integration to use

    # Governance
    evidence_pins: list[EvidencePin] = []
    confidence_ledger: ConfidenceLedger = ConfidenceLedger()
    attestation_gates: list[AttestationGate] = []
    reasoning_manifest: ReasoningManifest

    # Causal Intelligence
    evidence_graph: EvidenceGraph = EvidenceGraph(nodes=[], edges=[], root_causes=[], timeline=[])
    hypotheses: list[Hypothesis] = []
    incident_timeline: IncidentTimeline = IncidentTimeline(events=[])

    # Change Intelligence
    change_correlations: list[ChangeRiskScore] = []

    # Memory
    similar_incidents: list[SimilarIncident] = []

    # Impact
    blast_radius: BlastRadius | None = None
    severity_recommendation: SeverityRecommendation | None = None

    # Remediation
    runbook_matches: list[RunbookMatch] = []
    remediation_decisions: list[RemediationDecision] = []
    remediation_results: list[RemediationResult] = []
```

---

## Implementation Priority

Based on dependency analysis and SRE value:

| Phase | Section | Rationale |
|-------|---------|-----------|
| 1 | Governance & Safety | Foundation — everything else depends on evidence pinning and confidence tracking |
| 2 | Integration Registry | Enables cluster connectivity for all agents; removes user friction |
| 3 | Resilience | Makes existing agents production-ready with fallbacks and budget controls |
| 4 | Causal Intelligence | Core differentiator — transforms output from "errors found" to "root cause chain" |
| 5 | Change Intelligence | High SRE value — most incidents correlate with recent changes |
| 6 | Post-Mortem Memory | Accelerates recurring incidents; requires completed sessions to build corpus |
| 7 | Impact & Risk | Useful but not blocking — severity recommendation helps prioritization |
| 8 | Remediation Safety | Last because it depends on all other phases being solid; highest risk if done wrong |

---

## API Endpoints Summary

### Governance
```
GET  /api/v5/session/{id}/evidence-graph     — Get evidence graph
GET  /api/v5/session/{id}/confidence          — Get confidence ledger
GET  /api/v5/session/{id}/reasoning           — Get reasoning manifest
POST /api/v5/session/{id}/attestation         — Submit human attestation decision
GET  /api/v5/session/{id}/timeline            — Get incident timeline
```

### Integrations
```
POST   /api/v5/integrations                   — Add integration
GET    /api/v5/integrations                   — List integrations
GET    /api/v5/integrations/{id}              — Get integration
PUT    /api/v5/integrations/{id}              — Update integration
DELETE /api/v5/integrations/{id}              — Delete integration
POST   /api/v5/integrations/{id}/probe        — Probe/verify integration
```

### Memory
```
GET  /api/v5/memory/similar?session_id={id}   — Find similar past incidents
GET  /api/v5/memory/incidents                  — List stored incident fingerprints
POST /api/v5/memory/incidents                  — Store incident fingerprint
```

### Remediation
```
POST /api/v5/session/{id}/remediation/propose  — Propose remediation
POST /api/v5/session/{id}/remediation/dry-run  — Execute dry-run
POST /api/v5/session/{id}/remediation/execute  — Execute remediation (requires attestation)
POST /api/v5/session/{id}/remediation/rollback — Rollback last action
```

---

## What Stays the Same

- **Supervisor + ReAct architecture** (v4 core preserved)
- **Existing agents** (log_analyzer, metrics_agent, k8s_agent, code_navigator, fix_generator) — enhanced, not replaced
- **WebSocket real-time updates** (existing infrastructure)
- **Frontend component library** (DebugDuck design system, Action Center)
- **AnthropicClient** (v4 LLM client)
- **All existing tests** (116 passing, must remain passing)

## What Changes

| Component | Change |
|-----------|--------|
| DiagnosticState | Extended to DiagnosticStateV5 with governance, causal, memory fields |
| Supervisor | Add confidence tracking, evidence graph building, hypothesis mode, attestation gates |
| All agents | Must return EvidencePin with every finding, respect ReActBudget |
| Log Analyzer | Add TieredLogProcessing, DiscoveryFallback |
| New: ChangeAgent | Dedicated change correlation agent |
| New: IntegrationRegistry | Backend service + SQLite storage + API endpoints |
| New: MemoryStore | ChromaDB-based incident memory with fingerprinting |
| New: RemediationEngine | Safe execution with dry-run, rollback, pre/post checks |
| Frontend: ResultsPanel | Add EvidenceGraph card, Timeline card, Impact card, Memory card |
| Frontend: Settings | New page for integration management |
| Frontend: Chat | AttestationGate UI, remediation confirmation dialogs |

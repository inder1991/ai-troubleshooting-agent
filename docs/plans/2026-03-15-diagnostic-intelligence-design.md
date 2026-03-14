# Diagnostic Intelligence Engine — Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform cluster diagnostics from LLM-first reasoning to evidence-graph + failure-patterns + hypothesis-ranking + LLM-synthesis — making LLM the last step, not the main brain.

**Architecture:** Layered pipeline of 6 new deterministic nodes inserted between domain agents and synthesizer, plus enhanced critic, solution validator, and frontend overhaul. All new stages are zero LLM cost.

---

## Pipeline Overview

```
PRE-PROCESSING (existing, unchanged)
  START → rbac_preflight → topology → correlator → firewall → dispatch_router

DATA GATHERING (existing, unchanged)
  → [5 domain agents in parallel]

DIAGNOSTIC INTELLIGENCE (6 new deterministic nodes, ~25s total, zero LLM cost)
  → signal_normalizer (3s)
  → failure_pattern_matcher (5s)
  → temporal_analyzer (3s)
  → diagnostic_graph_builder (5s)
  → issue_lifecycle_classifier (5s)
  → hypothesis_engine (10s)

VALIDATION + SYNTHESIS (enhanced existing)
  → enhanced_critic (8s, deterministic)
  → synthesizer (LLM — explain + remediate, doesn't override ranking)
  → solution_validator (8s, deterministic)

OUTPUT (existing, enhanced)
  → guard_formatter → END
```

---

## Section 1: Known Failure Pattern Library

### Signal Normalization

Before pattern matching, raw domain report data gets normalized into canonical signals.

```python
class NormalizedSignal(BaseModel):
    signal_id: str = ""
    signal_type: str              # "CRASHLOOP", "NODE_DISK_PRESSURE", etc.
    resource_key: str             # "pod/production/payments-api-abc123"
    source_domain: str            # "node", "network", etc.
    raw_value: Any = None
    reliability: float = 0.5     # Signal weight
    timestamp: str = ""
    namespace: str = ""
```

Signal extraction rules (deterministic):

| Raw Data | Normalized Signal | Reliability |
|----------|------------------|-------------|
| pod.status == "CrashLoopBackOff" | `CRASHLOOP` | 0.8 |
| pod.status == "OOMKilled" | `OOM_KILLED` | 0.9 |
| node.condition.DiskPressure == True | `NODE_DISK_PRESSURE` | 1.0 |
| deployment.replicas_ready < desired | `DEPLOYMENT_DEGRADED` | 0.9 |
| service.endpoints == 0 | `SERVICE_ZERO_ENDPOINTS` | 0.9 |
| event.reason == "FailedScheduling" | `FAILED_SCHEDULING` | 0.6 |
| HPA.scaling_limited == True | `HPA_AT_MAX` | 0.9 |
| PVC.phase == "Pending" | `PVC_PENDING` | 0.9 |
| pod.restarts > 5 | `HIGH_RESTART_COUNT` | 0.8 |
| daemonset.number_unavailable > 0 | `DAEMONSET_INCOMPLETE` | 0.9 |

Pipeline node:

```python
@traced_node(timeout_seconds=3)
async def signal_normalizer(state: dict, config: dict) -> dict:
    """Extract canonical signals from domain reports. Deterministic."""
    reports = state.get("domain_reports", [])
    signals = extract_signals(reports)
    return {"normalized_signals": signals}
```

### Pattern Model

```python
@dataclass
class FailurePattern:
    pattern_id: str
    name: str
    version: str = "1.0"
    scope: str = "resource"           # "resource" | "namespace" | "cluster"
    priority: int = 5                 # Higher wins on conflict (10 > 5)
    conditions: list[dict]            # {"signal": "CRASHLOOP"}, {"signal": "OOM_KILLED"}
    probable_causes: list[str]
    known_fixes: list[str]
    severity: str
    confidence_boost: float           # Added to hypothesis confidence when matched
```

### Pattern Match Output (traceable evidence)

```python
@dataclass
class PatternMatch:
    pattern_id: str
    name: str
    matched_conditions: list[str]     # Which signals matched
    affected_resources: list[str]     # Which resources were involved
    confidence_boost: float
    severity: str
    scope: str
    probable_causes: list[str]
    known_fixes: list[str]
```

### Starter Pattern Library (~15 patterns)

| Pattern | Conditions | Probable Cause | Priority |
|---------|-----------|----------------|----------|
| CrashLoop + OOM | CRASHLOOP + OOM_KILLED | Memory limit too low | 10 |
| CrashLoop + config | CRASHLOOP + no OOM | Bad env/secret/configmap | 5 |
| Service zero endpoints | SERVICE_ZERO_ENDPOINTS | Selector mismatch or no ready pods | 8 |
| Pod Pending + insufficient CPU | FAILED_SCHEDULING | Cluster capacity / resource requests | 7 |
| Node NotReady + DiskPressure | NODE_NOT_READY + NODE_DISK_PRESSURE | Disk full | 9 |
| HPA at max + unmet target | HPA_AT_MAX | Cluster capacity ceiling | 7 |
| ImagePullBackOff | IMAGE_PULL_BACKOFF | Bad image tag or registry auth | 6 |
| Deployment stuck rollout | DEPLOYMENT_DEGRADED + ROLLOUT_STUCK | Bad readiness probe or resource issue | 8 |
| PVC Pending | PVC_PENDING | No matching StorageClass or capacity | 6 |
| DNS resolution failure | DNS_FAILURE | CoreDNS pod crash or config | 8 |
| Certificate expiry | CERT_EXPIRY_SOON | Cert-manager misconfigured | 7 |
| Node pressure evictions | POD_EVICTION + NODE_PRESSURE | Node undersized or noisy neighbor | 9 |
| DaemonSet incomplete | DAEMONSET_INCOMPLETE | Node taint or resource conflict | 5 |
| NetworkPolicy blocking | NETPOL_EMPTY_INGRESS + SERVICE_UNREACHABLE | Overly restrictive policy | 7 |
| Job backoff exceeded | JOB_BACKOFF_EXCEEDED | Application bug or dependency failure | 5 |

### Pipeline Node

```python
@traced_node(timeout_seconds=5)
async def failure_pattern_matcher(state: dict, config: dict) -> dict:
    """Match normalized signals against known failure patterns. Zero LLM cost."""
    reports = state.get("domain_reports", [])
    signals = state.get("normalized_signals", [])
    matches = match_patterns(reports, signals, FAILURE_PATTERNS)
    matches = resolve_priority_conflicts(matches)
    return {"pattern_matches": matches}
```

### Pattern → Hypothesis Seeding

Each matched pattern automatically creates a hypothesis seed:

```
PatternMatch(CRASHLOOP_OOM, confidence_boost=0.2)
  → Hypothesis(cause="Memory limit too low", initial_confidence=0.6, source="pattern")
```

---

## Section 2: Diagnostic Evidence Graph, Temporal Analysis, and Issue Lifecycle

### Diagnostic Graph Model

Built ON TOP of topology graph — not replacing it.

```python
class DiagnosticNode(BaseModel):
    node_id: str
    node_type: str = "signal"         # "signal" | "resource" | "pattern" | "hypothesis"
    resource_key: str = ""
    signal_type: str = ""
    severity: str = "medium"
    reliability: float = 0.5
    first_seen: str = ""
    last_seen: str = ""
    event_age_seconds: int = 0
    restart_velocity: float = 0.0
    resource_age_seconds: int = 0
    event_count_recent: int = 0       # Last 5 min
    event_count_baseline: int = 0     # Last 60 min
    namespace: str = ""

class DiagnosticEdge(BaseModel):
    from_id: str
    to_id: str
    edge_type: str                    # "CAUSES" | "DEPENDS_ON" | "OBSERVED_AFTER" | "AFFECTS" | "SYMPTOM_OF"
    confidence: float = 0.5
    evidence: str = ""

class DiagnosticGraph(BaseModel):
    nodes: dict[str, DiagnosticNode]
    edges: list[DiagnosticEdge]
```

### Edge Creation Rules (deterministic)

| Condition | Edge Type |
|-----------|-----------|
| Node pressure + pod eviction on same node | `CAUSES` |
| Deployment owns evicted pods | `AFFECTS` |
| Service selector matches degraded deployment | `DEPENDS_ON` |
| Two signals share resource_key | `OBSERVED_AFTER` (temporal) |
| Pattern match links signals | `SYMPTOM_OF` |

### Temporal Analyzer

Computes temporal attributes using K8s timestamps — no history storage needed.

```python
@traced_node(timeout_seconds=3)
async def temporal_analyzer(state: dict, config: dict) -> dict:
    """Compute issue age, recency, restart velocity from K8s timestamps."""
```

**Worsening detection (no stored history):**

```python
def detect_worsening(node: DiagnosticNode) -> bool:
    # Event rate spike: recent rate > 3x baseline rate
    baseline_rate = max(1, node.event_count_baseline) / 60
    recent_rate = max(0, node.event_count_recent) / 5
    if recent_rate > 3 * baseline_rate:
        return True

    # Restart velocity acceleration
    if node.restart_velocity > 0.5 and node.event_age_seconds < 300:
        return True

    # Cascade growth
    if node.recent_downstream_count > node.baseline_downstream_count:
        return True

    return False
```

### Issue Lifecycle — 9 States

```python
class IssueState(str, Enum):
    ACTIVE_DISRUPTION = "ACTIVE_DISRUPTION"   # Currently breaking, immediate attention
    WORSENING         = "WORSENING"           # Trending worse
    NEW               = "NEW"                 # Newly observed, recent events
    EXISTING          = "EXISTING"            # Present but stable
    LONG_STANDING     = "LONG_STANDING"       # Old persistent issue
    INTERMITTENT      = "INTERMITTENT"        # Flapping, recurring
    SYMPTOM           = "SYMPTOM"             # Downstream effect linked to root cause
    RESOLVED          = "RESOLVED"            # No longer observed
    ACKNOWLEDGED      = "ACKNOWLEDGED"        # Known & tracked, out of scope
```

### Issue Model

```python
class DiagnosticIssue(BaseModel):
    issue_id: str
    state: IssueState
    priority_score: float
    first_seen: str
    last_state_change: str
    state_duration_seconds: int
    event_count_recent: int
    event_count_baseline: int
    restart_velocity: float
    severity_trend: str               # "escalating" | "stable" | "de-escalating"
    is_root_cause: bool
    is_symptom: bool
    root_cause_id: str
    blast_radius: int
    affected_resources: list[str]
    signals: list[str]
    pattern_matches: list[str]
    anomaly_ids: list[str]
```

### State Classification (ordered evaluation)

```python
def classify_issue_state(issue: DiagnosticIssue) -> IssueState:
    if issue.is_symptom:
        return IssueState.SYMPTOM
    if (issue.event_age_seconds < 120
        and (issue.restart_velocity > 1.0 or issue.blast_radius > 2)):
        return IssueState.ACTIVE_DISRUPTION
    if detect_worsening(issue):
        return IssueState.WORSENING
    if issue.flap_count > 3:
        return IssueState.INTERMITTENT
    if issue.first_seen_seconds < 900:
        return IssueState.NEW
    if issue.resource_age_seconds > 86400:
        return IssueState.LONG_STANDING
    return IssueState.EXISTING
```

### Config Knobs (tunable per cluster)

```python
@dataclass
class LifecycleThresholds:
    active_event_age_seconds: int = 120
    active_restart_velocity: float = 1.0
    active_blast_radius_min: int = 2
    worsening_rate_multiplier: float = 3.0
    new_first_seen_seconds: int = 900
    long_standing_age_seconds: int = 86400
    flap_count_threshold: int = 3
    intermittent_window_seconds: int = 600
```

### Priority Scoring

```python
STATE_WEIGHT = {
    IssueState.ACTIVE_DISRUPTION: 4.0,
    IssueState.WORSENING: 2.5,
    IssueState.NEW: 2.0,
    IssueState.EXISTING: 0.5,
    IssueState.LONG_STANDING: 0.0,
    IssueState.INTERMITTENT: 0.5,
    IssueState.SYMPTOM: -1.5,
    IssueState.RESOLVED: -3.0,
    IssueState.ACKNOWLEDGED: -2.0,
}

SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}

priority = (
    SEVERITY_WEIGHT[severity]
    + 0.5 * blast_radius
    + STATE_WEIGHT[state]
    + (2.0 if is_root_cause else 0)
)
```

### State Transitions

```
NEW → WORSENING → ACTIVE_DISRUPTION → RESOLVED
EXISTING → WORSENING → ACTIVE_DISRUPTION
INTERMITTENT ↔ EXISTING (flap detection)
Any → ACKNOWLEDGED (operator marks)
Any → SYMPTOM (when linked to root cause)
```

---

## Section 3: Multi-Hypothesis Root Cause Engine

### Signal Confidence Weights

```python
SIGNAL_RELIABILITY = {
    "node_condition": 1.0,
    "deployment_status": 0.9,
    "pod_phase": 0.8,
    "pvc_status": 0.9,
    "hpa_status": 0.9,
    "daemonset_status": 0.9,
    "service_endpoints": 0.9,
    "k8s_event_warning": 0.6,
    "k8s_event_normal": 0.3,
    "prometheus_metric": 0.5,
    "resource_utilization": 0.6,
    "pod_log": 0.4,
    "coredns_log": 0.4,
    "alert_firing": 0.3,
    "pattern_match": 0.8,
}
```

### Hypothesis Model

```python
class Hypothesis(BaseModel):
    hypothesis_id: str
    cause: str
    cause_type: str
    source: str                       # "pattern" | "graph_traversal" | "signal_correlation"
    supporting_evidence: list[WeightedEvidence]
    contradicting_evidence: list[WeightedEvidence]
    evidence_score: float
    contradiction_penalty: float
    confidence: float
    affected_issues: list[str]
    explains_count: int
    blast_radius: int
    issue_state: Optional[IssueState] = None
    root_resource: str
    causal_chain: list[str]           # Ordered evidence chain
    depth: int                        # Chain length
    evidence_ids: list[str]

class WeightedEvidence(BaseModel):
    signal_id: str = ""
    signal_type: str = ""
    resource_key: str = ""
    weight: float = 0.5
    reliability: float = 0.5
    relevance: str = ""
```

### Hypothesis Generation (3 sources, deterministic)

1. **Pattern seeds** — each PatternMatch becomes a hypothesis at confidence 0.5 + boost
2. **Graph traversal** — root nodes (outgoing CAUSES, no incoming CAUSES) in the diagnostic graph
3. **Signal correlation** — signals sharing topology dependency + namespace + temporal proximity (<60s)

### Negative Evidence Collection

```python
CONTRADICTION_RULES = [
    {"hypothesis_type": "SERVICE_ZERO_ENDPOINTS",
     "check": "SERVICE_HEALTHY signal present",
     "contradiction": "Service has healthy endpoints"},
    {"hypothesis_type": "OOM_KILLED",
     "check": "MEMORY_UTILIZATION < 70%",
     "contradiction": "Memory usage below 70%"},
    {"hypothesis_type": "NODE_PRESSURE_EVICTION",
     "check": "evicted pods rescheduled and running",
     "contradiction": "Evicted pods rescheduled successfully"},
    {"hypothesis_type": "DNS_FAILURE",
     "check": "DNS_SUCCESS_RATE > 95%",
     "contradiction": "DNS success rate normal"},
]
```

Also uses `ruled_out` items from domain agents as contradicting evidence.

### Hypothesis Scoring

```python
MAX_SIGNAL_CONTRIBUTION = 0.6

def score_hypothesis(h: Hypothesis) -> float:
    # Capped evidence — no single signal dominates
    evidence_score = sum(
        min(e.weight * e.signal.reliability, MAX_SIGNAL_CONTRIBUTION)
        for e in h.supporting_evidence
    )

    # Contradiction penalty — uncapped
    contradiction_penalty = sum(
        e.weight * e.signal.reliability
        for e in h.contradicting_evidence
    )

    # Explanatory bonus — more signals explained = better
    explanatory_bonus = h.explains_count * 0.1

    # Diversity bonus — multiple signal types > repeated same
    unique_types = len(set(e.signal.signal_type for e in h.supporting_evidence))
    diversity_bonus = unique_types * 0.05

    # Depth penalty — closer causes rank higher
    depth_penalty = h.depth * 0.05

    raw_score = (evidence_score
                 - contradiction_penalty
                 + explanatory_bonus
                 + diversity_bonus
                 - depth_penalty)

    # Logistic normalization
    confidence = 1.0 / (1.0 + math.exp(-raw_score))
    return confidence
```

### Deduplication (merge key: resource_key + signal_family)

```python
SIGNAL_FAMILIES = {
    "CRASHLOOP": "pod_failure", "OOM_KILLED": "pod_failure",
    "NODE_DISK_PRESSURE": "node_pressure", "NODE_MEMORY_PRESSURE": "node_pressure",
    "DEPLOYMENT_DEGRADED": "workload_health",
    "SERVICE_ZERO_ENDPOINTS": "service_health",
    "PVC_PENDING": "storage", "HPA_AT_MAX": "scaling",
}
```

### Filtering and Caps

```python
MIN_EVIDENCE_SCORE = 0.4
MAX_HYPOTHESES_PER_ISSUE = 3
MAX_TOTAL_HYPOTHESES = 8
```

### LLM Role — Explain, Don't Select

```python
def determine_root_causes(ranked_hypotheses):
    top = ranked_hypotheses[0]
    runner_up = ranked_hypotheses[1] if len(ranked_hypotheses) > 1 else None

    # Clear winner: deterministic selection, no LLM
    if not runner_up or (top.confidence - runner_up.confidence) > 0.15:
        return {"root_causes": [top], "selection_method": "deterministic", "llm_reasoning_needed": False}

    # Ambiguous: LLM disambiguates
    return {"root_causes": ranked_hypotheses[:3], "selection_method": "ambiguous_needs_llm", "llm_reasoning_needed": True}
```

LLM's job:
1. Explain the deterministic selection in natural language
2. Generate remediation for top 3 root causes
3. Only when gap < 0.15: choose between close candidates
4. Flag anything the engine missed (low confidence addendum)

### Per-Issue Hypothesis Storage

```python
{
    "ranked_hypotheses": [...],           # Global top 8
    "hypotheses_by_issue": {              # Per issue cluster
        "issue-001": [h1, h2],
        "issue-002": [h3],
    },
    "hypothesis_selection": {
        "root_causes": [...],
        "selection_method": "deterministic",
        "llm_reasoning_needed": False,
    },
}
```

---

## Section 4: Enhanced Critic + Solution Validator

### Enhanced Critic — 6 Validation Layers

```python
@traced_node(timeout_seconds=8)
async def enhanced_critic(state: dict, config: dict) -> dict:
    """Multi-layer validation of hypotheses. Deterministic."""
```

| Layer | Check | Result on Failure |
|-------|-------|-------------------|
| 1. Evidence traceable | Every supporting signal exists in normalized_signals | REJECTED |
| 2. Resource exists | root_resource exists in topology | REJECTED |
| 3. Causal chain valid | Every edge in chain exists in diagnostic graph | REJECTED |
| 4. Contradiction ratio | contradicting > supporting evidence | REJECTED (>1.0), WEAKENED (>0.5) |
| 5. Temporal consistency | Root cause first_seen <= all downstream first_seen | REJECTED |
| 6. Graph reachability | Root resource can reach all affected issues via BFS | REJECTED |

### Solution Validator

```python
@traced_node(timeout_seconds=8)
async def solution_validator(state: dict, config: dict) -> dict:
    """Validate remediation safety. Deterministic."""
```

**Safety checks:**
- Single-replica deletion: pod delete when deployment replicas=1 → dangerous
- Node drain capacity: draining 1-of-2 nodes → dangerous
- Scale-to-zero: --replicas=0 → dangerous
- Namespace-wide delete: delete --all → dangerous
- Fixes root cause, not symptom: destructive action on non-root resource → caution

**Forbidden commands (blocked entirely):**
```python
FORBIDDEN_COMMANDS = [
    "kubectl delete namespace", "kubectl delete node",
    "kubectl delete pvc", "kubectl delete pv",
    "kubectl delete clusterrole", "kubectl delete crd",
    "kubectl delete storageclass", "kubectl replace --force",
]
```

**Remediation simulation:**
```python
OWNER_BEHAVIOR = {
    "ReplicaSet": "safe_recreated",
    "DaemonSet": "safe_recreated",
    "StatefulSet": "safe_recreated",
    "Job": "may_not_restart",
    "None": "permanent_delete",
}
```

Simulates: pod delete → will it be recreated? Node drain → enough capacity? Scale → what happens?

**Remediation confidence score:**
```python
def compute_remediation_confidence(step, hypothesis, simulation, risk):
    score = hypothesis.confidence * 0.4
    if step.source == "pattern": score += 0.3     # Known fix
    if "safe" in simulation.impact: score += 0.2
    if simulation.side_effects: score -= 0.1
    if risk == "dangerous": score -= 0.2
    return clamp(score, 0.0, 1.0)
```

| Score | Label | UI Treatment |
|-------|-------|-------------|
| >= 0.8 | High confidence fix | Green, prominent |
| >= 0.5 | Likely fix | Amber, with context |
| >= 0.3 | Speculative | Gray, "investigate" |
| < 0.3 | Low confidence | Hidden from remediation, moved to findings |

### Tiered Remediation Output

```python
class ClusterHealthReport:
    critical_incidents: list[Incident]    # Max 3, full remediation
    other_findings: list[Issue]           # Investigation hints only
    symptom_map: dict[str, str]           # symptom_id → root_cause_id
```

Rules:
- Max 3 detailed remediations (with commands, rollback, verify, simulation)
- Symptoms never get their own remediation — linked to root cause
- Related issues batched (3 CrashLoop pods from same deployment = 1 incident)
- Long-standing issues labeled "Known" with lower priority

---

## Section 5: State Model Changes and Graph Wiring

### New State Fields in graph.py

```python
class State(TypedDict):
    # ... existing fields ...
    normalized_signals: list[dict]
    pattern_matches: list[dict]
    temporal_analysis: Optional[dict]
    diagnostic_graph: Optional[dict]
    diagnostic_issues: list[dict]
    ranked_hypotheses: list[dict]
    hypotheses_by_issue: Optional[dict]
    hypothesis_selection: Optional[dict]
```

### Graph Wiring

```python
# Fan-in: agents → NEW diagnostic intelligence pipeline
graph.add_edge("ctrl_plane_agent", "signal_normalizer")
graph.add_edge("node_agent", "signal_normalizer")
graph.add_edge("network_agent", "signal_normalizer")
graph.add_edge("storage_agent", "signal_normalizer")
graph.add_edge("rbac_agent", "signal_normalizer")

# Sequential intelligence pipeline
graph.add_edge("signal_normalizer", "failure_pattern_matcher")
graph.add_edge("failure_pattern_matcher", "temporal_analyzer")
graph.add_edge("temporal_analyzer", "diagnostic_graph_builder")
graph.add_edge("diagnostic_graph_builder", "issue_lifecycle_classifier")
graph.add_edge("issue_lifecycle_classifier", "hypothesis_engine")
graph.add_edge("hypothesis_engine", "enhanced_critic")

# Critic → Synthesizer → Solution Validator → Guard Formatter
graph.add_edge("enhanced_critic", "synthesize")
graph.add_edge("synthesize", "solution_validator")
graph.add_conditional_edges("solution_validator", _should_redispatch, {...})
graph.add_edge("guard_formatter", END)
```

### New Backend Files

| File | Purpose | Timeout |
|------|---------|---------|
| `signal_normalizer.py` | Extract canonical signals from domain reports | 3s |
| `failure_patterns.py` | 15 patterns + matcher + priority resolution | 5s |
| `temporal_analyzer.py` | Issue age, event recency, restart velocity, worsening detection | 3s |
| `diagnostic_graph_builder.py` | Cross-domain evidence graph with typed edges | 5s |
| `issue_lifecycle.py` | 9 lifecycle states, priority scoring, config knobs | 5s |
| `hypothesis_engine.py` | 3-source generation, negative evidence, scoring, ranking, selection | 10s |

### Modified Backend Files

| File | Changes |
|------|---------|
| `state.py` | ~12 new models (NormalizedSignal through SolutionValidation) |
| `graph.py` | 6 new nodes, rewired edges, new state fields |
| `critic_agent.py` → `enhanced_critic.py` | 6-layer validation + graph reachability |
| `synthesizer.py` | Receives ranked hypotheses, tiered output, LLM doesn't override |
| `guard_formatter.py` | Reads diagnostic_issues for lifecycle-aware output |

---

## Section 6: Frontend UI Overhaul

Based on the design critique, the following fixes are required.

### Fix 1: Replace center column DomainPanel with IssuePriorityPanel

The center column currently groups findings by domain agent. Operators think in priority, not domain.

**Create `IssuePriorityPanel.tsx`:**

Shows tiered issues grouped by lifecycle state:

```
🔴 Active Disruptions (1)
   NodeDiskPressure on node-1
   Impact: 5 pods evicted │ Blast radius: 3 deployments
   Trend: ↑ worsening │ Confidence: 0.82

🟠 Escalating (1)
   CrashLoopBackOff payments-api
   First seen: 2m ago │ Restarts: 45/min

🟡 Known Issues (1)
   PVC Pending analytics-db
   Age: 4 days │ Impact: batch jobs only

⚪ Symptoms (1)
   Service endpoints=0 → caused by CrashLoopBackOff
```

Design rules:
- NOT identical cards — each tier has distinct visual weight
- Active: left border red, larger text, bold
- Escalating: left border amber, normal weight
- Known: left border slate, muted, compact
- Symptoms: no border, italic, linked to root cause with "→"
- DomainPanel becomes secondary tab via VerticalRibbon

### Fix 2: Replace Domain Health Ribbon with Lifecycle Summary Strip

**Create `LifecycleSummaryStrip.tsx`:**

Single row (36px height, not a grid of cards):

```
[ ● 1 Active | ● 1 Escalating | ● 2 Known | ● 1 Symptom ] │ 5 domains │ 87% complete
```

Colored dots with counts. Right side: scan metadata. No MetricCards.

### Fix 3: Remove decorative noise

- Remove `NeuralPulseSVG` — decorative animated SVG with no information
- Remove `crt-scanlines` class — hacker aesthetic, not Mission Control
- Remove `ResourceVelocity` — shows static placeholder data

### Fix 4: Merge ExecutionDAG + AgentTimeline

Create single `ExecutionProgress.tsx` that shows DAG nodes with inline timeline bars. Frees ~200px for FleetHeatmap.

Fix ExecutionDAG agent count: currently hardcoded to `/4` but 5 agents exist.

### Fix 5: HypothesisCard replaces RootCauseCard

**Create `HypothesisCard.tsx`:**

Shows ranked hypotheses with confidence bars, not just one root cause:

```
Root Cause Hypotheses

#1  NodeMemoryPressure          ████████░░  0.82
    Evidence: 4 supporting, 1 contradicting
    Chain: Node → Pod → Deployment (depth 3)
    Source: graph + pattern

#2  ConfigError payments-api    ██████░░░░  0.65
    Evidence: 3 supporting, 0 contradicting
    Chain: Pod (depth 1)
    Source: pattern (CRASHLOOP_CONFIG)
```

Cascading effects from current VerdictStack become expandable section inside this card.

### Fix 6: SimulationPreview inside RemediationCard

Not a separate component. Before the hold-to-execute button, show:

```
Impact Simulation
Action: delete pod/payments-api-abc123
Impact: safe_recreated (ReplicaSet will recreate)
Side effects: none
Confidence: 0.78 (Likely fix)
[Hold to Execute]
```

Add remediation confidence badge (green/amber/gray based on score).
If `blocked == true`, show block reason and hide execute button.
If `requires_confirmation == true`, show warning before hold-to-execute.

### Fix 7: FleetHeatmap cleanup

- Remove 60-node placeholder grid for empty state — show "Waiting for node data" instead
- Keep existing heatmap for real data

### Fix 8: Minor cleanups

- Standardize panel backgrounds: use `bg-[#141210]` consistently, not mixed `bg-[#152a2f]/40`
- VerticalRibbon: add lifecycle-colored dots instead of just anomaly counts
- Remove unused sparklineData with identical values

### Updated ClusterWarRoom Layout

```
ClusterHeader (with LLMCostBadge)
LifecycleSummaryStrip (single row, 36px)
┌─────────────┬──────────────────────┬────────────────┐
│ LEFT (col-3) │ CENTER (col-5)       │ RIGHT (col-4)  │
│              │                      │                │
│ Execution    │ IssuePriorityPanel   │ HypothesisCard │
│ Progress     │ (primary view)       │                │
│              │                      │ RemediationCard│
│ Fleet        │  OR                  │ (with sim +    │
│ Heatmap      │                      │  confidence)   │
│              │ DomainPanel          │                │
│              │ (via ribbon tabs)    │ ScanDiff       │
│              │                      │ (guard only)   │
└─────────────┴──────────────────────┴────────────────┘
EventLogViewer (collapsible)
CommandBar
```

State variable: `centerView: 'priority' | ClusterDomainKey` defaulting to 'priority'.

### New Frontend Components

| Component | Replaces |
|-----------|----------|
| `IssuePriorityPanel.tsx` | DomainPanel (as default center view) |
| `LifecycleSummaryStrip.tsx` | Domain Health Ribbon (MetricCards grid) |
| `HypothesisCard.tsx` | RootCauseCard + VerdictStack |
| `ExecutionProgress.tsx` | ExecutionDAG + AgentTimeline + ResourceVelocity |

### Removed Components

| Component | Reason |
|-----------|--------|
| `NeuralPulseSVG.tsx` | Decorative noise, hardcoded coordinates |
| `ResourceVelocity.tsx` | Static placeholder data |

### Modified Components

| Component | Changes |
|-----------|---------|
| `ClusterWarRoom.tsx` | New layout, new state, remove decorative imports |
| `RemediationCard.tsx` | Inline simulation preview, confidence badge, blocked state |
| `FleetHeatmap.tsx` | Remove placeholder nodes, proper empty state |
| `VerticalRibbon.tsx` | Lifecycle-colored dots |

---

## API Changes

### Modified `/session/{id}/findings` response

```json
{
  "...existing fields...",
  "diagnostic_issues": [...],
  "issue_lifecycle_summary": {"ACTIVE_DISRUPTION": 1, "WORSENING": 1, ...},
  "ranked_hypotheses": [...],
  "critical_incidents": [...],
  "other_findings": [...],
  "symptom_map": {"symptom-001": "root-cause-001"}
}
```

### Lifecycle Config Endpoint

```
GET  /cluster/lifecycle-config → current thresholds
PUT  /cluster/lifecycle-config → update thresholds
```

---

## Implementation File Summary

### New files (6 backend + 4 frontend):

**Backend:**
1. `backend/src/agents/cluster/signal_normalizer.py`
2. `backend/src/agents/cluster/failure_patterns.py`
3. `backend/src/agents/cluster/temporal_analyzer.py`
4. `backend/src/agents/cluster/diagnostic_graph_builder.py`
5. `backend/src/agents/cluster/issue_lifecycle.py`
6. `backend/src/agents/cluster/hypothesis_engine.py`

**Frontend:**
7. `frontend/src/components/ClusterDiagnostic/IssuePriorityPanel.tsx`
8. `frontend/src/components/ClusterDiagnostic/LifecycleSummaryStrip.tsx`
9. `frontend/src/components/ClusterDiagnostic/HypothesisCard.tsx`
10. `frontend/src/components/ClusterDiagnostic/ExecutionProgress.tsx`

### Modified files (8 backend + 5 frontend):

**Backend:**
1. `state.py` — ~12 new models
2. `graph.py` — 6 new nodes, rewired edges
3. `critic_agent.py` → enhanced 6-layer validation
4. `synthesizer.py` — hypothesis-aware, tiered output
5. `guard_formatter.py` — lifecycle-aware
6. `command_validator.py` — forbidden commands, simulation
7. `routes_v4.py` — lifecycle config endpoint
8. `hallucination_detector.py` — integrated into critic

**Frontend:**
9. `ClusterWarRoom.tsx` — new layout, remove decorative components
10. `RemediationCard.tsx` — simulation, confidence, blocked state
11. `FleetHeatmap.tsx` — proper empty state
12. `VerticalRibbon.tsx` — lifecycle dots
13. `types/index.ts` — new types

### Removed files:

- `NeuralPulseSVG.tsx`
- `ResourceVelocity.tsx`

---

## Expected Impact

| Metric | Improvement |
|--------|-------------|
| Root cause accuracy | +20-30% (pattern library + hypothesis ranking) |
| False root causes | -50% (negative evidence + critic 6-layer validation) |
| LLM cost per scan | -30-50% (6 deterministic stages replace LLM reasoning) |
| Diagnostic latency | Neutral (~25s added deterministic, but less LLM) |
| Remediation safety | +40% (simulation + forbidden list + confidence scoring) |
| Operator trust | Significantly higher (explainable hypotheses, tiered output) |
| Consistency | Much higher (deterministic pattern matching + scoring) |

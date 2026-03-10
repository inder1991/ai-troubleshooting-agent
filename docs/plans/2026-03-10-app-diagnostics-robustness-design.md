# App Diagnostics Robustness Upgrade — Design Document

**Date:** 2026-03-10
**Status:** Approved
**Scope:** Comprehensive robustness upgrade across 10 areas — evidence graph, critic ensemble, chat tool calling, tracing agent, multi-repo fixes, LLM prompt framework, live data refresh, observability correlations, token overflow protection, multi-file visibility.

---

## Architectural Principle: Additive Layer, Never Replace

The existing `DiagnosticState` orchestration is **untouched**. All new capabilities are additive layers that READ from state but never replace its mutation flow.

```
Agent Result (raw dict)
    │
    ▼
_update_state_with_result()         ◄── UNTOUCHED
    │
    ├── state.log_analysis = ...     ◄── UNTOUCHED
    ├── state.all_findings.append()  ◄── UNTOUCHED
    ├── state.overall_confidence     ◄── UNTOUCHED
    │
    ▼
_ingest_into_graph(state, agent)    ◄── NEW (additive)
    │
    ├── Creates graph nodes from new findings
    ├── Creates tentative edges
    └── state.evidence_graph = ...   ◄── NEW field
    │
    ▼
_build_agent_context()              ◄── UNTOUCHED
    │
    └── Next agent context cascading stays identical
```

**What stays untouched:**
- `_update_state_with_result()` — all typed slot writes
- `_build_agent_context()` — cross-agent data sharing
- `_decide_next_agents()` — phase machine routing
- `_update_phase()` — phase progression
- `_enrich_reasoning_chain()` — supervisor LLM synthesis
- `all_findings`, `all_breadcrumbs`, `critic_verdicts` — accumulation
- Every agent's output format and parsing
- `GET /findings` serialization (extended, not replaced)

---

## Current State: What Works

### Agent Pipeline (6 agents + Critic)
| Agent | Pattern | Data Source | Status |
|-------|---------|-------------|--------|
| Log (L1) | Hybrid (deterministic + 1 LLM) | Elasticsearch | Active |
| Metrics (M1) | ReAct (3-turn batched) | Prometheus | Active |
| K8s (K1) | ReAct (3-turn batched) | Kubernetes API | Active |
| Tracing | ReAct (max 6 iter) | Jaeger + ELK fallback | **Commented out** |
| Code (C1) | Two-pass | GitHub API / local FS | Active |
| Change | Two-pass | GitHub + kubectl | Active |
| Critic | Deterministic rules (V4) / LLM delta (V5) | Cross-validates | Active |

### Orchestration
- Supervisor state machine: `INITIAL → LOGS → METRICS+K8S (parallel) → TRACING → CODE → DIAGNOSIS_COMPLETE`
- Context cascading: each agent receives relevant findings from prior agents
- Critic validation after each agent with 1 re-investigation cycle
- Impact analysis with blast radius + P1-P4 severity
- Past incident memory with Jaccard fingerprint matching
- Budget system with wrap-up nudges and forced final answers

### Fix Generation
- Multi-file fixes within a single repo — fully working
- Campaign orchestrator for multi-repo coordinated PRs — built
- Cross-repo code reading via `repo_map` in Code Agent
- Auto repo discovery from org pattern + GitHub validation
- SurgicalTelescope side-by-side diff viewer with file tabs

### Frontend War Room
- 20+ evidence section types in priority-ordered scroll stack
- Causal Forest visualization with root cause / cascading / correlated
- Real-time WebSocket streaming for agent events + chat tokens
- Action chips for human-in-the-loop gates
- Investigation Router with slash commands and quick actions

### Error Handling
- Infrastructure failure tracking (2 consecutive → early exit with partial results)
- API retries with backoff for 429/529/500+
- Graceful no-data fallbacks (query broadening in log agent)
- Session cleanup with 24h TTL
- WebSocket reconnection with event replay

---

## Gap Analysis: 10 Areas

| # | Gap | Severity | Description |
|---|-----|----------|-------------|
| 1 | Evidence graph is flat | Critical | `EvidenceGraphBuilder` exists but no edges are ever created. All nodes are "symptom". `identify_root_causes()` returns everything. |
| 2 | Critic is single-pass | Critical | V4 uses static rules only. No ensemble, no temporal reasoning, confidence uncalibrated. `causal_role` returned but never wired to graph edges. |
| 3 | Chat has no tool calling | High | `handle_user_message()` uses `chat_stream()` — cannot query live data. Findings context is a static snapshot. |
| 4 | Tracing agent disabled | High | Commented out in supervisor. `TraceWaterfall` exists in frontend but gets almost no data. |
| 5 | No infra-repo awareness | High | Code Agent / Fix Generator have zero understanding of Helm, Terraform, K8s manifests, Dockerfiles. |
| 6 | Chat prompt underspecified | Medium | Missing grounding rules, citation rules, communication style, workflow awareness. |
| 7 | No live data refresh | Medium | Once agents complete, findings are frozen. No mechanism to re-query during investigation. |
| 8 | Missing observability correlations | Medium | No metric→log, log→trace, or trace→code click-through linking. |
| 9 | Token overflow risk | Medium | No pre-check that combined context fits within LLM context window. |
| 10 | Multi-repo fix isolation | Medium | Each repo's fix generated independently. Fix for repo B doesn't see repo A's fix. No cross-repo PR linking. |

---

## Phase 1: Foundation — Evidence Graph + Critic Ensemble

### 1A. Graph-Based Incident Model

**Storage: NetworkX + SQLite** (same pattern as `network/knowledge_graph.py`).
- In-memory `networkx.DiGraph` for algorithms
- SQLite persistence per session for durability
- No new infrastructure dependency
- Proven in our codebase (network KG has confidence-weighted edges, path algorithms, persistence)

**New file:** `backend/src/agents/incident_graph.py`

**Node types (7):**

| Type | Source Agent | Attributes |
|------|-------------|------------|
| `error_event` | Log Agent | exception_type, message, service, stack_trace, trace_id |
| `metric_anomaly` | Metrics Agent | metric_name, current_value, baseline, deviation_pct, promql |
| `k8s_event` | K8s Agent | event_type (OOMKilled/CrashLoop/Warning), pod, restart_count |
| `trace_span` | Tracing Agent | service, operation, duration_ms, status, parent_span_id |
| `code_change` | Change Agent | commit_sha, author, files_changed, timestamp |
| `config_change` | Change Agent | resource_type (ConfigMap/Secret/HPA), key, old_value, new_value |
| `code_location` | Code Agent | file_path, line_number, function_name, root_cause_description |

**Common node fields:** `id` (UUID), `timestamp`, `confidence` (0.0-1.0), `severity` (critical/high/medium/low), `agent_source`, `evidence_snippets[]`, `metadata{}`.

**Edge types (6):**

| Edge | Meaning | Constraint |
|------|---------|-----------|
| `causes` | Direct causation | source.timestamp < target.timestamp |
| `triggers` | Temporal trigger | source.timestamp < target.timestamp |
| `manifests_as` | Symptom expression | source is cause-type, target is symptom-type |
| `correlates_with` | Statistical correlation | Bidirectional, no temporal constraint |
| `precedes` | Temporal ordering only | source.timestamp < target.timestamp |
| `located_in` | Code location mapping | source is event, target is code_location |

**Common edge fields:** `confidence` (0.0-1.0), `reasoning` (text), `temporal_delta_ms` (int), `created_by` (agent name or "critic").

**Graph algorithms:**

1. **Root cause ranking** — Weighted PageRank on reversed graph. Nodes with highest authority score = most-likely root cause. Replaces trivial in-degree-zero heuristic.
2. **Causal path extraction** — Dijkstra shortest path (weight = 1 - edge.confidence) from each root cause to each symptom. Produces ordered causal chains for the reasoning panel.
3. **Temporal consistency** — Post-edge-creation sweep: reject edges where source.timestamp > target.timestamp (effect before cause). Log as invariant violation.
4. **Cycle detection** — `networkx.find_cycle()`. Break cycles by removing lowest-confidence edge. Log broken cycles.
5. **Blast radius (graph-based)** — BFS from root cause node. Count reachable nodes grouped by type. Replaces the current list-based blast radius that depends on caller-supplied lists.
6. **Subgraph extraction** — Given a node, extract its 2-hop neighborhood for focused UI rendering.

**Integration into supervisor (additive):**

```python
# supervisor.py — AFTER existing _update_state_with_result():

async def _ingest_into_graph(self, state: DiagnosticState, agent_name: str, result: dict):
    """Additive layer: reads from state, writes to state.evidence_graph."""
    if not hasattr(state, 'incident_graph_builder'):
        state.incident_graph_builder = IncidentGraphBuilder(state.session_id)

    builder = state.incident_graph_builder

    # Create nodes from the agent's newly added findings
    new_findings = state.all_findings[-len(result.get("findings", [])):]
    for finding in new_findings:
        node_id = builder.add_node(
            node_type=self._finding_to_node_type(agent_name, finding),
            data=finding,
            timestamp=finding.get("timestamp"),
            confidence=finding.get("confidence", 0.5),
            severity=finding.get("severity", "medium"),
            agent_source=agent_name,
        )

    # Create tentative edges based on heuristics:
    # - Same trace_id → correlates_with
    # - Same service + temporal proximity (< 5min) → precedes
    # - Error pattern mentions another service → causes (tentative)
    builder.create_tentative_edges()

    # Run consistency checks
    builder.enforce_temporal_consistency()
    builder.break_cycles()

    # Update root cause ranking
    builder.rank_root_causes()

    # Store on state (new field)
    state.evidence_graph = builder.to_serializable()
```

**DiagnosticState extension (1 new field):**

```python
# schemas.py — add to DiagnosticState:
evidence_graph: Optional[dict] = None  # Serialized IncidentGraph {nodes, edges, root_causes, causal_paths}
```

**API extension:**

```python
# GET /findings — add to response alongside existing fields:
"evidence_graph": state.evidence_graph,  # New field, None until Phase 1 ships
```

### 1B. Critic → Ensemble Debate + Calibrated Confidence

**New file:** `backend/src/agents/critic_ensemble.py`

**Two-stage pipeline:**

**Stage 1: Deterministic Pre-checks (0 LLM calls)**

```python
class DeterministicValidator:
    """Port invariant pattern from cluster/causal_invariants.py to per-incident scope."""

    def validate(self, pin: EvidencePin, graph: IncidentGraph, existing_pins: list) -> PreCheckResult:
        violations = []

        # Temporal: cause must precede effect
        if pin.timestamp and self._has_future_cause(pin, graph):
            violations.append("temporal_violation")

        # Domain invariants (ported from cluster causal_invariants.py):
        # - Pod cannot cause etcd failure
        # - Application error cannot cause node failure
        # - Network partition cannot cause code bug
        for inv in INCIDENT_INVARIANTS:
            if inv.matches(pin, graph):
                violations.append(inv.name)

        # Contradiction: new pin contradicts validated pin on same resource
        for existing in existing_pins:
            if existing.validation_status == "validated" and self._contradicts(pin, existing):
                violations.append(f"contradicts:{existing.pin_id}")

        # Schema: required fields present, confidence in range
        if not pin.claim or not pin.source_agent:
            violations.append("schema_incomplete")

        if violations:
            return PreCheckResult(status="hard_reject", violations=violations)
        return PreCheckResult(status="pass")
```

**Stage 2: LLM Ensemble Debate (3 calls, Sonnet-tier)**

```python
class EnsembleCritic:
    """Three-role debate: Advocate, Challenger, Judge."""

    async def validate(self, finding: Finding, state: DiagnosticState, graph: IncidentGraph) -> EnrichedVerdict:
        # Pre-check
        pre = self.deterministic.validate(finding, graph, state.all_findings)
        if pre.status == "hard_reject":
            return EnrichedVerdict(verdict="challenged", confidence=0.95, reasoning=pre.violations, graph_edges=[])

        evidence_context = self._build_evidence_context(finding, state, graph)

        # Advocate: argues FOR the finding
        advocate_result = await self.llm.chat(
            system="You are an advocate. Argue why this finding is valid...",
            messages=[{"role": "user", "content": evidence_context}],
            model="claude-sonnet-4-20250514",
            temperature=0.0,
        )

        # Challenger: argues AGAINST the finding
        challenger_result = await self.llm.chat(
            system="You are a challenger. Find contradictions, alternative explanations...",
            messages=[{"role": "user", "content": evidence_context}],
            model="claude-sonnet-4-20250514",
            temperature=0.3,  # Higher temp for creative counter-arguments
        )

        # Judge: reads both, produces structured verdict
        judge_result = await self.llm.chat(
            system=JUDGE_SYSTEM_PROMPT,  # Includes graph edge output schema
            messages=[{
                "role": "user",
                "content": f"ADVOCATE:\n{advocate_result}\n\nCHALLENGER:\n{challenger_result}\n\nRAW EVIDENCE:\n{evidence_context}"
            }],
            model="claude-sonnet-4-20250514",
            temperature=0.0,
        )

        verdict = self._parse_judge_output(judge_result)
        # verdict.graph_edges: [{source_pin_id, target_pin_id, edge_type, confidence}]
        # These edges are written into the IncidentGraph by the supervisor
        return verdict
```

**Judge output schema:**

```json
{
  "verdict": "validated | challenged | insufficient_data",
  "confidence": 0.82,
  "causal_role": "root_cause | cascading_symptom | correlated | informational",
  "reasoning": "The OOMKilled event at 14:03 is validated because...",
  "supporting_evidence": ["metric_anomaly_node_id", "k8s_event_node_id"],
  "contradictions": [],
  "graph_edges": [
    {
      "source_node_id": "n-abc123",
      "target_node_id": "n-def456",
      "edge_type": "causes",
      "confidence": 0.85,
      "reasoning": "Memory spike preceded OOMKill by 47 seconds"
    }
  ]
}
```

**Graph edge wiring (in supervisor, after critic returns):**

```python
# supervisor.py — AFTER critic validation:
for edge in verdict.graph_edges:
    state.incident_graph_builder.add_confirmed_edge(
        source_id=edge["source_node_id"],
        target_id=edge["target_node_id"],
        edge_type=edge["edge_type"],
        confidence=edge["confidence"],
        reasoning=edge["reasoning"],
        created_by="critic_ensemble",
    )
state.incident_graph_builder.rank_root_causes()  # Re-rank after new edges
```

**Confidence calibration:**

```python
class ConfidenceCalibrator:
    """Platt scaling: maps raw LLM confidence → calibrated probability."""

    def __init__(self, memory_store: MemoryStore):
        self.history = []  # (raw_confidence, was_correct) pairs
        self.A = 0.0  # Platt parameter
        self.B = 1.0  # Platt parameter

    def calibrate(self, raw_confidence: float) -> float:
        """Apply logistic calibration: P(correct) = 1 / (1 + exp(A * raw + B))"""
        if len(self.history) < 50:
            return raw_confidence  # Not enough data, pass through
        return 1.0 / (1.0 + math.exp(self.A * raw_confidence + self.B))

    def record_outcome(self, raw_confidence: float, was_correct: bool):
        """Called after incident resolution to track accuracy."""
        self.history.append((raw_confidence, was_correct))
        if len(self.history) >= 50:
            self._fit_platt()  # Re-fit logistic curve

    def _fit_platt(self):
        """Fit A, B parameters using scipy.optimize or manual gradient descent."""
        # Standard Platt scaling implementation
        pass
```

**Budget:** 3 Sonnet calls per finding. For P1/P2 incidents, escalate Judge to Opus. Configurable via env var `CRITIC_ENSEMBLE_MODEL`.

**Fallback:** If ensemble times out (30s per role, 90s total), fall back to single-pass critic with `validation_status="pending_critic"` and retry in background.

---

## Phase 2: Intelligence — Chat Tools + Tracing + Prompt Framework

### 2A. Chat LLM Tool Calling

**Modified file:** `backend/src/agents/supervisor.py` — `handle_user_message()` method.

Replace `chat_stream()` with `chat_with_tools()`. The chat LLM gets 6 tools:

| Tool | Purpose | Backend Function | Data Source |
|------|---------|-----------------|-------------|
| `query_prometheus` | Live metric queries | Reuse `MetricsAgent._execute_tool("query_prometheus_range")` | Prometheus API |
| `query_logs` | Search ES logs | Reuse `LogAgent._search_elasticsearch()` | Elasticsearch |
| `check_pod_status` | Current K8s state | Reuse `K8sAgent._execute_tool("get_pod_status")` | Kubernetes API |
| `query_trace` | Fetch Jaeger spans | Reuse `TracingAgent._execute_tool("query_jaeger")` | Jaeger API |
| `run_promql` | Execute suggested PromQL | Prometheus range query (thin wrapper) | Prometheus API |
| `search_findings` | Search collected evidence | Filter `state.all_findings` by agent/severity/keyword | In-memory |

**Context management (prevents token overflow):**

```python
def _build_chat_system_prompt(self, state: DiagnosticState) -> str:
    """Compact system prompt ≤ 4K tokens. Tools provide detail on-demand."""
    sections = [
        f"Phase: {state.phase.value}",
        f"Service: {state.service_name}",
        f"Confidence: {state.overall_confidence}%",
        f"Agents completed: {', '.join(state.agents_completed)}",
    ]

    # Compact reasoning chain (1-2 sentences per step)
    if state.reasoning_chain:
        sections.append("Reasoning chain:")
        for step in state.reasoning_chain[:8]:
            sections.append(f"  {step.get('step', '')}: {step.get('inference', '')}")

    # Top 3 findings summary (not full data)
    top_findings = sorted(state.all_findings, key=lambda f: f.confidence, reverse=True)[:3]
    if top_findings:
        sections.append("Top findings:")
        for f in top_findings:
            sections.append(f"  [{f.agent}] {f.summary} (confidence: {f.confidence}%)")

    # Graph root causes (if available)
    if state.evidence_graph and state.evidence_graph.get("root_causes"):
        sections.append(f"Graph root causes: {state.evidence_graph['root_causes']}")

    sections.append("Use tools to get detailed data. Do NOT guess values you don't have.")
    return "\n".join(sections)
```

**Tool execution flow:**

```python
async def handle_user_message(self, message: str, state: DiagnosticState, emitter) -> str:
    system_prompt = CHAT_RULES + self._build_chat_system_prompt(state)
    conversation = self._get_chat_history(state)  # Last 10 turns
    conversation.append({"role": "user", "content": message})

    # ReAct loop (max 5 tool calls per message)
    for _ in range(5):
        response = await self.llm.chat_with_tools(
            system=system_prompt,
            messages=conversation,
            tools=CHAT_TOOLS,
            model="claude-sonnet-4-20250514",
        )

        if response.stop_reason == "end_turn":
            # Extract text, stream to frontend
            text = response.content[0].text
            await self._stream_response(text, emitter)
            return text

        if response.stop_reason == "tool_use":
            # Execute tool calls, emit tool_call events for UI timeline
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await self._execute_chat_tool(block.name, block.input, state)
                    await emitter.emit("task_event", {
                        "event_type": "tool_call",
                        "agent": "chat",
                        "tool": block.name,
                        "details": {"input": block.input, "success": result.success},
                    })
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result.output})
            conversation.extend([response, *tool_results])

    # Budget exhausted — return what we have
    return "I've reached the maximum number of tool calls for this question. Please try rephrasing."
```

**Streaming:** Only the final text response is streamed via WebSocket. Tool call execution happens server-side; tool_call events are emitted to the UI timeline for transparency.

### 2B. Re-enable Tracing Agent

**Modified file:** `backend/src/agents/supervisor.py`

```python
# Line 131 — uncomment:
self._agents = {
    "log_agent": LogAnalysisAgent,
    "metrics_agent": MetricsAgent,
    "k8s_agent": K8sAgent,
    "tracing_agent": TracingAgent,  # ← Uncomment
    "code_agent": CodeNavigatorAgent,
    "change_agent": ChangeAgent,
}
```

**Dispatch order update in `_decide_next_agents()`:**
- After `LOGS_ANALYZED`: dispatch `metrics_agent` + `k8s_agent` + `tracing_agent` (if `state.trace_id` exists) — all in parallel
- After `METRICS_ANALYZED`: dispatch `tracing_agent` (if not done and trace_ids found in logs)

**Graph integration:** TracingAgent produces `SpanInfo[]` → graph builder creates `trace_span` nodes + `precedes` edges between parent-child spans + `correlates_with` edges to error_event nodes sharing the same trace_id.

**Frontend:** `TraceWaterfall` component already exists and consumes `findings.trace_spans`. No frontend changes needed for basic span display. Add later:
- Critical path highlighting (longest path through span tree)
- Latency anomaly detection (compare span durations vs. Prometheus baselines)

### 2C. System Prompt Framework

**New directory:** `backend/src/prompts/`

**Files:**
- `rules.py` — shared constants injected into every LLM call
- `agent_prompts.py` — per-agent system prompts (extract from inline strings)
- `chat_prompts.py` — chat-specific rules

**Communication rules (injected into ALL LLM calls):**

```python
GROUNDING_RULES = """
GROUNDING:
- Never speculate about values you don't have. Say "I don't have that data" and suggest how to get it.
- Never hallucinate metric values, pod names, timestamps, or file paths.
- If uncertain, state your confidence level explicitly.

CITATION:
- Always reference specific values: "CPU hit 94% at 14:03:22" not "CPU was high".
- Cite the data source: "[Prometheus] container_cpu_usage peaked at 0.94" or "[ES logs] NullPointerException in PaymentService".
- When referencing findings, include the agent that produced them.

TEMPORAL REASONING:
- Events are ordered by timestamp. Correlation does not imply causation.
- A cause MUST precede its effect. Never claim A caused B if A happened after B.
- Always note the time delta between correlated events.

COMPLETENESS:
- Report what you checked and found nothing (negative findings are evidence).
- Distinguish between "confirmed" (validated by critic) and "suspected" (single-agent, unvalidated).
- Never claim root cause without at least 2 corroborating signals from different data sources.
"""
```

**Chat-specific rules:**

```python
CHAT_RULES = """
ROLE: You are an AI SRE assistant embedded in a live incident investigation.

WORKFLOW:
- If the user asks about a metric/pod/log you don't have in context, use the appropriate tool to fetch it live.
- If a tool call fails, tell the user what failed and suggest alternatives.
- When presenting comparisons, use markdown tables.
- When presenting sequences, use numbered lists.
- Keep responses concise (3-5 sentences for simple questions, structured sections for complex ones).

BOUNDARIES:
- You can READ data via tools. You cannot MODIFY infrastructure.
- For remediation actions (fix, rollback, restart), explain what would happen and ask for explicit approval.
- Stay within the scope of the current investigation session.
"""
```

**Per-agent prompt extraction:** Move the inline system prompt strings from each agent file into `agent_prompts.py` as named constants. Each agent's `__init__` references the constant. This enables:
- Centralized prompt versioning
- Shared rules injection via `GROUNDING_RULES + AGENT_SPECIFIC_PROMPT`
- Easier A/B testing of prompt variants

---

## Phase 3: Multi-Repo + Infra — Fix Generation Upgrade

### 3A. Infra-Repo Awareness

**New enum in schemas.py:**

```python
class RepoType(str, Enum):
    APPLICATION = "application"
    INFRASTRUCTURE = "infrastructure"
    MONOREPO = "monorepo"
```

**Infra repo detection (in Code Agent):**

```python
def _detect_repo_type(self, file_tree: list[str]) -> RepoType:
    infra_markers = {
        "Chart.yaml": "helm",
        "kustomization.yaml": "kustomize",
        "*.tf": "terraform",
        "Dockerfile": "docker",
        "docker-compose.yml": "compose",
    }
    k8s_manifest_count = sum(1 for f in file_tree if f.endswith(('.yaml', '.yml'))
                             and any(d in f for d in ['deploy', 'k8s', 'manifests', 'charts']))

    if any(marker in file_tree for marker in infra_markers) or k8s_manifest_count > 3:
        return RepoType.INFRASTRUCTURE
    return RepoType.APPLICATION
```

**Infra-specific prompt additions in Fix Generator:**

```python
INFRA_FIX_RULES = {
    "helm": """
        - Modify values.yaml resource limits, NOT template files directly.
        - Use Helm value paths (e.g., resources.limits.memory).
        - Preserve existing value structure and comments.
    """,
    "kustomize": """
        - Use patches or overlays, not base modifications.
        - Preserve kustomization.yaml structure.
    """,
    "terraform": """
        - Update resource configuration preserving state compatibility.
        - Never change resource names (causes destroy+recreate).
        - Update variable defaults in variables.tf, not hardcoded values.
    """,
    "k8s_manifest": """
        - Update Deployment/StatefulSet resource requests and limits.
        - Ensure requests <= limits.
        - Preserve label selectors (immutable on existing deployments).
    """,
}
```

**User prompt for missing infra repo:**

When K8s Agent finds OOMKilled or resource-related issues AND no infra repo is in `repo_map`:

```python
# In supervisor, after K8s analysis:
if self._is_resource_issue(state.k8s_analysis) and not self._has_infra_repo(state.repo_map):
    await emitter.emit("task_event", {
        "event_type": "waiting_for_input",
        "agent": "supervisor",
        "details": {
            "question": "The issue appears to be a resource misconfiguration (e.g., memory limits). "
                       "Do you have an infrastructure repo (Helm charts, Terraform, K8s manifests) for this service?",
            "type": "infra_repo_request",
        },
    })
```

### 3B. Multi-Repo Campaign Improvements

**Dependent fix generation:**

When CampaignOrchestrator generates fix for repo B, inject repo A's completed fix as context:

```python
# campaign_orchestrator.py — in run_campaign():
prior_fixes = {}
for repo_fix in sorted_by_causal_order:
    context = {
        "prior_fixes": prior_fixes,  # {repo_url: {diff, explanation}}
        "causal_role": repo_fix.causal_role,
    }

    fix = await self._generate_fix_for_repo(repo_fix, context)

    # Store for next repo's context
    prior_fixes[repo_fix.repo_url] = {
        "diff": fix.diff,
        "explanation": fix.fix_explanation,
    }
```

**Fix Generator prompt addition:**

```
## PRIOR FIXES IN THIS CAMPAIGN
The following fixes have already been generated for upstream services:
{prior_fix_diffs}
Ensure your fix is compatible. Do not duplicate changes already made upstream.
```

**Cross-repo PR linking:**

Each PR body includes:

```markdown
## Coordinated Fix Campaign #{campaign_id}
| Repo | Role | PR | Status |
|------|------|----|--------|
| org/service-a | Root Cause | #123 | ✅ Merged |
| org/service-b (this) | Cascading | #124 | 🔄 Review |
| org/service-c | Config Update | #125 | ⏳ Pending |
```

**Monorepo detection:**

```python
def _group_by_repo(self, repo_fixes: list[CampaignRepoFix]) -> dict[str, list]:
    """Group services sharing the same repo URL to avoid duplicate clones."""
    groups = defaultdict(list)
    for fix in repo_fixes:
        normalized = fix.repo_url.rstrip("/").lower()
        groups[normalized].append(fix)
    return groups
    # Services in same repo get a single clone + single PR with combined changes
```

### 3C. Multi-File Change Visibility (Frontend)

**Enhanced SurgicalTelescope:**

Current: single scrollable diff block split by `--- filepath ---` headers.

New:
- **File tree sidebar** (left, 200px): list of changed files with `+N / -M` line counts, colored by change type (added=green, modified=yellow, deleted=red)
- **Per-file tab navigation**: click a file to scroll/jump to its diff section
- **Change summary header**: "3 files changed, 47 insertions(+), 12 deletions(-)"
- **Syntax highlighting**: detect language from file extension, apply appropriate highlight theme

No new components needed — extend existing `SurgicalTelescope.tsx` and `DiffViewer` within `FixPipelinePanel.tsx`.

---

## Phase 4: Polish — Live Refresh + Correlations + Token Safety

### 4A. Live Data Refresh

Add `refresh_data` as a chat tool (included in 2A's tool list, but the implementation is here):

```python
async def _execute_refresh(self, data_type: str, state: DiagnosticState) -> dict:
    """Re-run data collection (no LLM) for a specific source."""
    if data_type == "metrics":
        # Re-query Prometheus with current timestamp
        results = await self._query_prometheus_current(state)
        # Diff against state.metrics_analysis
        changes = self._diff_metrics(state.metrics_analysis, results)
        return {"status": "refreshed", "changes": changes}

    elif data_type == "k8s":
        results = await self._query_k8s_current(state)
        changes = self._diff_k8s(state.k8s_analysis, results)
        return {"status": "refreshed", "changes": changes}

    elif data_type == "logs":
        results = await self._query_es_current(state)
        return {"status": "refreshed", "new_entries": len(results)}
```

This is NOT a full agent re-run. It's a lightweight data collection pass that returns the delta. The chat LLM then narrates what changed.

### 4B. Observability Correlations (Frontend)

Three click-through links, all implemented as frontend navigation actions:

| Interaction | From | To | Implementation |
|------------|------|----|----------------|
| Metric → Logs | Click anomaly timestamp in EvidenceFindings | Filter logs to ±2min window | Chat slash command `/logs time:{t-2m} to:{t+2m}` |
| Log → Trace | Click `trace_id` in log entry | Open TraceWaterfall filtered | Scroll to trace section + highlight matching trace_id |
| Trace → Code | Click span operation name | Open code file in SurgicalTelescope | Only if Code Agent mapped the operation to a file |

**Implementation approach:** Each correlation is a `ChatDrawer` quick action or an inline link that triggers navigation within the Investigation view. No backend changes needed — the data is already present, just not cross-linked.

### 4C. Token Overflow Protection

**New utility:** `backend/src/utils/token_budget.py`

```python
import anthropic

def estimate_tokens(text: str) -> int:
    """Approximate token count (4 chars ≈ 1 token for English text)."""
    return len(text) // 4

def enforce_budget(system_prompt: str, conversation: list, context: str,
                   model_max: int = 200_000, target_ratio: float = 0.7) -> tuple[str, list, str]:
    """Truncate context to fit within model context window."""
    target = int(model_max * target_ratio)
    total = estimate_tokens(system_prompt) + estimate_tokens(str(conversation)) + estimate_tokens(context)

    if total <= target:
        return system_prompt, conversation, context

    # Truncation priority (lowest priority removed first):
    # 1. Old conversation turns (keep last 5)
    # 2. Low-confidence findings (< 40%)
    # 3. Negative findings
    # 4. Detailed evidence snippets (keep summaries only)
    # 5. Summary findings (last resort)

    # Apply truncations in order until under budget
    truncated_conv = conversation[-10:]  # Keep last 10
    if estimate_tokens(str(truncated_conv)) + estimate_tokens(system_prompt) + estimate_tokens(context) <= target:
        return system_prompt, truncated_conv, context

    # Truncate context (findings serialization)
    truncated_context = _truncate_findings(context, target - estimate_tokens(system_prompt) - estimate_tokens(str(truncated_conv)))
    return system_prompt, truncated_conv, truncated_context
```

Injected into:
- `handle_user_message()` before every chat LLM call
- `_enrich_reasoning_chain()` before supervisor synthesis call
- `CriticEnsemble.validate()` before each debate call

---

## Files Changed Summary

### New Files
| File | Description |
|------|-------------|
| `backend/src/agents/incident_graph.py` | IncidentGraphBuilder — NetworkX graph + SQLite persistence |
| `backend/src/agents/critic_ensemble.py` | EnsembleCritic — Advocate/Challenger/Judge + calibration |
| `backend/src/prompts/rules.py` | Shared grounding/citation/temporal rules |
| `backend/src/prompts/agent_prompts.py` | Extracted per-agent system prompts |
| `backend/src/prompts/chat_prompts.py` | Chat-specific rules and tool descriptions |
| `backend/src/utils/token_budget.py` | Token estimation and context truncation |

### Modified Files
| File | Change |
|------|--------|
| `backend/src/models/schemas.py` | Add `evidence_graph` field to DiagnosticState, `RepoType` enum |
| `backend/src/agents/supervisor.py` | Add `_ingest_into_graph()` (additive), upgrade `handle_user_message()` to tool calling, uncomment tracing_agent, add infra repo prompt |
| `backend/src/agents/code_agent.py` | Add `_detect_repo_type()`, infra-repo-aware prompting |
| `backend/src/agents/fix_generator.py` | Add infra-specific fix rules, prior-fix context injection |
| `backend/src/agents/campaign_orchestrator.py` | Dependent fix generation, cross-repo PR linking, monorepo grouping |
| `backend/src/api/routes_v4.py` | Add `evidence_graph` to findings response |
| `frontend/src/components/Investigation/SurgicalTelescope.tsx` | File tree sidebar, per-file navigation |
| `frontend/src/components/Investigation/EvidenceFindings.tsx` | Cross-correlation click-through links |

### Untouched Files (explicit guarantee)
| File | Guarantee |
|------|-----------|
| `_update_state_with_result()` in supervisor.py | Zero changes to agent result parsing |
| `_build_agent_context()` in supervisor.py | Zero changes to cross-agent data sharing |
| `_decide_next_agents()` in supervisor.py | Zero changes to phase routing (except adding tracing_agent back) |
| `_update_phase()` in supervisor.py | Zero changes to phase progression |
| All agent output formats | Zero changes to what agents return |
| `GET /findings` existing fields | All existing response fields preserved |

---

## Delivery Phases

| Phase | Scope | Dependencies |
|-------|-------|-------------|
| **1: Foundation** | Evidence Graph + Critic Ensemble | None |
| **2: Intelligence** | Chat Tool Calling + Tracing Agent + Prompt Framework | Phase 1 (graph feeds chat context) |
| **3: Multi-Repo** | Infra repos + Campaign improvements + Multi-file visibility | Phase 2 (chat asks for infra repos) |
| **4: Polish** | Live refresh + Correlations + Token overflow | Phases 1-3 |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Ensemble Critic triples LLM cost per finding | Use Sonnet (not Opus) for Advocate/Challenger. Skip ensemble for low-severity findings (P3/P4). Configurable via env var. |
| Graph adds latency to agent pipeline | Graph operations are O(N) where N ≈ 10-50 nodes per incident. NetworkX handles this in <1ms. |
| Chat tool calls slow down responses | Max 5 tool calls per message. Tool timeout at 10s each. Stream final text response only. |
| Token overflow in ensemble debate | Apply `enforce_budget()` before each debate call. Truncate evidence context if needed. |
| Tracing agent fails on missing Jaeger | Prerequisite check already exists. Falls back to ELK trace reconstruction. |
| Infra fix generates wrong Helm syntax | Add Helm/Terraform linters as post-fix validators alongside existing `StaticValidator`. |

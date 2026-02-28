# Live Investigation Steering: InvestigationRouter Design

**Date:** 2026-02-28
**Status:** Approved
**Scope:** Backend router + tool execution layer + frontend quick-action UI + progressive tool expansion

---

## 1. Problem Statement

Today the diagnostic pipeline is fire-and-forget: the user starts a session, agents run sequentially, and findings appear when done. The user cannot:

- Pull live logs from a specific pod mid-investigation
- Run a PromQL query to validate a hypothesis
- Ask "check DNS in this namespace" and get an answer
- Steer the investigation toward areas the automated agents didn't cover

This makes the tool passive. SREs fall back to terminal windows alongside the UI, defeating the purpose. We need to make the tool an active investigation partner that responds to user direction in real-time while the automated pipeline continues running.

---

## 2. Design Decisions (Agreed)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | **Approach A: Tool Router** with Command Palette speed injection | Tools and agents are separate concerns. Users requesting raw data shouldn't wait for LLM reasoning |
| Interaction model | **Parallel: auto + manual** | Automated pipeline runs as today. User issues commands anytime. Findings merge into same evidence pool |
| Scope | **Progressive: Phase 1 → 2 → 3** | Ship core SRE tools fast, expand iteratively |
| Input mode | **Structured commands + natural language** | Quick-action buttons for reliability, chat for flexibility |
| Evidence integration | **Merge + re-trigger critic** | Manual findings merge into unified pool. Critic delta-validates new evidence against existing findings |

---

## 3. InvestigationRouter Architecture

### 3.1 Two-Path Design

The router has a **Fast Path** (deterministic, ~50ms) and a **Smart Path** (LLM-powered, ~400ms). Both converge on the same ToolDispatcher.

```
┌─────────────────────────────────────────────────────────────┐
│                    InvestigationRouter                       │
│                                                             │
│  ┌──────────────┐     ┌───────────────┐                    │
│  │  Fast Path   │     │  Smart Path   │                    │
│  │ /command or  │     │ Natural lang  │                    │
│  │ button click │     │ → Haiku LLM   │                    │
│  │ → regex/map  │     │ → JSON schema │                    │
│  └──────┬───────┘     └──────┬────────┘                    │
│         │                    │                              │
│         └────────┬───────────┘                              │
│                  ▼                                          │
│         ┌────────────────┐                                  │
│         │ ToolDispatcher │  Unified {intent, params} → tool │
│         └───────┬────────┘                                  │
│                 ▼                                           │
│         ┌────────────────┐                                  │
│         │ EvidencePin    │  Standardized output             │
│         │ Factory        │                                  │
│         └───────┬────────┘                                  │
│                 ▼                                           │
│         ┌────────────────┐                                  │
│         │ State Merger   │  Append to LangGraph state       │
│         │ + Critic Gate  │  IF manual → route to Critic     │
│         └────────────────┘                                  │
└─────────────────────────────────────────────────────────────┘
```

**Fast Path:** Anything starting with `/` or arriving as a `QuickActionPayload` skips the LLM. The router parses the slash command via regex, maps button payloads directly to `{intent, params}`, and dispatches immediately.

**Smart Path:** Natural language queries go to a Haiku LLM call with `tool_use` and strict JSON schema output. The LLM receives the full `RouterContext` (active namespace, service, pod, discovered entities) so it can infer missing parameters without asking the user.

### 3.2 Smart Path Context Injection

The Haiku call receives a context envelope so it can resolve implicit references:

```python
class RouterContext(BaseModel):
    # From UI viewport state
    active_namespace: str | None = None
    active_service: str | None = None
    active_pod: str | None = None
    time_window: TimeWindow

    # From session state
    session_id: str
    incident_id: str
    discovered_services: list[str] = []
    discovered_namespaces: list[str] = []
    pod_names: list[str] = []

    # From evidence pool
    active_findings_summary: str = ""
    last_agent_phase: str = ""
```

System prompt pattern:

```
You are an investigation router. The SRE is investigating incident {incident_id}.

Current context:
- Active namespace: {active_namespace}
- Active service: {active_service}
- Time window: {time_window}
- Known pods: {pod_names}

Parse the user's request into a tool call. Use the active context
to fill any missing parameters. Output strict JSON:
{intent: string, params: dict}

Available tools: {tool_registry_descriptions}
```

Example: User types "get me the auth pod logs" → Haiku sees `active_namespace: "payment-api"` → outputs `{"intent": "fetch_pod_logs", "params": {"pod": "auth-*", "namespace": "payment-api"}}`.

---

## 4. EvidencePin Schema

Every tool execution — automated or manual — produces the same output structure:

```python
class EvidencePin(BaseModel):
    # Identity
    id: str                              # UUID
    claim: str                           # "Pod auth-5b6q has 12 restarts in last hour"

    # Source tracking
    source: Literal["auto", "manual"]
    source_agent: str | None             # "log_agent" or None for manual
    source_tool: str                     # "kubectl_logs", "prometheus_range_query", etc.
    triggered_by: Literal["automated_pipeline", "user_chat", "quick_action"]

    # Evidence
    evidence_type: Literal["log", "metric", "trace", "k8s_event", "k8s_resource", "code", "change"]
    supporting_evidence: list[str]       # Key extracted snippets
    raw_output: str | None               # Full tool output for "View Raw" UI

    # Classification
    confidence: float                    # 0-100
    severity: Literal["critical", "high", "medium", "low", "info"] | None
    causal_role: Literal["root_cause", "cascading_symptom", "correlated", "informational"] | None

    # Routing
    domain: Literal["compute", "network", "storage", "control_plane", "security", "unknown"]
    validation_status: Literal["pending_critic", "validated", "rejected"] = "pending_critic"

    # Context
    namespace: str | None
    service: str | None
    resource_name: str | None
    timestamp: datetime
    time_window: TimeWindow | None
```

Key design decisions:
- `source: "manual"` triggers the conditional edge to Critic
- `validation_status: "pending_critic"` is the initial state — UI renders amber pulse + spinner
- `domain` is set by the backend (not guessed by the frontend) for clean grid routing
- `causal_role` starts as `None` — Critic assigns it during delta revalidation
- `confidence: 100.0` for raw tool output (factual); Critic may adjust downward

---

## 5. LangGraph Integration

### 5.1 Graph Topology

```
                    ┌─────────────────────────────────────────┐
                    │         Automated Pipeline              │
                    │  log → metrics → k8s → tracing →        │
                    │  code → change → synthesizer            │
                    └──────────────┬──────────────────────────┘
                                   │
                                   ▼
START ──────────────────►  SharedState (evidence_pins[])
                                   ▲
                                   │
                    ┌──────────────┴──────────────────────────┐
                    │         Manual Pipeline                  │
                    │  chat/button → InvestigationRouter       │
                    │       → ToolDispatcher → EvidencePin     │
                    │       → ConditionalEdge                 │
                    │            ↓                            │
                    │       CriticAgent (delta revalidation)  │
                    └─────────────────────────────────────────┘
```

### 5.2 Conditional Edge

```python
def route_after_pin_merge(state: DiagnosticState) -> str:
    latest_pin = state["evidence_pins"][-1]
    if latest_pin.source == "manual":
        return "critic_revalidation"
    else:
        return "continue_pipeline"
```

### 5.3 Critic Delta Revalidation

The critic runs a delta validation (not full re-analysis) on each manual pin:

```python
async def critic_revalidation(state: DiagnosticState) -> DiagnosticState:
    new_pin = state["evidence_pins"][-1]
    existing_pins = state["evidence_pins"][:-1]

    verdict = await critic_agent.validate_delta(
        new_evidence=new_pin,
        existing_evidence=existing_pins,
        current_causal_chains=state["causal_chains"]
    )

    new_pin.validation_status = verdict.status         # "validated" or "rejected"
    new_pin.causal_role = verdict.assigned_role         # "root_cause", "correlated", etc.
    new_pin.confidence = verdict.adjusted_confidence

    # If new pin contradicts existing findings, update those too
    for contradiction in verdict.contradictions:
        existing_pin = find_pin(state, contradiction.pin_id)
        existing_pin.validation_status = "rejected"
        existing_pin.causal_role = "informational"

    emit("evidence_pin_updated", {
        "pin_id": new_pin.id,
        "validation_status": new_pin.validation_status,
        "causal_role": new_pin.causal_role,
    })

    return state
```

### 5.4 Concurrency Safety

Per-session asyncio lock (existing C1 pattern) extended to cover pin appends:

```python
async with session_locks[session_id]:
    state["evidence_pins"].append(new_pin)
```

### 5.5 WebSocket Events

| Event | When | UI Behavior |
|-------|------|-------------|
| `evidence_pin_added` | Pin created, pre-critic | Amber pulse + spinner |
| `evidence_pin_updated` | Critic finishes | Snap to final state (green/red border, badge assigned) |
| `evidence_pin_rejected` | Critic rejects | Fade to "Informational" section |

---

## 6. API Endpoints

### 6.1 Manual Investigation

```
POST /api/v4/session/{session_id}/investigate
```

**Request (exactly one of command/query/quick_action must be set — enforced by Pydantic `@model_validator`):**

```python
class InvestigateRequest(BaseModel):
    command: str | None = None              # Fast Path: "/logs namespace=payment pod=auth-5b6q"
    query: str | None = None               # Smart Path: "check if auth pod is crashing"
    quick_action: QuickActionPayload | None = None  # Button click

    context: RouterContext                  # Always sent

    @model_validator(mode="after")
    def exactly_one_input(self) -> "InvestigateRequest":
        provided = sum(1 for v in [self.command, self.query, self.quick_action] if v is not None)
        if provided != 1:
            raise ValueError("Exactly one of command, query, or quick_action must be provided")
        return self

class QuickActionPayload(BaseModel):
    intent: str
    params: dict[str, Any]
```

**Response:**

```python
class InvestigateResponse(BaseModel):
    pin_id: str                             # Track pin lifecycle via WebSocket
    intent: str
    params: dict[str, Any]
    path_used: Literal["fast", "smart"]
    status: Literal["executing", "error"]
    error: str | None = None
```

### 6.2 Tool Registry Discovery

```
GET /api/v4/session/{session_id}/tools
```

Returns the list of available tools with their parameter schemas. Session-scoped because available options (pod names, namespaces) are populated from session state.

```python
class ToolDefinition(BaseModel):
    intent: str                             # "fetch_pod_logs"
    label: str                              # "Get Pod Logs"
    icon: str                               # Material Symbol: "terminal"
    description: str
    category: Literal["logs", "metrics", "cluster", "network", "security", "code"]
    params_schema: list[ToolParam]
    slash_command: str                      # "/logs"
    requires_context: list[str]             # ["namespace"] — dims button if missing

class ToolParam(BaseModel):
    name: str
    type: Literal["string", "select", "number", "boolean"]
    required: bool
    default_from_context: str | None        # "active_pod" — auto-fills from RouterContext
    options: list[str] | None = None        # For select type
    placeholder: str | None = None
```

### 6.3 Updated Chat Endpoint

```
POST /api/v4/session/{session_id}/chat
```

Chat gains `context` and `include_recent_pins` so the LLM can reference investigation results:

```python
class ChatRequest(BaseModel):
    message: str
    context: RouterContext
    include_recent_pins: bool = True
```

---

## 7. Tool Execution Layer

### 7.1 Architecture

```python
class ToolExecutor:
    def __init__(self, connection_config: ResolvedConnectionConfig): ...

    async def execute(self, intent: str, params: dict) -> ToolResult:
        handler = self.HANDLERS[intent]
        return await handler(self, params)

class ToolResult(BaseModel):
    success: bool
    intent: str
    raw_output: str
    summary: str
    evidence_snippets: list[str]
    evidence_type: str
    domain: str
    severity: str | None
    error: str | None
    metadata: dict[str, Any]
```

### 7.2 EvidencePinFactory

Converts ToolResult → EvidencePin:

```python
class EvidencePinFactory:
    @staticmethod
    def from_tool_result(
        result: ToolResult,
        triggered_by: Literal["automated_pipeline", "user_chat", "quick_action"],
        context: RouterContext,
    ) -> EvidencePin:
        return EvidencePin(
            id=str(uuid4()),
            claim=result.summary,
            source="manual" if triggered_by in ("user_chat", "quick_action") else "auto",
            source_agent=None,
            source_tool=result.intent,
            triggered_by=triggered_by,
            evidence_type=result.evidence_type,
            supporting_evidence=result.evidence_snippets,
            raw_output=result.raw_output,
            confidence=100.0 if result.success else 0.0,
            severity=result.severity,
            causal_role=None,
            domain=result.domain,
            validation_status="pending_critic",
            namespace=context.active_namespace,
            service=context.active_service,
            resource_name=result.metadata.get("pod") or result.metadata.get("name"),
            timestamp=datetime.utcnow(),
            time_window=context.time_window,
        )
```

### 7.3 Phase 1 Tools

#### fetch_pod_logs
- Wraps K8s `read_namespaced_pod_log` API
- Supports wildcard pod names (`auth-*` → resolves to most recent matching pod)
- `previous=True` fetches crashed container logs
- `timestamps=True` for temporal correlation
- Extracts error/exception/fatal/panic/oom/timeout lines as evidence snippets
- Severity derived from log content (fatal/panic → critical, oom → high, errors → medium, clean → info)
- Domain: `compute`

#### describe_resource
- Generic `kubectl describe` for pod, deployment, service, node, configmap, ingress, PVC
- Maps resource kind → API method (namespaced vs cluster-scoped)
- Extracts conditions, events, key signals from resource status
- Domain mapped per kind: pod/deployment/node → `compute`, service/ingress → `network`, pvc → `storage`

#### query_prometheus
- Direct PromQL range query execution
- Computes basic stats: series count, latest value, peak, average, stddev
- Anomaly detection: flags spikes > 2 stddev above mean
- Returns simplified time series for sparkline rendering in UI
- Domain inferred from PromQL content (coredns/ingress → `network`, apiserver/etcd → `control_plane`, default → `compute`)

#### search_logs
- Elasticsearch `query_string` search with level and time filters
- Extracts top 20 hits with timestamp, service name, message
- Uses existing LogAgent field mapping logic for vendor-agnostic fields
- Domain: `unknown` (logs can be from any domain)

#### check_pod_status
- Lists pods with optional label selector
- Reports phase, restart count, OOM detection, readiness
- Domain: `compute`

#### get_events
- K8s events filtered by namespace, time window, involved object
- Sorts by timestamp descending
- Highlights Warning-type events
- Domain: `compute`

#### re_investigate_service
- Re-dispatches the full automated agent pipeline for a different service/namespace
- Creates a sub-investigation linked to the parent session
- Results merge into the same evidence pool

---

## 8. Frontend Quick-Action UI

### 8.1 Investigation Toolbar

Collapsible toolbar docked at the top of the chat drawer:

```
┌─ Quick Actions ───────────────────────────┐
│ [terminal Pod Logs] [monitoring PromQL]   │
│ [info Describe] [event_note Events]       │
│ [search Search ELK] [health Pods]         │
│ [radar Investigate Service]               │
└───────────────────────────────────────────┘
```

- Buttons dim when required context is missing (tooltip explains why)
- Buttons with no required user input beyond context execute immediately on click
- Buttons needing input show a compact inline form below the toolbar

### 8.2 Inline Parameter Form

```
┌─ Get Pod Logs ────────────────────────────┐
│ Namespace: [payment-api      ] (auto-fill)│
│ Pod:       [auth-5b6q ▾      ] (dropdown) │
│ Previous:  [checkbox]  Tail: [200   ]     │
│                          [Cancel] [Run]   │
└───────────────────────────────────────────┘
```

- `default_from_context` fields auto-fill from RouterContext
- `select` type fields populated from session state (discovered pods, namespaces)
- On Execute: sends `POST /investigate` with `quick_action` payload

### 8.3 Slash Command Autocomplete

Typing `/` in the chat input shows an autocomplete dropdown listing all available slash commands. Selecting one pre-fills the input with the command template. `default_from_context` values inject as ghost text:

```
/logs namespace=payment-api pod=|
```

Ghost text (dimmed, pre-filled) teaches the CLI syntax without requiring memorization. User types over or tabs through parameters.

### 8.4 Context-Aware Suggestion Chips

After automated agents produce findings, deterministic rules generate suggestion chips:

```python
SUGGESTION_RULES = {
    "oom_killed": [
        SuggestionChip("Pull crash logs", "fetch_pod_logs", {"previous": True}),
        SuggestionChip("Check memory limits", "describe_resource", {"kind": "pod"}),
    ],
    "crash_loop": [
        SuggestionChip("Pull crash logs", "fetch_pod_logs", {"previous": True}),
        SuggestionChip("View recent events", "get_events", {"since_minutes": 30}),
    ],
    "high_error_rate": [
        SuggestionChip("Search error logs", "search_logs", {"level": "ERROR"}),
        SuggestionChip("Check pod health", "check_pod_status", {}),
    ],
    "memory_spike": [
        SuggestionChip("Run memory PromQL", "query_prometheus",
                       {"query": "container_memory_working_set_bytes{namespace='...'}"}),
    ],
}
```

Chips render below the last AI message. Each chip is a pre-wired `QuickActionPayload` — clicking it fires immediately via the Fast Path.

### 8.5 Button State Management

| Condition | Behavior |
|-----------|----------|
| No `active_namespace` | "Pod Logs", "Events", "Pods", "Describe" dimmed |
| K8s agent hasn't run | Pod dropdown shows text input fallback |
| No Prometheus configured | "Run PromQL" dimmed |
| No ELK configured | "Search ELK" dimmed |
| Investigation complete | All buttons remain active |

---

## 9. End-to-End Request Flow

```
User clicks [Get Pod Logs] → fills form → hits Execute
  ↓
Frontend: POST /api/v4/session/{sid}/investigate
  body: {
    quick_action: {intent: "fetch_pod_logs", params: {pod: "auth-5b6q", previous: true}},
    context: {active_namespace: "payment-api", ...}
  }
  ↓
Backend: InvestigationRouter
  1. Detects quick_action → Fast Path (no LLM)
  2. Validates params against ToolParam schema
  3. Returns 200: {pin_id: "abc-123", intent: "fetch_pod_logs", path_used: "fast", status: "executing"}
  ↓
Backend (async): ToolExecutor._fetch_pod_logs(params)
  → K8s API → log text → extract error lines → ToolResult
  ↓
Backend: EvidencePinFactory.from_tool_result(result, "quick_action", context)
  → EvidencePin with validation_status="pending_critic"
  ↓
Backend: State merger (with session lock)
  → Append pin to state["evidence_pins"]
  → WebSocket: evidence_pin_added {pin_id, claim, domain, severity, validation_status}
  ↓
Frontend: Renders amber-pulsing card in Evidence column
  ↓
Backend: Conditional edge → source="manual" → critic_revalidation
  → Critic evaluates new pin against existing evidence
  → Updates: validation_status="validated", causal_role="cascading_symptom"
  ↓
Backend: WebSocket: evidence_pin_updated {pin_id, validation_status, causal_role}
  ↓
Frontend: Card snaps to final state — green border, badge assigned
```

---

## 10. Progressive Expansion Roadmap

### Phase 1: Foundation (Ship First)

| Tool | Intent | Slash Command | Domain |
|------|--------|---------------|--------|
| Get Pod Logs | `fetch_pod_logs` | `/logs` | compute |
| Describe Resource | `describe_resource` | `/describe` | varies |
| Run PromQL | `query_prometheus` | `/promql` | varies |
| Search ELK | `search_logs` | `/search` | unknown |
| Pod Health | `check_pod_status` | `/pods` | compute |
| Cluster Events | `get_events` | `/events` | compute |
| Investigate Service | `re_investigate_service` | `/investigate` | N/A |

Infrastructure: Router, ToolExecutor, EvidencePinFactory, Tool Registry API, `/investigate` endpoint, conditional edge, WebSocket events, quick-action toolbar, slash command autocomplete with ghost text, suggestion chips.

### Phase 2: Infrastructure & Network Depth

| Tool | Intent | Slash Command | Domain |
|------|--------|---------------|--------|
| Check DNS | `check_dns` | `/dns` | network |
| Network Policies | `list_network_policies` | `/netpol` | network |
| Inspect Ingress/Route | `describe_ingress` | `/ingress` | network |
| RBAC Check | `check_rbac` | `/rbac` | security |
| SCC Violations | `check_scc` | `/scc` | security |
| Helm Values | `get_helm_values` | `/helm` | compute |
| ConfigMap Diff | `diff_configmap` | `/configdiff` | compute |
| Node Conditions | `check_node_health` | `/nodes` | compute |

New infrastructure: Security domain panel in War Room, Helm client, RBAC simulation (`SelfSubjectAccessReview`), OpenShift SCC queries.

### Phase 3: Middleware, Databases & Advanced

| Tool | Intent | Slash Command | Domain |
|------|--------|---------------|--------|
| DB Slow Queries | `check_db_queries` | `/dbslow` | compute |
| Redis Health | `check_redis` | `/redis` | compute |
| Kafka Consumer Lag | `check_kafka_lag` | `/kafka` | compute |
| RabbitMQ Queues | `check_rabbitmq` | `/rabbitmq` | compute |
| Certificate Expiry | `check_certificates` | `/certs` | security |
| CronJob Status | `check_cronjobs` | `/cronjobs` | compute |
| Resource Quotas | `check_quotas` | `/quotas` | compute |
| OpenShift Builds | `check_builds` | `/builds` | compute |
| Custom Script | `run_diagnostic_script` | `/script` | unknown |

New infrastructure: Database clients (read-only), Redis/Kafka/RabbitMQ clients, sandboxed debug pod execution, attestation gate for custom scripts.

### Phase 4: Intelligence Layer (Future)

- Multi-root-cause engine (N independent causal trees)
- Incident memory/RAG (vector DB of past resolutions)
- Predictive alerts ("OOM in ~2 hours at current rate")
- Runbook generation (step-by-step with rollback)
- Cross-cluster correlation (staging vs production)

### Expansion Model

Adding a new tool at any phase:

```
1. Add entry to TOOL_REGISTRY (intent, label, params_schema, slash_command)
2. Write handler in ToolExecutor (params → ToolResult)
3. Map domain
4. Done — Router auto-discovers, UI auto-renders button, slash command works
```

No changes to the router, EvidencePin schema, critic, or LangGraph edges.

---

## 11. Phase 1 Tool Registry

```python
TOOL_REGISTRY = [
    ToolDefinition(
        intent="fetch_pod_logs",
        label="Get Pod Logs",
        icon="terminal",
        slash_command="/logs",
        category="logs",
        description="Fetch logs from a running or previously crashed pod",
        params_schema=[
            ToolParam(name="namespace", type="string", required=True,
                      default_from_context="active_namespace"),
            ToolParam(name="pod", type="select", required=True,
                      default_from_context="active_pod", options=[]),
            ToolParam(name="container", type="select", required=False, options=[]),
            ToolParam(name="previous", type="boolean", required=False,
                      placeholder="Fetch from previous (crashed) container"),
            ToolParam(name="tail_lines", type="number", required=False,
                      placeholder="200"),
        ],
        requires_context=["namespace"],
    ),
    ToolDefinition(
        intent="query_prometheus",
        label="Run PromQL",
        icon="monitoring",
        slash_command="/promql",
        category="metrics",
        description="Execute a Prometheus query and pin the result",
        params_schema=[
            ToolParam(name="query", type="string", required=True,
                      placeholder="e.g., rate(http_requests_total[5m])"),
            ToolParam(name="range_minutes", type="number", required=False,
                      placeholder="60"),
        ],
        requires_context=[],
    ),
    ToolDefinition(
        intent="describe_resource",
        label="Describe Resource",
        icon="info",
        slash_command="/describe",
        category="cluster",
        description="kubectl describe for any K8s/OpenShift resource",
        params_schema=[
            ToolParam(name="kind", type="select", required=True,
                      options=["pod", "deployment", "service", "node",
                               "configmap", "ingress", "pvc"]),
            ToolParam(name="name", type="string", required=True),
            ToolParam(name="namespace", type="string", required=True,
                      default_from_context="active_namespace"),
        ],
        requires_context=["namespace"],
    ),
    ToolDefinition(
        intent="get_events",
        label="Cluster Events",
        icon="event_note",
        slash_command="/events",
        category="cluster",
        description="Fetch Kubernetes events filtered by namespace and time",
        params_schema=[
            ToolParam(name="namespace", type="string", required=True,
                      default_from_context="active_namespace"),
            ToolParam(name="since_minutes", type="number", required=False,
                      placeholder="60"),
            ToolParam(name="involved_object", type="string", required=False,
                      placeholder="e.g., pod/auth-5b6q"),
        ],
        requires_context=["namespace"],
    ),
    ToolDefinition(
        intent="search_logs",
        label="Search ELK Logs",
        icon="search",
        slash_command="/search",
        category="logs",
        description="Search Elasticsearch for log patterns across services",
        params_schema=[
            ToolParam(name="query", type="string", required=True,
                      placeholder="e.g., TimeoutException"),
            ToolParam(name="index", type="string", required=False,
                      default_from_context="elk_index"),
            ToolParam(name="level", type="select", required=False,
                      options=["ERROR", "WARN", "INFO", "DEBUG"]),
            ToolParam(name="since_minutes", type="number", required=False,
                      placeholder="60"),
        ],
        requires_context=[],
    ),
    ToolDefinition(
        intent="check_pod_status",
        label="Pod Health",
        icon="health_and_safety",
        slash_command="/pods",
        category="cluster",
        description="Check pod status, restart counts, and OOM kills",
        params_schema=[
            ToolParam(name="namespace", type="string", required=True,
                      default_from_context="active_namespace"),
            ToolParam(name="label_selector", type="string", required=False,
                      placeholder="e.g., app=payment-api"),
        ],
        requires_context=["namespace"],
    ),
    ToolDefinition(
        intent="re_investigate_service",
        label="Investigate Service",
        icon="radar",
        slash_command="/investigate",
        category="cluster",
        description="Run the full agent pipeline against a different service",
        params_schema=[
            ToolParam(name="service", type="string", required=True),
            ToolParam(name="namespace", type="string", required=True,
                      default_from_context="active_namespace"),
        ],
        requires_context=["namespace"],
    ),
]
```

---

## 12. Key Invariants

1. **One execution path.** Both Fast Path and Smart Path converge on the same ToolDispatcher. Tool logic is written once.
2. **One output schema.** Every tool produces a `ToolResult`. Every `ToolResult` becomes an `EvidencePin`. Every `EvidencePin` merges into the same state.
3. **One validation flow.** Manual pins route to Critic. Automated pins route to Synthesizer. The conditional edge handles this.
4. **Additive only.** New tools require zero changes to the router, pin schema, critic, or graph edges. Add to registry + write handler = done.
5. **Context flows downward.** The frontend sends `RouterContext` with every request. The backend never asks the user for missing context that the UI already knows.

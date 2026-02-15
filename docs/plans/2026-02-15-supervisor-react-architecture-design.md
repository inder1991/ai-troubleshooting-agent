# AI SRE Troubleshooting Platform v4.0 — Design Document

**Date:** 2026-02-15
**Status:** Approved

## Overview

Rebuild the AI troubleshooting system from a linear pipeline to a **Supervisor + ReAct multi-agent architecture** with cross-validation, real-time interactivity, and evidence-backed diagnostics.

## Goals

- Replace linear orchestrator with an LLM-powered Supervisor (state machine)
- Rebuild all agents using the ReAct (Reason + Act) pattern for self-correction
- Add Prometheus metrics analysis with spike detection and charting
- Add K8s/OpenShift health checks (restarts, CrashLoopBackOff, events)
- Add distributed tracing (Jaeger first, ELK fallback)
- Add a Critic Agent for cross-validation of findings
- Make log analysis robust with error pattern detection and LLM prioritization
- Make code navigation multi-file with full impact analysis
- Build an interactive chat-centered UI with tabbed dashboard
- Use Anthropic Claude exclusively for all LLM requests
- Track and display token usage across the entire session
- Provide breadcrumb-based evidence chains for every finding

---

## Architecture

### Agent Inventory (7 Agents)

| Agent | Pattern | Trigger | Key Output |
|---|---|---|---|
| **Supervisor** | State Machine + LLM | User request | Orchestration decisions, phase transitions |
| **Log Analyzer** | ReAct | Supervisor dispatches first | Error patterns (prioritized), breadcrumbs |
| **Metrics Analyzer** | ReAct | After Log Agent | Anomalies, time-series data, spike highlights |
| **K8s/OpenShift Agent** | ReAct | Supervisor decides based on findings | Pod health, restarts, CrashLoopBackOff, events |
| **Tracing Agent** | ReAct | Supervisor decides based on findings | Call chain (Jaeger first, ELK fallback) |
| **Code Navigator** | ReAct | After root cause identified | Multi-file impact, dependency graph, fix areas |
| **Critic** | Read-only validator | After each agent completes | Validated / Challenged / Insufficient verdicts |

### Supervisor Agent (State Machine)

Replaces the current linear orchestrator. Instead of a fixed pipeline, it reasons about what to do next based on the current diagnostic state.

**State Machine Phases:**

```python
class DiagnosticPhase(str, Enum):
    INITIAL = "initial"
    COLLECTING_CONTEXT = "collecting_context"
    LOGS_ANALYZED = "logs_analyzed"
    METRICS_ANALYZED = "metrics_analyzed"
    K8S_ANALYZED = "k8s_analyzed"
    TRACING_ANALYZED = "tracing_analyzed"
    CODE_ANALYZED = "code_analyzed"
    VALIDATING = "validating"
    RE_INVESTIGATING = "re_investigating"
    DIAGNOSIS_COMPLETE = "diagnosis_complete"
    FIX_IN_PROGRESS = "fix_in_progress"
    COMPLETE = "complete"
```

**Decision Logic:**
- Receives current state + all agent findings so far
- Claude decides: which agent to run next, what to pass it, whether to run agents in parallel
- Respects confidence thresholds — won't proceed to fix generation if overall confidence < 70
- Handles user messages between agent dispatches (status queries, additional context, priority overrides)

### ReAct Pattern (All Specialized Agents)

Every agent uses Reason -> Act -> Observe loops:
1. Agent thinks about what to query
2. Executes the query/tool
3. Observes the result
4. Decides next step (retry with different params, investigate further, or return findings)
5. Self-corrects on empty/unexpected results instead of failing

### Critic Agent (Read-Only Validator)

Cross-validates findings between agents. Has NO write access to tools.

| Agent Says | Critic Checks | Result |
|---|---|---|
| "DB is down" | Metrics show DB CPU at 5%, healthy | Contradiction — force re-investigation |
| "OOM killed pod" | K8s confirms OOMKilled, metrics show memory at 95% | Validated — proceed |
| "Network timeout" | Tracing shows all spans completed in <100ms | Contradiction — likely not network |

If Critic challenges with confidence > 80, Supervisor must re-investigate.

---

## Agent Designs

### Log Analysis Agent (ReAct)

**Error Pattern Detection:**
- Groups errors by: exception type, error message similarity (fuzzy matching), stack trace fingerprint, affected component
- Handles multiple patterns across the dataset

**LLM-Powered Prioritization:**
- Claude ranks patterns by: frequency, severity, blast radius, likely root cause vs symptom
- Returns prioritized list: Pattern 1 (fix first) + Patterns 2-4 (saved for user to choose later)

**Negative Evidence Reporting:**
- Every query that returns zero results is logged as negative evidence
- Example: "Checked database logs for trace_id X — zero errors found. Suggests the issue is NOT in the DB layer."

**Breadcrumbs:**
- Every finding includes: source_index, log_id, raw_log_snippet, timestamp
- Example: "DB timed out (Source: app-logs-2025.12.26, ID: R3znW5, Line: `ConnectionTimeout after 30s`)"

**Output:**

```python
class ErrorPattern(BaseModel):
    pattern_id: str
    exception_type: str
    error_message: str
    frequency: int
    severity: Literal["critical", "high", "medium", "low"]
    affected_components: list[str]
    sample_logs: list[LogEvidence]
    confidence_score: int
    priority_rank: int
    priority_reasoning: str

class LogAnalysisResult(BaseModel):
    primary_pattern: ErrorPattern
    secondary_patterns: list[ErrorPattern]
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int
    tokens_used: TokenUsage
```

### Metrics Agent (ReAct) — Prometheus

**Runs after Log Agent.** Uses incident time window and affected services to query Prometheus.

**Metric Categories:**
- Resource: CPU, memory, disk I/O, network I/O
- Application: Request rate, error rate, latency (RED metrics)
- Connection pools: Active connections, wait time, exhaustion
- Custom: Any PromQL the LLM decides is relevant

**Spike Detection:**
- LLM analyzes time-series data to identify anomalies
- Marks spike start/end timestamps for UI highlighting
- Compares incident window vs baseline (1 hour before)

**Output:**

```python
class MetricAnomaly(BaseModel):
    metric_name: str
    promql_query: str
    baseline_value: float
    peak_value: float
    spike_start: datetime
    spike_end: datetime
    severity: Literal["critical", "high", "medium", "low"]
    correlation_to_incident: str
    confidence_score: int

class MetricsAnalysisResult(BaseModel):
    anomalies: list[MetricAnomaly]
    time_series_data: dict[str, list[DataPoint]]
    chart_highlights: list[TimeRange]
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int
    tokens_used: TokenUsage
```

**Connection:** Configurable endpoint via `PROMETHEUS_URL` env var. Standard `/api/v1/query_range` HTTP API. Optional auth via env vars.

### K8s/OpenShift Agent (ReAct)

**Takes cluster details from user via chat.** Supervisor asks if not already provided.

**Checks:**
- Pod status: Running, CrashLoopBackOff, Error, Pending, OOMKilled
- Restart history: Count, frequency, termination reasons
- Events: Warning events for deployment/pod/namespace (last 1 hour)
- Resource specs: Requests vs limits vs actual usage (cross-referenced with Metrics Agent)
- Replica health: Desired vs available vs ready
- Node conditions: If scheduling issues detected

**Output:**

```python
class PodHealthStatus(BaseModel):
    pod_name: str
    status: str
    restart_count: int
    last_termination_reason: Optional[str]
    last_restart_time: Optional[datetime]
    resource_requests: dict[str, str]
    resource_limits: dict[str, str]

class K8sEvent(BaseModel):
    timestamp: datetime
    type: Literal["Normal", "Warning"]
    reason: str
    message: str
    source_component: str

class K8sAnalysisResult(BaseModel):
    cluster_name: str
    namespace: str
    service_name: str
    pod_statuses: list[PodHealthStatus]
    events: list[K8sEvent]
    is_crashloop: bool
    total_restarts_last_hour: int
    resource_mismatch: Optional[str]
    findings: list[Finding]
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int
    tokens_used: TokenUsage
```

**Connection:** OpenShift API via `kubernetes` Python client. Auth via `OPENSHIFT_TOKEN` env var. Cluster URL from user input or `OPENSHIFT_API_URL` env var.

### Tracing Agent (ReAct) — Jaeger First, ELK Fallback

**Strategy:**
1. Query Jaeger/Tempo for structured trace data
2. If no data or invalid response → fall back to Elasticsearch log-based trace reconstruction
3. ELK reconstruction: search by `trace_id`, `correlation_id`, `request_id`, `x-request-id` across all service indices

**ELK Reconstruction:**
- Groups logs by service name, sorts by timestamp
- Identifies entry/exit points from log patterns
- LLM reconstructs call chain from log context when fields are ambiguous
- Calculates approximate latency from timestamp differences
- Lower confidence score than Jaeger (inferred vs structured)

**Output:**

```python
class SpanInfo(BaseModel):
    span_id: str
    service_name: str
    operation_name: str
    duration_ms: float
    status: Literal["ok", "error", "timeout"]
    error_message: Optional[str]
    parent_span_id: Optional[str]
    tags: dict[str, str]

class TraceAnalysisResult(BaseModel):
    trace_id: str
    total_duration_ms: float
    total_services: int
    total_spans: int
    call_chain: list[SpanInfo]
    failure_point: Optional[SpanInfo]
    cascade_path: list[str]
    latency_bottlenecks: list[SpanInfo]
    retry_detected: bool
    service_dependency_graph: dict[str, list[str]]
    trace_source: Literal["jaeger", "tempo", "elasticsearch", "combined"]
    elk_reconstruction_confidence: Optional[int]
    findings: list[Finding]
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int
    tokens_used: TokenUsage
```

**Connection:** Configurable via `TRACING_URL` env var (Jaeger or Tempo HTTP API). Elasticsearch reuses existing connection from Log Agent.

### Code Navigator Agent (ReAct) — Multi-File Impact

**Traces outward from error location to find all connected code:**
- Direct impact: Files containing the erroring code
- Upstream callers: What calls the broken function (N levels deep)
- Downstream dependencies: What the broken function calls
- Shared resources: Config files, utilities, shared components
- Related test files: Existing tests for impacted code

**Output:**

```python
class ImpactedFile(BaseModel):
    file_path: str
    impact_type: Literal["direct_error", "caller", "callee", "shared_resource", "config", "test"]
    relevant_lines: list[LineRange]
    code_snippet: str
    relationship: str
    fix_relevance: Literal["must_fix", "should_review", "informational"]

class CodeAnalysisResult(BaseModel):
    root_cause_location: ImpactedFile
    impacted_files: list[ImpactedFile]
    call_chain: list[str]
    dependency_graph: dict[str, list[str]]
    shared_resource_conflicts: list[str]
    suggested_fix_areas: list[FixArea]
    mermaid_diagram: str
    negative_findings: list[NegativeFinding]
    breadcrumbs: list[Breadcrumb]
    overall_confidence: int
    tokens_used: TokenUsage
```

---

## Shared Data Models

### Core Models (Used by All Agents)

```python
class Breadcrumb(BaseModel):
    agent_name: str
    action: str
    source_type: Literal["log", "metric", "k8s_event", "trace_span", "code", "config"]
    source_reference: str
    raw_evidence: str
    timestamp: datetime

class NegativeFinding(BaseModel):
    agent_name: str
    what_was_checked: str
    result: str
    implication: str
    source_reference: str

class Finding(BaseModel):
    finding_id: str
    agent_name: str
    category: str
    summary: str
    confidence_score: int
    severity: Literal["critical", "high", "medium", "low"]
    breadcrumbs: list[Breadcrumb]
    negative_findings: list[NegativeFinding]
    critic_verdict: Optional[CriticVerdict]

class CriticVerdict(BaseModel):
    finding_id: str
    agent_source: str
    verdict: Literal["validated", "challenged", "insufficient_data"]
    reasoning: str
    contradicting_evidence: Optional[list[Breadcrumb]]
    recommendation: Optional[str]
    confidence_in_verdict: int

class TokenUsage(BaseModel):
    agent_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int

class TaskEvent(BaseModel):
    timestamp: datetime
    agent_name: str
    event_type: Literal["started", "progress", "success", "warning", "error"]
    message: str
    details: Optional[dict]
```

### Master Diagnostic State

```python
class DiagnosticState(BaseModel):
    session_id: str
    phase: DiagnosticPhase

    # User input
    service_name: str
    trace_id: Optional[str]
    time_window: TimeWindow
    cluster_url: Optional[str]
    namespace: Optional[str]
    repo_url: Optional[str]

    # Agent results
    log_analysis: Optional[LogAnalysisResult]
    metrics_analysis: Optional[MetricsAnalysisResult]
    k8s_analysis: Optional[K8sAnalysisResult]
    trace_analysis: Optional[TraceAnalysisResult]
    code_analysis: Optional[CodeAnalysisResult]

    # Cross-cutting
    all_findings: list[Finding]
    all_negative_findings: list[NegativeFinding]
    all_breadcrumbs: list[Breadcrumb]
    critic_verdicts: list[CriticVerdict]

    # Tracking
    token_usage: list[TokenUsage]
    task_events: list[TaskEvent]

    # Supervisor decisions
    supervisor_reasoning: list[str]
    agents_completed: list[str]
    agents_pending: list[str]
    overall_confidence: int
```

### Confidence Score Thresholds

| Score | Meaning | Supervisor Action |
|---|---|---|
| 90-100 | Very high — strong evidence from multiple sources | Proceed confidently |
| 70-89 | Good — evidence supports conclusion | Proceed with caveats noted |
| 50-69 | Moderate — some evidence but gaps exist | Ask user: investigate deeper or proceed? |
| Below 50 | Low — insufficient or contradictory evidence | Mandatory: ask user for guidance |

---

## UI Design — Hybrid Chat + Tabbed Dashboard

### Layout

```
+-----------------------------------------------------------+
|  Header: AI SRE Troubleshooting Platform                  |
+-------------+---------------------------------------------+
|             |  [Chat]  [Dashboard]  [Activity Log]  tabs   |
|  Sessions   +---------------------------------------------+
|             |                                              |
|  Session 1  |  CHAT TAB (default):                        |
|  Session 2  |  - Conversation with AI                     |
|  Session 3  |  - Compact summaries inline                 |
|             |  - "View details" links to Dashboard tab     |
|  + New Chat |                                              |
|             |  DASHBOARD TAB:                              |
|             |  - Grid layout with all agent result cards   |
|             |  - Charts, traces, code side by side         |
|             |  - Full-size visualizations                  |
|             |  - Auto-populates as agents complete         |
|             |                                              |
|             |  ACTIVITY LOG TAB:                           |
|             |  - Full task log with timestamps             |
|             |  - Token usage breakdown                     |
|             |                                              |
|             |  [input box - always visible on all tabs]    |
+-------------+---------------------------------------------+
|  Tokens: 23,350 | Phase: Code Analysis | Confidence: 87%  |
+-----------------------------------------------------------+
```

### Chat Tab
- Primary interface — conversation flow with AI
- Compact inline summaries from agents
- "View details" links switch to Dashboard tab
- User can type at any time: status queries, additional context, priority overrides

### Dashboard Tab
- Grid layout with agent result cards
- Error patterns: prioritized table with severity badges, expandable raw log snippets
- Metrics charts (Recharts): CPU/memory time-series with highlighted spike regions
- K8s status: pod table with restart counts, CrashLoopBackOff badges, events timeline
- Trace visualization: Mermaid sequence diagram with failure highlighting
- Code impact: file tree with impact type badges, expandable code snippets, dependency graph
- Diagnosis summary: root cause statement, evidence, negative findings, Critic status

### Activity Log Tab
- Live-scrolling task log with timestamps and color-coded event types
- Token usage breakdown by agent
- Clickable events

### Status Bar (always visible)
- Total tokens used
- Current phase
- Overall confidence score

### Multiple Sessions
- Left sidebar lists all sessions
- Each session has independent DiagnosticState
- "New Chat" button starts fresh session
- Sessions persist in-memory (Redis upgrade path)

---

## Interactive Chat Behavior

**User messages during analysis:**
1. Status queries ("What's happening?") — Supervisor responds with current phase and findings
2. Additional context ("Check namespace prod-east too") — Supervisor incorporates and re-routes agents
3. Priority overrides ("Focus on memory issue first") — Supervisor adjusts dispatch order
4. Follow-up requests ("Also check redis") — Supervisor queues new investigation

**When agent is mid-execution:** "Log Agent is still analyzing. I'll incorporate your input once it completes."

---

## Technology Decisions

| Decision | Choice |
|---|---|
| LLM | Anthropic Claude only (no OpenAI) |
| LLM SDK | Anthropic Python SDK directly |
| Orchestration | LangGraph (state machine + nodes) |
| Prometheus | HTTP API, configurable endpoint |
| K8s/OpenShift | `kubernetes` Python client |
| Tracing | Jaeger first, ELK fallback |
| Frontend charts | Recharts |
| UI pattern | Hybrid chat + tabbed dashboard |
| Session storage | In-memory (Redis upgrade path) |
| Token tracking | Anthropic `usage` response field |
| Data models | Pydantic throughout |

---

## What Gets Rebuilt vs Extended

| Component | Action |
|---|---|
| `orchestrator.py` | Rebuild — Supervisor Agent with state machine |
| `agent1_log_analyzer.py` | Rebuild — ReAct, pattern detection, prioritization |
| `agent2_code_navigator.py` | Rebuild — ReAct, multi-file impact analysis |
| `agent3/fix_generator.py` | Extend — works with new state model, Anthropic-only |
| `agent4_metrics_analyzer.py` | Rebuild — ReAct, Prometheus integration |
| New: `k8s_agent.py` | New — OpenShift/K8s health checks |
| New: `tracing_agent.py` | New — Jaeger + ELK fallback |
| New: `critic_agent.py` | New — Cross-validation |
| New: `models/schemas.py` | New — All shared Pydantic models |
| `TroubleshootingUI.tsx` | Rebuild — Chat-centered + tabbed dashboard |
| `api/main.py` | Extend — Multi-session, enhanced WebSocket |

---

## Out of Scope (for now)

- Redis session persistence (design for it, implement in-memory first)
- Authentication / RBAC
- Historical incident learning
- Auto-remediation (runbook execution)

---

## Typical Flow

```
User: "Troubleshoot order-service, trace_id abc-123"
    |
    v
Supervisor -> Log Agent (ReAct)
    |  Found 4 patterns, primary: DatabaseTimeout (conf: 87%)
    v
Critic validates -> OK
    |
    v
Supervisor decides: dispatch Metrics + K8s in parallel
    |
    +-> Metrics Agent -> Memory spike 95% at 14:02
    +-> K8s Agent -> needs cluster details -> asks user via chat
    |       User provides -> 6 restarts, OOMKilled
    |
    v
Critic cross-validates -> Memory spike + OOM consistent
    |
    v
Supervisor -> Tracing Agent
    |  Jaeger returns data -> call chain mapped
    |  Failure: inventory-service -> postgres (31s timeout)
    v
Critic validates -> OK
    |
    v
Supervisor -> Code Navigator (ReAct)
    |  Found 6 impacted files, root cause in connection pool config
    v
Critic validates -> OK
    |
    v
Supervisor: overall confidence 89% -> DIAGNOSIS_COMPLETE
    |
    v
Present to user:
  - Primary pattern: DatabaseTimeout (fix first)
  - 3 secondary patterns saved for later
  - "Generate Fix?" -> user approves -> Fix Generator creates PR
```

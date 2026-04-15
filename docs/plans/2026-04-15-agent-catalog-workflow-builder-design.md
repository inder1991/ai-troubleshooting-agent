# Agent Catalog + Workflow Builder — Design

**Status:** Approved design, ready for implementation plan.
**Date:** 2026-04-15
**Hard constraint:** Zero behavioral change to the existing Auto-mode (Supervisor-driven) diagnostic workflow. Everything below is additive and opt-in, gated by feature flags that default OFF until explicit rollout.

---

## 1. Goal

Let users author, run, and inspect **deterministic diagnostic workflows** as an alternative to the existing adaptive Supervisor-driven Auto mode. System-defined workflows remain read-only; users compose new workflows from a catalog of agents whose inputs/outputs/trigger examples are declared in version-controlled manifests.

The feature has four user-visible surfaces:
- **Agent Catalog** — discover what each agent does and what it expects (inputs, outputs, triggers, cost).
- **Workflow Builder** — author conditional DAGs with three interchangeable views (list, canvas, YAML) over a single canonical model.
- **Workflow Runner** — auto-generated input forms; runtime reuses the existing Investigation view with a DAG progress strip added.
- **Run History** — past runs per workflow, with re-run and open-in-investigation.

---

## 2. Architecture

### 2.1 Mental model

```
                       Decision Layer
                ┌────────────────────────────┐
                │ SupervisorAgent (mode=auto)│  unchanged in Phase 1
                │ WorkflowExecutor           │
                │   (mode=workflow)          │
                └──────────────┬─────────────┘
                               │ only WorkflowExecutor calls ↓
                        ┌──────▼───────┐
                        │ Orchestrator │   validation, retry, timeout,
                        │ (pure exec)  │   events, state
                        └──────┬───────┘
                               │
                        ┌──────▼───────┐
                        │  Agents      │   unchanged: async def run(ctx)
                        │  (10 today)  │
                        └──────┬───────┘
                               │
                   ┌───────────▼────────────┐
                   │  ContractRegistry      │   versioned YAML manifests
                   │  (name, version) keyed │
                   └────────────────────────┘

                   WebSocket event adapter   ← normalizes Auto-mode
                   into typed StepEvent schema
```

### 2.2 Responsibility boundaries

| Component | Owns | Does NOT own |
|---|---|---|
| `SupervisorAgent` (existing) | Auto-mode adaptive reasoning; current retry/event logic | Anything new. Unchanged in Phase 1. |
| `WorkflowExecutor` (new) | Deterministic DAG walk; fan-out/fan-in via `asyncio.gather`; applies `on_failure` policy; watchdog | Any LLM reasoning; agent selection; adaptive retry decisions |
| `Orchestrator` (new) | Contract validation (in/out); retry mechanics (declared policy); timeout via `asyncio.wait_for`; standard `StepEvent` emission; state update | Agent selection; workflow branching; LLM reasoning; cost/budget |
| `ContractRegistry` (new) | Load/index versioned YAML manifests; serve schemas; soft-validate inputs/outputs | Runtime execution decisions |
| Agents (existing) | Their `async def run(ctx) -> dict` logic | Unchanged |

**Design rule (Phase 1):** Orchestrator accepts an externally-supplied `RetryPolicy` and `timeout_seconds` — no Custom-mode-specific assumptions. Supervisor integration (Phase 5) is a pure plug-in with no signature change.

---

## 3. Contract System

### 3.1 Manifest format (JSON-Schema-compatible YAML)

Location: `backend/src/agents/manifests/<agent_name>.yaml` (one file per agent, per version when breaking).

```yaml
name: k8s_agent
version: 2
deprecated_versions: [1]
description: Diagnoses Kubernetes cluster and workload issues.
category: infrastructure
tags: [cluster, pods, events]

inputs:
  type: object
  properties:
    cluster_id: { type: string }
    namespace:  { type: string }
    service_name: { type: string }
  required: [cluster_id]

outputs:
  type: object
  properties:
    pod_statuses: { type: array, items: { type: object } }
    k8s_events:   { type: array }
    findings:     { type: array }
  required: [pod_statuses]

trigger_examples:
  - "Why is my pod crashing?"
  - "Check cluster health for service X"
  - "Investigate OOMKilled events"

retry_on: [TimeoutError, ConnectionError]   # known classes; resolved at load time
timeout_seconds: 30                          # default; overridable per node, bounded by server cap
cost_hint: { llm_calls: 2, typical_duration_s: 15 }
```

### 3.2 Non-negotiables

1. No agent is registered in the catalog without a manifest file.
2. Every manifest must include: input schema, output schema, ≥ 2 trigger examples. Startup fails loudly if any manifest violates.
3. Manifests are the single source of truth for agent shape. The rest of the system only asks `ContractRegistry`.

### 3.3 Versioning

- `(name, version)` is the registry key.
- Breaking changes bump `version`; a new manifest file is added. Old version remains loadable until no workflow references it.
- Workflows pin `agent_version` per node. Save-time validation rejects references to unknown or missing (name, version) tuples.
- UI flags workflows pinned to `deprecated_versions`.
- CI test enforces breaking-change rules: removing required input, changing output key type, tightening required-ness → MUST bump version.

### 3.4 Runtime validation

Uses `jsonschema`. Validation returns a list of errors rather than raising; Orchestrator converts to `StepFailed(reason="schema_error")` and halts. In Phase 5 (Supervisor migration) validation starts warn-only for Auto mode before being flipped to strict.

### 3.5 API

```
GET /v4/catalog/agents                     # list (name, version, category, tags, cost_hint)
GET /v4/catalog/agents/{name}              # full contract, latest version
GET /v4/catalog/agents/{name}/v/{version}  # specific version
```

All public, read-only, cached in frontend.

---

## 4. Orchestrator (execution substrate)

### 4.1 Signature

```python
async def execute_step(
    *,
    node_id: str,
    agent_name: str,
    agent_version: int,
    input: dict,
    retry_policy: RetryPolicy,
    timeout_seconds: float,
    state: DiagnosticState,
    emitter: EventEmitter,
) -> dict:
    ...
```

### 4.2 Execution flow

```
1. registry.validate_input(agent_name, agent_version, input)
   └─ errors → emit StepFailed(schema_error) → raise ContractViolation

2. emit StepStarted(node_id, agent_name, input_keys)

3. attempts = 0
   while attempts < retry_policy.max_attempts:
     attempts += 1
     try:
       result = await asyncio.wait_for(
           agent.run(input), timeout=timeout_seconds
       )
       break
     except asyncio.CancelledError:
       emit StepCancelled(node_id, elapsed_ms); raise
     except asyncio.TimeoutError:
       emit StepTimedOut(node_id, elapsed_ms, timeout_seconds)
       if TimeoutError not in retry_policy.retry_on or attempts >= max_attempts:
         emit StepFailed(reason="timeout", attempts_used=attempts); raise
       await sleep(compute_delay(retry_policy, attempts))
       emit StepRetry(node_id, attempts, error_class="TimeoutError", elapsed_ms)
     except Exception as e:
       if type(e) not in retry_policy.retry_on or attempts >= max_attempts:
         emit StepFailed(reason="agent_error", error_class=type(e).__name__,
                         attempts_used=attempts); raise
       await sleep(compute_delay(retry_policy, attempts))
       emit StepRetry(node_id, attempts, error_class=type(e).__name__, elapsed_ms)

4. registry.validate_output(agent_name, agent_version, result)
   └─ errors → emit StepFailed(output_schema_error) → raise

5. state.update(node_id, result)
6. emit StepCompleted(node_id, duration_ms, attempts_used=attempts)
```

**Invariants:** `StepFailed` is always emitted before any raise on failure paths. `StepCancelled` always emitted in `finally` on cancellation.

### 4.3 Retry policy

```python
class RetryPolicy(BaseModel):
    max_attempts: int = 1                                    # 1 = no retry
    backoff: Literal["fixed", "exponential"] = "fixed"
    delay_seconds: float = 0
    jitter: bool = False                                     # default off → deterministic
    retry_on: list[type[Exception]] = []                     # resolved from YAML class names
```

**Backoff formulas (pinned):**
- `fixed`: `delay = delay_seconds`
- `exponential`: `delay = delay_seconds * (2 ** (attempt - 1))`
- If `jitter=True`: add uniform `[0, delay * 0.1]`.

### 4.4 Event taxonomy (typed, shared across modes)

```python
class StepEvent(BaseModel):
    type: Literal["step_started","step_retry","step_timed_out",
                  "step_failed","step_completed","step_cancelled","step_skipped"]
    node_id: str | None                   # None for Auto mode (no DAG)
    agent: str
    agent_version: int | None
    timestamp: datetime
    run_mode: Literal["auto", "workflow"]
    workflow_id: str | None
    attempt: int | None
    duration_ms: int | None
    error: ErrorInfo | None
    skip_reason: str | None
```

Auto-mode events pass through a thin WebSocket-layer adapter that wraps existing emissions into this shape (`run_mode="auto"`, `node_id=None`). Supervisor code is **not** modified in Phase 1.

---

## 5. Workflow Model

### 5.1 Canonical DAG JSON (single source of truth for all three views)

```json
{
  "workflow_id": "wf_01HG...",
  "name": "CrashLoop Investigation",
  "version": 3,
  "description": "Standard playbook for repeated pod restarts",
  "created_by": "user_123",
  "created_at": "2026-04-15T10:00:00Z",
  "updated_at": "2026-04-15T14:22:00Z",
  "is_system": false,

  "input_schema": {
    "type": "object",
    "properties": {
      "cluster_id": { "type": "string" },
      "namespace":  { "type": "string" },
      "service_name": { "type": "string" }
    },
    "required": ["cluster_id", "namespace"]
  },

  "limits": {
    "workflow_max_seconds": 600,
    "max_total_nodes": 50,
    "max_parallel_nodes": 5
  },

  "nodes": [
    {
      "id": "n1",
      "label": "Log Analysis",
      "agent": "log_agent",
      "agent_version": 2,
      "input_mapping": {
        "service_name": "$input.service_name",
        "time_window": { "minutes": 30 }
      },
      "trigger": { "kind": "always" },
      "retry": {
        "max_attempts": 2,
        "backoff": "exponential",
        "delay_seconds": 2,
        "retry_on": ["TimeoutError"]
      },
      "timeout_seconds": 30,
      "on_failure": { "action": "continue" }
    }
  ],

  "edges": [
    { "from": "n1", "to": "n2" },
    { "from": "n1", "to": "n3" },
    { "from": "n2", "to": "n4" },
    { "from": "n3", "to": "n4" }
  ],

  "groups": [
    { "id": "g1", "label": "Infra checks", "members": ["n2","n3"], "wait_for": "all" }
  ],

  "layout": {
    "positions": { "n1": {"x":0,"y":0}, "n2": {"x":200,"y":-60}, "n3": {"x":200,"y":60}, "n4": {"x":400,"y":0} }
  }
}
```

**Rules:**
- `edges[]` is the single source of truth for ordering. `depends_on` is removed.
- `groups[]` is UI metadata only. Executor works on flat `nodes + edges`. Fan-in is implicit: when the set of a group's members all complete, downstream edges from any member fire normally.
- `layout.positions` is cosmetic; executor ignores it.
- `trigger.kind ∈ {"always", "predicate"}`; predicates are a structured JSON AST (not strings).
- Fallback nodes are regular nodes referenced by another node's `on_failure.fallback_node_id`.

### 5.2 Predicate AST

```json
{ "op": "and", "args": [
  { "op": "==", "lhs": "$node.n1.output.severity", "rhs": "critical" },
  { "op": ">",  "lhs": "$node.n1.output.findings.length", "rhs": 3 }
]}
```

**MVP operators:** `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `contains`, `exists`, `and`, `or`, `not`, `length`.

**Deterministic evaluation rules** when referenced node state is:

| State | Result |
|---|---|
| `completed`, path resolves | evaluate operator normally |
| `completed`, path missing/null | `false` (unless op is `exists` → `false`; or `not exists` → `true`) |
| `failed` | `false` always |
| `skipped` | `false` always |
| `cancelled` | `false` always |
| not yet executed | save-time validation forbids forward references |

Predicate false → `StepSkipped(node_id, reason="predicate_false", referenced_nodes=[...])`.

### 5.3 Input mapping

Values: literal, `$input.X`, `$node.<id>.output.<path>`, `$env.VAR`.

**Save-time validation** resolves `$node.<id>.output.<path>` against the upstream agent's `output_schema`. Unknown keys / type mismatches are rejected. JSONPath subset: `.field`, `.field[index]`, `.field[*].sub`. Wildcards return arrays.

### 5.4 Failure policies

- `stop` — halt entire run; remaining nodes marked `not_started`; run status `failed`.
- `continue` — mark node `failed` in state; downstream nodes still run (predicates decide if they execute).
- `fallback` — invoke `fallback_node_id` once:
  - Bypasses its own `trigger` (unconditional invocation).
  - Runs at most once per run; subsequent invocations log `FallbackSuppressed`.
  - Its downstream edges fire normally after it completes — re-enters DAG.
  - Save-time: fallback graph must be acyclic; chain depth ≤ 2.
  - Marked in state: `invoked_as: "fallback", for_node: "<failing_node_id>"`.

### 5.5 Limits (enforced in both places)

**Save time (static validation, reject if violated):**
- `limits.workflow_max_seconds ≤ WORKFLOW_MAX_SECONDS_HARD` (e.g. 900)
- `limits.max_total_nodes ≤ MAX_TOTAL_NODES_HARD` (e.g. 100)
- `limits.max_parallel_nodes ≤ MAX_PARALLEL_NODES_HARD` (e.g. 10)
- Every node's `timeout_seconds ≤ WORKFLOW_NODE_TIMEOUT_MAX`

**Run time (safety guards):**
- `asyncio.Semaphore(max_parallel_nodes)` in Executor.
- Watchdog task sleeping `workflow_max_seconds`, then cancels.
- Orchestrator enforces per-node `timeout_seconds`.

### 5.6 Watchdog cancellation path

```
watchdog fires
 └─ executor._cancel_requested = True
 └─ executor._cancel_event.set()
 └─ cancel every asyncio.Task in _active_node_tasks
      └─ each Orchestrator call unwinds via CancelledError
      └─ emits StepCancelled(node_id, elapsed_ms) in finally
 └─ nodes never scheduled → status="not_started" in node_states
 └─ workflow_run.status = "cancelled", ended_at = now
 └─ emit WorkflowCancelled(run_id, reason="watchdog_timeout")
 └─ persist final node_states_json
```

Same path for user-triggered cancellation; different `reason`.

### 5.7 Run state structure

```python
class NodeState(BaseModel):
    status: Literal["not_started","running","completed","failed","skipped","cancelled"]
    attempts: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    invoked_as: Literal["normal","fallback"] = "normal"
    for_node: str | None = None
    skip_reason: str | None = None
    error: ErrorInfo | None = None
    output_ref: str | None = None

class WorkflowRunState(BaseModel):
    nodes: dict[str, NodeState]
```

### 5.8 Persistence

```sql
CREATE TABLE workflows (
  workflow_id     TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  version         INTEGER NOT NULL,
  is_system       BOOLEAN NOT NULL DEFAULT 0,
  created_by      TEXT,
  created_at      TIMESTAMP NOT NULL,
  updated_at      TIMESTAMP NOT NULL,
  dag_json        TEXT NOT NULL,
  input_schema    TEXT NOT NULL,
  latest          BOOLEAN NOT NULL DEFAULT 1,
  UNIQUE(name, version)
);
CREATE INDEX ix_workflows_name_latest ON workflows(name, latest);

CREATE TABLE workflow_runs (
  run_id            TEXT PRIMARY KEY,
  workflow_id       TEXT NOT NULL REFERENCES workflows(workflow_id),
  workflow_version  INTEGER NOT NULL,
  mode              TEXT NOT NULL DEFAULT 'workflow',
  session_id        TEXT NOT NULL,
  input_json        TEXT NOT NULL,
  status            TEXT NOT NULL,
  started_at        TIMESTAMP NOT NULL,
  ended_at          TIMESTAMP,
  node_states_json  TEXT
);
CREATE INDEX ix_workflow_runs_session ON workflow_runs(session_id);
CREATE INDEX ix_workflow_runs_status  ON workflow_runs(status);
```

- `workflow_id` is immutable; `name` is mutable and unique per scope; `version` is monotonic per `workflow_id`.
- Editing a workflow inserts a new row with `latest=1` and flips the previous `latest` row to `0`.
- `is_system=1` rows rejected by `PUT`/`DELETE`.

### 5.9 API routes (all additive)

```
# Catalog (read-only)
GET    /v4/catalog/agents
GET    /v4/catalog/agents/{name}
GET    /v4/catalog/agents/{name}/v/{version}

# Workflows (CRUD)
GET    /v4/workflows
GET    /v4/workflows/{workflow_id}
POST   /v4/workflows
PUT    /v4/workflows/{workflow_id}        # creates new version; rejected if is_system
DELETE /v4/workflows/{workflow_id}        # soft delete; rejected if is_system
POST   /v4/workflows/{workflow_id}/validate

# Runs
POST   /v4/workflows/{workflow_id}/runs                 # requires If-Match: <version>
POST   /v4/workflows/{workflow_id}/v/{version}/runs     # preferred, version-pinned
GET    /v4/workflow-runs/{run_id}
POST   /v4/workflow-runs/{run_id}/cancel
GET    /v4/workflow-runs?workflow_id=&status=

# Templates
GET    /v4/workflows/templates
POST   /v4/workflows/from-template/{name}
```

### 5.10 Save-time validation checklist

- DAG schema parses (Pydantic).
- Topo sort succeeds; no cycles.
- Every `(agent, agent_version)` exists in `ContractRegistry`.
- `input_mapping` references resolve:
  - `$input.X` matches a property in workflow `input_schema`.
  - `$node.<id>.output.<path>` references an upstream node; path is valid against that agent's `output_schema`.
- Every node's `timeout_seconds ≤ WORKFLOW_NODE_TIMEOUT_MAX`.
- `limits` within server hard caps.
- Predicate AST operators are known.
- Fallback graph acyclic; chain depth ≤ 2.

---

## 6. UI

### 6.1 Agent Catalog — `/catalog`

Two-pane. Left: searchable list (filters: category, tag, deprecated). Right: selected agent's contract — input/output schemas as collapsible trees, trigger examples, cost hint, version selector. Action: "Use in workflow". Read-only in MVP; admin enable/disable deferred to Phase 6.

### 6.2 Workflow Builder — `/workflows/{id}/edit`

**Shell:** metadata strip, view switcher (List / Canvas / YAML), inspector right rail (always visible), footer (Validate / Save as new version / Run). System workflows render all three views read-only with "Clone to edit".

**Single canonical DAG model in a React store. All three views are renderings of the same object.**

**View switching when YAML is invalid:**
```
Invalid YAML detected — changes won't be applied.
[Fix YAML]   [Discard and switch]
```
Discard reverts YAML buffer to the last valid autosaved model.

**List view (primary authoring surface):**
- Linear step rows with inline trigger/retry/timeout summaries.
- Parallel groups rendered with `⇄` icon, dashed container, `⏸ Next step runs after all complete` footer.
- Click any row → opens Inspector.
- Drag-to-reorder with constraint enforcement (see below).

**Canvas view (reactflow):**
- Nodes + edges from the same model.
- Dashed bounding box around `groups[].members`.
- Auto-layout (dagre/elk) on open; manual positions persisted to `layout.positions`.
- Drag to pan, pinch to zoom, click node to edit in Inspector.
- Cannot introduce anything list view can't express — same underlying model.

**YAML view:**
- Monaco editor with JSON Schema autocomplete (generated from Pydantic DAG model).
- Format button; inline validation.
- Forgiving switch-away via discard prompt.

**Inspector (single edit surface):**
- Agent + version dropdowns.
- Inputs with explicit mode selector per field:
  - `🔤 Literal` · `📥 Workflow Input` · `🔗 From Previous Step` · `🌍 Environment`
  - Resolved value/path shown as pill.
- Trigger builder (form → predicate AST) with data-lineage breadcrumb:
  ```
  Field: $node.n1.output.findings[*].title
         └─ Log Analysis → findings[].title
  ```
- Retry: max_attempts, backoff, delay_seconds, retry_on (multiselect from known exception classes).
- Timeout: per-node override (manifest default shown).
- On failure: stop / continue / fallback → picker for another node.
- **Resolved input preview** (collapsible):
  - Uses last successful run's data if available, else manifest `trigger_examples` as fake upstream outputs, else placeholders.
  - Red-highlighted keys flag unresolvable mappings.

**Drag-and-drop constraints:**
- Blocked moves: before a dependency, into an incompatible group, creating a cycle.
- Snap-back animation + toast:
  ```
  ⚠ Cannot move "Code Analysis" before "Log Analysis"
  Code Analysis depends on Log Analysis findings.
  ```

### 6.3 Run input form (auto-derived)

At `Run` time, a `JsonSchemaForm` (using `@rjsf/core`) renders the workflow's `input_schema`. Required fields marked. Type-appropriate inputs. Pre-fill from last run (localStorage per workflow_id). Submit disabled until valid.

On submit: `POST /v4/workflows/{id}/v/{version}/runs` with `{ input }`, then navigate to Investigation view for the returned `session_id`.

### 6.4 Runtime UI (reuse existing Investigation view)

`InvestigationView` reads `run_mode`:
- `auto` — renders exactly as today.
- `workflow` — adds:
  - Header pill: `Workflow: CrashLoop Investigation · v3` linking to the workflow definition.
  - `DagProgressStrip` in the RemediationProgressBar area — hierarchical layout (groups as bounding boxes; merge icon at fan-in), color-coded by `NodeState.status`. Click a pill → scroll event timeline to that node.
  - "Cancel run" button (only while running).
  - `step_skipped` events get a muted badge with `skip_reason` tooltip.

Zero changes required to Investigator, EvidenceFindings, Navigator, HypothesisScoreboard.

### 6.5 Templates

Three MVP system workflows, seeded from `backend/src/workflows/system/*.json` at startup, `is_system=1`:
1. **CrashLoop Investigation** — logs → (k8s || metrics) → code.
2. **Latency Spike Triage** — metrics → tracing → code.
3. **Deployment Rollback Decision** — change → code → critic.

**Template preview modal:**
```
┌─ CrashLoop Investigation ─────────────────┐
│ Standard playbook for repeated pod restarts│
│  [ mini DAG preview (read-only canvas) ]  │
│  Est. cost: ~5 LLM calls · ~45s typical   │
│  Steps: 4 · Parallel groups: 1            │
│  [ Cancel ]   [ Use this template ]       │
└───────────────────────────────────────────┘
```
"Use this template" → `POST /v4/workflows/from-template/{name}` → editable clone → redirect.

### 6.6 Run History

`/workflows` list rows show last-run badge:
```
CrashLoop Investigation · v3    Last run: ✓ 12m ago
Latency Spike Triage · v2       Last run: ✗ 2h ago (timeout)
Deployment Rollback · v1        Never run
```

`/workflows/{id}/runs` — table with filters (status, version, date range), pagination, per-row actions (`Open`, `Re-run with same input`, `Delete` creator-only).

Runtime Investigation view breadcrumbs back to this list.

### 6.7 Permissions (MVP)

- Anyone authenticated can create workflows.
- Anyone can read all workflows.
- Only creator edits/deletes (via `created_by`).
- System workflows are uneditable for everyone.

Admin RBAC / org-scoped visibility / agent enable-disable deferred to Phase 6.

---

## 7. Non-Impact Guarantees for the Existing Diagnostic Workflow

| Area | Guarantee |
|---|---|
| `SupervisorAgent` | Zero lines changed in Phase 1 |
| LangGraph graph | Unchanged |
| `/v4/sessions`, `/v4/findings`, `/v4/status`, `/v4/chat` | Unchanged response shapes |
| `DiagnosticState` | Additive only; no renamed/removed field |
| WebSocket events (Auto mode) | Unchanged emissions; typed shape via boundary adapter only |
| `InvestigationView` (mode=auto) | Byte-identical DOM snapshot |
| Database | New tables only; no ALTER on existing |

**Feature flags (default OFF):**
- `CATALOG_UI_ENABLED`
- `WORKFLOW_BUILDER_ENABLED`
- `WORKFLOW_EXECUTOR_ENABLED`
- `SUPERVISOR_USE_ORCHESTRATOR` (Phase 5 only)

New endpoints return 404 while flags are off — indistinguishable from pre-feature state.

**Rollback contract:** disabling the three flags fully reverts UX. No migration needed — tables can remain empty.

---

## 8. Testing Strategy

**Unit:** `ContractRegistry`, validators, predicate evaluator, mapping resolver, topo sort, DAG Pydantic validation, `RetryPolicy` delays.

**Integration (Orchestrator):** every failure path — success, retry-success, retry-exhausted, timeout, schema mismatch (input), schema mismatch (output), cancellation. Event sequences asserted exactly.

**Integration (Executor):** linear success, fan-out/fan-in, predicate skip, `on_failure=continue/stop/fallback`, watchdog timeout, user cancel mid-run, determinism (same input + same fake-agent seed → byte-identical event sequence).

**Contract tests (CI):** every manifest parses, schemas valid, ≥ 2 trigger examples, `retry_on` classes resolvable, breaking-change rules enforced.

**Non-impact (CI, run on every PR):**
- Auto-mode snapshot suite: 20 recorded real-session inputs replayed through Supervisor; assert events + final `DiagnosticState` match golden files byte-for-byte.
- Route compatibility tests on `/v4/sessions`, `/v4/findings`, `/v4/status`, `/v4/chat`.
- Old session JSON payloads round-trip through new Pydantic models.
- `InvestigationView` (mode=auto) DOM snapshot unchanged.

**UI:** manual smoke scripts + visual regression on key screens (Storybook + Chromatic if available).

---

## 9. Phasing

| Phase | Scope | Duration | Flag | Blocker for next? |
|---|---|---|---|---|
| 1. Contract Foundation | Manifests for 10 agents, `ContractRegistry`, catalog UI (read-only) | ~1.5 wk | `CATALOG_UI_ENABLED` | Yes |
| 2. Orchestrator + Executor | `Orchestrator.execute_step`, `WorkflowExecutor`, DB tables, core API, typed events | ~2 wk | `WORKFLOW_EXECUTOR_ENABLED` | Yes |
| 3. Workflow Builder UI | List view, YAML view, inspector, input form, runtime UI additions, templates, run history | ~3 wk | `WORKFLOW_BUILDER_ENABLED` | No (MVP launch here) |
| 4. Canvas View | reactflow canvas with constraints + layout persistence | ~2 wk | (same flag) | No |
| 5. Supervisor Unification | Supervisor → Orchestrator migration; warn-only → strict validation | ~2 wk + canary | `SUPERVISOR_USE_ORCHESTRATOR` | No |
| 6. Management UI | Admin controls, analytics, org-scoped visibility | TBD | separate | No |

Each phase has its own exit criteria (see Section 5 of original design for full list). Critical invariant: the Auto-mode snapshot suite must stay green through every phase.

---

## 10. Documentation Deliverables

- `docs/agents/authoring-manifests.md`
- `docs/workflows/authoring.md`
- `docs/workflows/api.md`
- `docs/operations/workflow-flags.md`
- `docs/examples/` — the three seed template JSONs with commentary

---

## 11. Deferred / Out of Scope for MVP

- Admin RBAC and org-scoped visibility (Phase 6).
- Agent enable/disable per environment (Phase 6).
- `wait_for: "any"` and `"first_success"` on parallel groups (beyond MVP).
- Workflow cost/budget tracking beyond `cost_hint` display.
- Workflow sharing/export/import outside the system.
- Sub-workflow composition (calling a workflow from inside another).
- Automatic Pydantic model generation from YAML manifests (keeping the door open; not required for MVP).

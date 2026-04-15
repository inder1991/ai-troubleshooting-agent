# Phase 2 — Orchestrator + WorkflowExecutor (Design)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to turn this design into a TDD implementation plan. Do NOT implement directly from this doc.

**Date:** 2026-04-15
**Status:** Approved (with refinements)
**Depends on:** Phase 1 (`docs/plans/2026-04-15-phase1-contract-foundation.md`) — merged to `main` in PR #19.

---

## 1. Goal

Introduce a deterministic, flag-gated workflow execution layer that runs static DAGs of Phase-1 agent contracts. No changes to the existing supervisor / investigation flow. Builds the spine Phase 3 (builder UI), Phase 4 (canvas replay), and Phase 6 (admin) will sit on.

## 2. Non-goals

- No dynamic graph mutation; no loops; no conditional branching beyond node-level predicates.
- No change to `supervisor.py`, `routes_v4.py` diagnostic paths, `Investigation/**`, `schemas.py`.
- No auto-triggering from investigations; explicit API calls only.
- No new LLM calls in the executor itself (it orchestrates; agents still own their own LLM usage).

## 3. Architecture

Three-layer split preserves Phase 1's contract purity:

```
Contracts (Phase 1)        — schema, metadata (what)
        ↓
Orchestrator (Phase 2)     — scheduling, validation, state (how)
        ↓
AgentRunnerRegistry        — wiring contract name+version → callable
        ↓
Agent implementation       — existing Phase 0 code, untouched
```

Orchestrator imports from Runner; Runner imports from agent modules. **Runners never import `ContractRegistry`**; orchestrator is the only validation point.

## 4. Workflow model

### 4.1 Stored entity

Workflows are first-class, versioned resources:

- `workflows` — `(id, name, description, created_at, created_by)`
- `workflow_versions` — `(id, workflow_id, version, dag_json, compiled_json, created_at, is_active)`
  - `dag_json`: the submitted, human-authored DAG.
  - `compiled_json`: resolver/predicate AST pre-compiled at save.
  - `is_active`: `false` marks deprecated.

### 4.2 DAG schema

```json
{
  "inputs_schema": { ... JSON-Schema ... },
  "steps": [
    {
      "id": "fetch_logs",
      "agent": "log_agent",
      "agent_version": 1,
      "inputs": { "service": {"ref": {"from": "input", "path": "service"}} },
      "when": { "op": "eq", "left": {"ref": ...}, "right": "prod" },
      "on_failure": "fail",
      "parallel_group": "probe",
      "concurrency_group": "logs_api",
      "timeout_seconds_override": 30,
      "retry_on_override": ["TimeoutError"]
    }
  ]
}
```

Hard rules enforced at save:
- `id` unique within workflow_version; `[a-z][a-z0-9_]*`.
- `(agent, agent_version)` must exist in `ContractRegistry` and `AgentRunnerRegistry`.
- `agent_version` resolution: `"latest"` → highest version where the version is NOT in `deprecated_versions`.
- `timeout_seconds_override` MUST be ≤ contract's `timeout_seconds`. Loosening is rejected at save.
- `retry_on_override` MUST be a subset of contract's `retry_on`.
- Every `ref` path must resolve against the target contract's **output** JSON-Schema (for upstream refs) or workflow `inputs_schema` (for `"from": "input"`).
- Topological sort must succeed; cycles rejected.

### 4.3 Input mapping AST (compiled, frozen op set)

**Refs:**
```json
{ "ref": { "from": "node" | "input" | "env", "node_id": "fetch_logs", "path": "output.services[0].name" } }
```

**Literals:**
```json
{ "literal": "prod" }
```

**Transforms (frozen set for Phase 2):**
```
coalesce(*args) → first non-null
concat(*args)   → strings only
eq(left, right)
in(needle, haystack)
exists(ref)
and(*args), or(*args), not(arg)
```

Any operator not on this list → save rejected. New ops require a design amendment.

**Forbidden:**
- Wildcards (`$node.*.output`) — reintroduce implicit coupling.
- Writes to shared state.
- Cross-node output modification.
- References to downstream / sibling nodes (only upstream per topo order).

### 4.4 Predicates (`when`)

Same AST as transforms. Evaluated before the node is scheduled; if `false` or missing required refs, node state = `SKIPPED`.

### 4.5 Node state triad (locked)

```
SUCCESS | FAILED | SKIPPED
```

| Trigger | Consequence for downstream ref to this node |
|---|---|
| `SUCCESS` | Normal mapping resolution against `output`. |
| `FAILED` | Run already stopped (fail-fast) OR `on_failure` branch fired. Refs never resolved. |
| `SKIPPED` | Downstream ref → **runtime error** (not null). Node is "non-existent," not "empty." |

**FAILED triggers `on_failure`. SKIPPED does not.** This is deliberate: skip is author-intent, failure is operational.

### 4.6 Failure policy

Global default: **fail-fast** — any `FAILED` step terminates the run, remaining scheduled steps marked `cancelled`.

Per-step opt-in overrides:

| `on_failure` | Meaning |
|---|---|
| `fail` (default) | Run halts on this step's failure. |
| `continue` | Step is marked `FAILED`; downstream nodes that ref it will themselves fail (per §4.5). Other independent branches proceed. |
| `fallback` | Run the referenced `fallback_step_id` (see below); its output **replaces** the failed node's output in state. Fallback is a full node but with constraints. |

**Fallback tight contract (locked):**
- Single node, referenced by id.
- Fallback node MUST have no additional upstream dependencies beyond what the primary node had.
- Runs immediately on primary failure; not scheduled unless fired.
- Fallback's output replaces primary's output; downstream refs resolve against fallback.
- Fallback failure → treated as primary failure under global `fail-fast`.
- Fallback has its own `on_failure`? No. Fallback is terminal.

Save-time check: fallback target exists, no cycle, dependency-subset rule holds.

### 4.7 Timeouts, retries, cancellation

- **Timeout:** min(contract default, step override). Enforced by executor wrapping the runner coroutine in `asyncio.wait_for`.
- **Retry:** runner is retried up to `contract.retry_on` policy; step override can **narrow** the exception set only.
- **Cancellation states:** `RUNNING → CANCELLING → CANCELLED`.
  - `POST /runs/{id}/cancel` sets `CANCELLING`.
  - Executor immediately stops scheduling new nodes.
  - In-flight runners observe `context.is_cancelled` (cooperative).
  - 30-second grace window. On expiry: force `CANCELLED`; any still-in-flight step marked `cancelled`.

### 4.8 Concurrency

- Global cap: `MAX_CONCURRENT_STEPS` (env-driven; default 8).
- Per-step `concurrency_group` — optional; bounded by `CONCURRENCY_GROUP_CAPS: {"logs_api": 2, ...}` (env JSON).
- Schedule order when capped: **FIFO by readiness time** (tiebreaker: step id lex order).
- `parallel_group` (structural) is a distinct, purely informational label for Phase 4 canvas layout; scheduler ignores it.

## 5. Persistence

All tables under existing SQLite file (`data/debugduck.db`). Migrations go through the repo's existing migration pattern (same as Phase 1 — none yet, but Phase 2 adds one).

- `workflows` — as §4.1.
- `workflow_versions` — as §4.1.
- `workflow_runs` — `(id, workflow_version_id, status, started_at, ended_at, inputs_json, error_json, idempotency_key, run_mode)`.
  - `status`: `PENDING | RUNNING | CANCELLING | CANCELLED | SUCCEEDED | FAILED`.
  - `run_mode`: enum, Phase 2 value is `"workflow"` (future: `"investigation"`, `"scheduled"`).
  - `idempotency_key`: optional; unique per-workflow-version; duplicate `POST` returns the existing run.
- `workflow_step_runs` — `(id, run_id, step_id, status, started_at, ended_at, inputs_json, output_json, attempt, duration_ms, error_json)`.
- `workflow_run_events` — append-only.

### 5.1 Event schema

```json
{
  "event_id": "uuid",
  "run_id": "uuid",
  "sequence": 42,
  "timestamp": "...",
  "type": "step.started",
  "node_id": "fetch_logs",
  "attempt": 1,
  "duration_ms": null,
  "error_class": null,
  "error_message": null,
  "parent_node_id": null,
  "payload_json": {}
}
```

Event types: `run.started`, `run.completed`, `run.failed`, `run.cancelled`, `step.started`, `step.completed`, `step.failed`, `step.skipped`, `step.cancelled`.

`sequence` is monotonic per `run_id`, assigned at emit time under a row-lock.

## 6. Runtime integrity

- Startup: `AgentRunnerRegistry` built from `src/agents/runners/__init__.py`. For every contract in `ContractRegistry`, assert a runner exists. Missing runner → `StartupError`; app refuses to boot.
- Runtime: on run start, **re-validate each step's compiled mappings against the current contract version**. If the contract has drifted since save (schema or version deprecation), mark the run `FAILED` with a structured `drift_detected` error before any step executes.
- Safety cap: `MAX_TOTAL_STEPS_PER_RUN` (env, default 200). Authored workflows exceeding this rejected at save.

## 7. API surface

All endpoints flag-gated by `WORKFLOWS_ENABLED` (default OFF). 404 when flag off — same pattern as Phase 1 catalog.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v4/workflows` | Create workflow (name, description) |
| GET | `/api/v4/workflows` | List |
| GET | `/api/v4/workflows/{id}` | Fetch (with latest version summary) |
| POST | `/api/v4/workflows/{id}/versions` | Create new version (submits DAG, validates, compiles) |
| GET | `/api/v4/workflows/{id}/versions/{version}` | Fetch specific version |
| POST | `/api/v4/workflows/{id}/runs` | Execute (optional `idempotency_key`, `inputs`) |
| GET | `/api/v4/runs/{run_id}` | Run status + step summary |
| GET | `/api/v4/runs/{run_id}/events` | SSE stream (resumable via `Last-Event-ID` header) |
| POST | `/api/v4/runs/{run_id}/cancel` | Cooperative cancel |

SSE stream replays all persisted events for the run, then keeps the connection open and pushes new events until run reaches a terminal state.

## 8. Code layout

```
backend/src/
  contracts/                  (Phase 1 — unchanged)
  workflows/                  (NEW)
    __init__.py
    models.py                 — Pydantic DAG, StepSpec, ref/transform AST
    compiler.py               — DAG → compiled form, schema-aware validation
    executor.py               — scheduler, state machine, cancellation, concurrency
    runners/
      __init__.py             — composition root: registers all runners
      registry.py             — AgentRunnerRegistry
      log_agent.py            — thin adapter around existing log_agent
      ...                     — one per Phase-1 manifest
    repository.py             — SQLite access for workflows, versions, runs, events
    events.py                 — emit + SSE bridge
    migrations/
      001_create_workflow_tables.sql
  api/
    routes_workflows.py       — flag-gated REST + SSE
```

## 9. Non-impact invariants

Must all hold at merge:
- `git diff main..HEAD -- backend/src/agents/supervisor.py` empty.
- `git diff main..HEAD -- backend/src/api/routes_v4.py` empty.
- `git diff main..HEAD -- backend/src/models/schemas.py` empty.
- `git diff main..HEAD -- frontend/src/components/Investigation/` empty.
- Phase 1 catalog tests still green.
- With `WORKFLOWS_ENABLED=false`, every `/api/v4/workflows*` + `/api/v4/runs*` returns 404.

## 10. Phase 2 exit criteria

- Authored workflow creates + validates + compiles; saved; invalid DAGs rejected with precise error paths.
- Runner integrity check fails boot when a Phase-1 contract lacks a runner.
- Run executes with correct topo order, parallel within cap, SSE stream emits events with monotonic `sequence`.
- Failure: global fail-fast works; `continue` isolates; `fallback` replaces output; SKIPPED ref fails fast.
- Cancellation transitions `RUNNING → CANCELLING → CANCELLED` with 30s grace.
- Drift detection fires when contract version schema changes post-save.
- Full backend pytest suite green (Phase 1 + Phase 2).
- `WORKFLOWS_ENABLED=false` → all new routes 404.
- Non-impact invariants §9.

## 11. Open questions deferred to plan / later phases

- **Authorization / RBAC** on workflows: out of scope Phase 2 (single-tenant assumption, same as rest of v4). Phase 6.
- **Scheduled runs** (cron): Phase 6.
- **Workflow import/export**: Phase 6.
- **Investigation integration** (supervisor delegates to executor): Phase 5.
- **Frontend**: Phase 3 (builder) and Phase 4 (canvas) consume these APIs; Phase 2 ships **backend only** plus a minimal `/workflows` list page if time permits (stretch goal; not in exit criteria).

---

## Follow-on plan

The TDD implementation plan derived from this design will live at
`docs/plans/2026-04-15-phase2-executor-plan.md`.

# Phase 3 — Workflow Builder UI (Design)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to turn this design into a TDD implementation plan. Do NOT implement directly from this doc.

**Date:** 2026-04-15
**Status:** Approved (with refinements)
**Depends on:** Phase 1 (catalog) + Phase 2 (executor) — both merged to `main`.

---

## 1. Goal

Form-based workflow authoring UI that exercises the full Phase 2 save-path and run-path contracts. Users create workflows, add steps via drawer-based forms, wire input mappings via schema-aware ref pickers, author predicates via a simple/advanced AST builder, save as immutable versions, run with a schema-driven inputs form, and watch live step status via SSE.

## 2. Non-goals

- No drag/drop graph canvas. Full visual canvas is a **separate later phase** (explicitly deferred until Phases 4, 5, 6 ship).
- No draft/publish lifecycle. Versions are immutable; every save = new version.
- No changes to Phase 2 backend contracts, schemas, or routes.
- No new feature flag (reuses `WORKFLOWS_ENABLED`).
- No investigation/supervisor integration (Phase 5).
- No workflow import/export, RBAC, scheduled runs (Phase 6).

## 3. Scope lock (Q1)

Phase 3 = form-based step builder (option b). Full canvas (option c) is deferred.

## 4. Information architecture

```
/workflows                              WorkflowBuilderPage (default view)
  ├─ version switcher (Q8)             — pick any version; edit forks a new one
  ├─ step list                         — execution truth, compact summary per step
  ├─ step drawer                       — per-step form (right-side panel)
  └─ "Save as new version" button      — always creates N+1

/workflows/runs                         WorkflowRunsPage
  ├─ run list (per workflow)
  └─ run detail pane: inputs form + step status panel (Q3) + SSE stream

/workflows/runs/:id                     RunDetailPage (live or historical)
```

Both views can trigger a run (Q2 = c): "Run" button on builder header (enters inputs form, navigates to `/runs/:id`), and "New run" button on the runs tab with the same inputs form + events component.

## 5. Component namespace (Q11)

New dedicated namespace. Old `Platform/WorkflowBuilder` + `Platform/WorkflowRuns` placeholders are left untouched during development; routes repointed atomically; legacy deleted only once the new surface is stable.

```
frontend/src/components/Workflows/
  Builder/
    WorkflowBuilderPage.tsx
    StepList.tsx
    StepDrawer.tsx
    StepSummaryRow.tsx
    PredicateBuilder/
      SimplePredicate.tsx
      AdvancedAstBuilder.tsx
      index.tsx
    RefPicker/
      RefPicker.tsx
      PathAutocomplete.tsx
    InputMapping/
      InputMappingField.tsx
      MappingModeToggle.tsx      — literal | input | node | env
  Runs/
    WorkflowRunsPage.tsx
    RunDetailPage.tsx
    StepStatusPanel.tsx          — cards per step (Q3)
    InputsForm.tsx               — shared with builder "Run" button
    EventsRawStream.tsx          — behind a "Show events" toggle
  Shared/
    WorkflowHeader.tsx
    VersionSwitcher.tsx          — Q8
    ValidationBanner.tsx
    DisabledState.tsx            — when flag off
    types.ts                     — local view-only types
```

Service modules: `frontend/src/services/workflows.ts`, `frontend/src/services/runs.ts`. Shared API types extend `frontend/src/types/index.ts`.

## 6. Authoring model (Q5)

### 6.1 Step list (execution truth)

One row per step, in DAG authoring order. Each row shows:

- Step id (editable inline via drawer)
- Agent name + version
- Trigger summary (if `when` set): human readable e.g. `if log.output.root_cause == "OOMKilled"`
- `on_failure` policy (icon + label)
- Concurrency group (if set)
- Timeout (if overridden)

Drag-to-reorder allowed but **guarded**: client validates that dependency graph remains legal (no ref to a step later in the list). Invalid drop → rejected with inline toast.

### 6.2 Step drawer

Right-side drawer, not modal. Sections (collapsible; sensible defaults; rarely-used tucked away):

1. **Agent** — picker from `/api/v4/catalog/agents` (Phase 1); version selector (defaults to latest non-deprecated).
2. **Inputs** — schema-driven per contract's `inputs_schema`; each field has a mapping-mode toggle (literal | workflow input | upstream node output | env). Literal uses Q4 hybrid renderer; non-literal modes open a RefPicker.
3. **Trigger (`when`)** — simple mode default (Q6); "Advanced" toggles to AST builder.
4. **Failure** — radio: fail (default) | continue | fallback → if fallback, step picker for `fallback_step_id` (must exist, no cycle, deps-subset; client validates).
5. **Execution** — optional `timeout_seconds_override` (client caps at contract's timeout), `retry_on_override` (subset of contract's), `concurrency_group` (free text).

### 6.3 Ref picker (critical UX)

Two-step picker:

1. **Source**: radio — Workflow input | Upstream step output | Env.
2. **Field**: autocomplete populated from the source's JSON Schema (walks `properties` / `items` / nested objects). Only shows legal paths. Shows description as hover hint.

Produces `{"ref": {"from": "node" | "input" | "env", "node_id": "...", "path": "output.foo.bar"}}` matching Phase 2's compiled AST. Node refs are always prefixed with `output.` (Phase 2 compiler requirement).

### 6.4 "Add step" flow

1. Click "+ Add step".
2. Prompt: "Pick an agent".
3. On pick: auto-generate step id (`<agent>_1`, increment on collision), open drawer.
4. User fills inputs/predicate/failure policy.
5. Drawer close → step lands in list; not yet persisted server-side.

## 7. Inputs form for workflow runs (Q4)

Hybrid. Given a workflow version's `inputs_schema`:

- **Supported subset** → auto-rendered widgets:
  - `string` → text input
  - `string` with `enum` → select
  - `string` with `format: date-time` → datetime-local input
  - `integer` / `number` → numeric input
  - `boolean` → checkbox
  - flat `object` (depth ≤ 2) → nested fieldset
- **Complex constructs** (`oneOf`, `anyOf`, `allOf`, arrays of objects, depth > 2) → auto-fallback to JSON textarea with AJV validation.
- **Toggle**: even for simple schemas, a `[Form view] [JSON view]` toggle lets power users author raw.
- **Unified validation**: both modes validate against the same compiled AJV validator; errors surface inline.
- **localStorage prefill**: last successful inputs per `workflow_id` remembered.
- **Schema descriptions surfaced inline** (field hints, required badges, `examples[0]` as placeholder).

Out of scope: full JSON Schema coverage, `format` handling beyond `date-time`, custom widgets.

## 8. Predicate editor (Q6)

### 8.1 Simple mode (default)

Single-clause UI:

```
Field:  [Step fetch_logs → output.status]
Op:     [ == ]
Value:  ["OOMKilled"]
```

Operators exposed: `==` (eq), `!=` (not+eq), `>`, `>=`, `<`, `<=`, `contains` (in), `exists`.
- Numeric ops hidden for string fields; `contains` hidden for numbers. Type inferred from referenced schema node.
- Enforces completeness — partial clauses cannot save.

### 8.2 Advanced mode

Tree editor for nested `and` / `or` / `not`. "Add condition" / "Add group" buttons. Each leaf is a simple-mode clause.

### 8.3 Mode switch

- Simple → Advanced: wraps single clause in trivial `and([...])`.
- Advanced → Simple: only allowed when the AST is a single clause. Otherwise warning: `This condition is too complex for simple mode. [Stay in advanced] [Reset to simple]`.

### 8.4 Separation

- Predicate UI exposes only decision operators (`eq, in, exists, and, or, not`, + comparison wrappers).
- **`coalesce` and `concat` stay out of predicate UI** — those live only in the Input Mapping UI (data transforms). Backend shares the AST engine; the UI enforces the split.

## 9. Validation model (Q7)

Hybrid client + server.

### 9.1 Client-side (live, every edit)

- Required fields present per the step schema.
- Ref paths resolve against cached contract `inputs_schema` / `outputs_schema` from the catalog.
- AST completeness — no partial `{op: "eq", left: ?}` nodes.
- `on_failure=fallback` requires `fallback_step_id` pointing to a step that exists, is not the step itself, and has a deps-subset relationship.
- Step id pattern `[a-z][a-z0-9_]*` and uniqueness.
- `timeout_seconds_override ≤ contract.timeout_seconds`; `retry_on_override ⊆ contract.retry_on`.

Save button is **disabled** while any structural error is live; the `ValidationBanner` enumerates errors with jump-to-step links.

### 9.2 Server-side (authoritative)

- Phase 2 compiler runs all client checks plus: topological sort, full JSON Schema path resolution, `MAX_TOTAL_STEPS_PER_RUN`, drift-adjacent invariants.
- Server returns `422` with `{detail: {type: "compile_error" | "dag_invalid", message, path}}` (Phase 2 shape).
- Client maps `detail.path` → step id → highlights the offending step and section.

### 9.3 Non-goals

The client does **not** re-implement the compiler. Compiler is the source of truth for: contract drift, deep schema resolution edge cases, cycle detection, anything the catalog schemas can't determine in isolation.

## 10. Version management (Q8)

- **Version switcher** in builder header — dropdown of all versions + created_at; current version badge says `Active` if it's the latest non-deprecated.
- Selecting a version loads its compiled DAG into the editor **as a draft copy** — editor never mutates the persisted version.
- Save button label is literally `Save as new version` — no ambiguity that editing is immutable.
- Header shows `Editing new version (based on v3)` when a non-latest version is selected as the fork source.
- Version history panel: list of `{version, created_at, author?}` with actions `View` (read-only drawer opens all steps collapsed) and `Edit` (forks — loads into builder).
- No server-side drafts. Reloading the page discards in-memory edits (with a confirm-navigation guard if dirty).

## 11. Run trigger + live view (Q2, Q3)

### 11.1 Triggering a run

Two entry points, shared underlying flow:

1. **Builder header "Run" button** → opens `InputsForm` modal → submits `POST /api/v4/workflows/:id/runs` → navigates to `/workflows/runs/:run_id`.
2. **Runs tab "New run"** → same modal, same flow.

Both pass `idempotency_key` optionally (advanced field hidden behind "More options"); default omits it.

### 11.2 Live view

Step status panel (option b), one card per step:

- Status badge: PENDING / RUNNING / SUCCESS / FAILED / SKIPPED / CANCELLED
- Attempt counter
- Duration (live-updating for RUNNING; final for terminal)
- Error class + message for FAILED
- Expand-to-see output JSON for SUCCESS (pretty-printed)

Subscribes to `GET /api/v4/runs/:run_id/events` via `EventSource`. `Last-Event-ID` supported by Phase 2 already; client uses it on reconnect.

Raw event stream (`EventsRawStream`) is hidden behind a `[Show events]` toggle — renders the chronological list of events for debugging.

Cancel button on the run detail page → `POST /api/v4/runs/:id/cancel`. Disabled if run is already terminal.

## 12. Flag gating (Q9)

Backend: unchanged — `WORKFLOWS_ENABLED=false` returns 404 on all workflow/run routes.

Frontend (hybrid: probe + defensive):

- **Boot-time probe**: on app init, a `FeatureProbe` hook hits `GET /api/v4/workflows`; 200 → feature enabled, 404 → disabled. Result stored in a global `FeatureFlagsContext`.
- **Nav gating**: if disabled, `SidebarNav` hides `Workflows` entries; `router.tsx` route guard redirects `/workflows*` to `NotFound`.
- **API wrapper** (`services/workflows.ts`, `services/runs.ts`): all calls surface a `WorkflowsDisabledError` on 404. Pages catch it and render `DisabledState` with a "Retry" button that re-probes (handles mid-session flag flips / partial deploys / direct URL access).
- Future (not Phase 3): `GET /api/v4/features` aggregate endpoint — noted for Phase 6.

## 13. API client (services)

### 13.1 `services/workflows.ts`

```ts
listWorkflows(): Promise<WorkflowSummary[]>
getWorkflow(id): Promise<WorkflowDetail>
createWorkflow({name, description, created_by?}): Promise<WorkflowDetail>
listVersions(workflowId): Promise<VersionSummary[]>
getVersion(workflowId, version): Promise<WorkflowVersionDetail>  // includes dag + compiled
createVersion(workflowId, dag): Promise<VersionSummary>          // server compiles; 422 on invalid
```

### 13.2 `services/runs.ts`

```ts
createRun(workflowId, {inputs, idempotency_key?}): Promise<RunDetail>
getRun(runId): Promise<RunDetail>                                 // includes step_runs[]
cancelRun(runId): Promise<RunDetail>                              // 409 if terminal
subscribeEvents(runId, lastEventId?): EventSource                 // wraps native EventSource
```

All throw `WorkflowsDisabledError` on 404; map pydantic 422 errors to a typed `CompileError` class with `{type, message, path}` shape.

### 13.3 Types (extend `frontend/src/types/index.ts`)

- `WorkflowSummary`, `WorkflowDetail`
- `VersionSummary`, `WorkflowVersionDetail`
- `RunDetail`, `StepRunDetail`, `RunStatus`
- `WorkflowDag`, `StepSpec`, `RefExpr`, `TransformExpr`, `PredicateExpr` — mirror Phase 2 pydantic models as TS types

These types are additive; no existing types change.

## 14. Testing (Q10)

### 14.1 Unit + component (Vitest + React Testing Library + MSW)

Per-component:
- `StepList` — renders summary rows; drag reorder obeys dep guards.
- `StepDrawer` — opens/closes; section collapse; form dirty tracking.
- `RefPicker` — lists only valid paths per schema; autocomplete filters.
- `InputMappingField` — mode toggle switches between literal editor and ref picker.
- `SimplePredicate` — op list varies with inferred field type; produces correct AST.
- `AdvancedAstBuilder` — round-trips nested AST; add/remove nodes.
- Mode switch (Simple↔Advanced) — downgrade guard works.
- `InputsForm` — hybrid renderer falls back to JSON for `oneOf`.
- `FeatureFlagsContext` + `DisabledState` — 404 → disabled; retry re-probes.
- `VersionSwitcher` — fork-on-edit flow.
- `ValidationBanner` — client errors + server 422 path mapping.
- `StepStatusPanel` — SSE event updates card status live.

MSW handlers cover: catalog list/detail, workflows CRUD, runs CRUD, SSE (using MSW's SSE support or a tiny custom mock).

### 14.2 Single Playwright E2E smoke

Playwright infrastructure does not currently exist in this repo — added as its own Phase 3 task (scaffolding + CI config).

Scenario (deterministic, no real LLM calls, stub agents registered in backend test fixture):

1. Visit `/workflows`.
2. Create workflow "Smoke".
3. Add step A (agent `log_agent` v1, literal input).
4. Add step B (agent `log_agent` v1, input refs A's output).
5. Save → version 1 created.
6. Click Run → fill inputs form → submit.
7. Observe step cards: A runs → SUCCESS → B runs → SUCCESS → run SUCCEEDED.
8. Assert final status.

Failure-case E2E deferred.

### 14.3 Manual verification checklist

A new `docs/` manual-verification checklist (same pattern as the CI/CD Phase A checklist) — covers mid-session flag flips, concurrent runs, SSE reconnect, drag-reorder edge cases, advanced predicate round-trip.

## 15. Code layout summary

```
frontend/src/
  components/Workflows/
    Builder/
    Runs/
    Shared/
  services/
    workflows.ts
    runs.ts
  types/
    index.ts                 (add workflow/run types)
  contexts/
    FeatureFlagsContext.tsx  (NEW — probes on boot)

frontend/e2e/                 (NEW — Playwright scaffolding)
  playwright.config.ts
  workflows.spec.ts
```

## 16. Non-impact invariants

Must all hold at merge:
- `git diff main..HEAD -- backend/` empty. Phase 3 is frontend only.
- `git diff main..HEAD -- frontend/src/components/Investigation/` empty.
- `git diff main..HEAD -- frontend/src/components/Platform/WorkflowBuilder/` empty during Phase 3 development (deletion lands in a final cleanup commit only after the new surface is stable).
- Phase 1 + Phase 2 tests still green.
- With `WORKFLOWS_ENABLED=false`: `/workflows` routes redirect to `NotFound`; no workflow nav items visible.

## 17. Phase 3 exit criteria

- Workflow created, version 1 saved, run executed, live events observed, final success — happy-path end-to-end works against a real backend.
- Version switcher lets user view + fork old versions; save always creates N+1.
- Step drawer supports all Phase 2 authoring primitives: agent pick, input mapping (literal + ref picker), predicate simple mode, advanced AST, failure policy (fail/continue/fallback), execution overrides.
- Predicate simple/advanced mode switching works per §8.3 guard.
- Inputs form hybrid: supported subset auto-rendered; complex schemas fall back to JSON.
- Flag OFF: nav hidden, routes 404-redirected, direct-URL page shows disabled state with retry.
- Vitest suite green; one Playwright E2E smoke passes with stub agents.
- Non-impact invariants §16.

## 18. Deferred to later phases

- Drag/drop visual canvas authoring — post-Phase-6.
- Canvas *replay* (read-only graph of a completed run) — Phase 4.
- Supervisor integration — Phase 5.
- RBAC, scheduled runs, import/export, aggregate `/features` endpoint — Phase 6.
- Full JSON Schema UI coverage (custom widgets, `format`-specific inputs beyond date-time).
- Draft/publish lifecycle.

---

## Follow-on plan

The TDD implementation plan derived from this design will live at
`docs/plans/2026-04-15-phase3-builder-plan.md`.

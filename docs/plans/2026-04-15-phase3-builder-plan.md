# Phase 3 — Workflow Builder UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task.

**Goal:** Ship a flag-gated form-based workflow authoring UI + run viewer that exercises the full Phase 2 save-path and run-path.

**Architecture:** New `frontend/src/components/Workflows/` namespace. Version-switching builder with per-step drawer, ref picker, simple/advanced predicate builder. Hybrid inputs form. SSE-driven live step status panel. Playwright E2E scaffolding added from scratch.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind (`wr-*` tokens), Vitest, React Testing Library, MSW, AJV, Playwright.

**Design:** `docs/plans/2026-04-15-phase3-builder-design.md`.

**Branch:** `feature/phase3-builder` (already created).

**Dev server:** `cd frontend && npm run dev`. Backend in separate terminal: `cd backend && uvicorn src.api.main:app --reload` with `WORKFLOWS_ENABLED=true CATALOG_UI_ENABLED=true`.

**Test commands:**
- Unit/component: `cd frontend && npm run test -- --run` (Vitest)
- Backend guard: `python3 -m pytest backend/tests/test_phase2_non_impact.py -q`
- E2E: `cd frontend && npm run test:e2e` (Playwright; added in Task 23)

---

## Batch map (for subagent dispatch)

| Batch | Tasks | Theme |
|---|---|---|
| A | 1-3 | Types + services + flag context |
| B | 4-5 | Nav gating + disabled state + route guard |
| C | 6-8 | Shared UI primitives: ValidationBanner, VersionSwitcher, WorkflowHeader |
| D | 9-11 | Ref picker + input mapping + literal widgets |
| E | 12-13 | Predicate builder (simple + advanced + mode switch) |
| F | 14-16 | Step list + summary row + drag guard |
| G | 17 | Step drawer (composes D+E+F into the editor) |
| H | 18 | WorkflowBuilderPage (top-level composition + save path) |
| I | 19-20 | Inputs form hybrid (widgets + JSON fallback) + run trigger |
| J | 21-22 | Step status panel + SSE subscription + run detail page |
| K | 23 | Runs list page |
| L | 24 | Playwright scaffolding |
| M | 25 | E2E smoke |
| N | 26-27 | Delete legacy + non-impact snapshot + final verification + PR |

---

## Task 1: Extend shared types for workflows

**Files:**
- Modify: `frontend/src/types/index.ts` (append only)

**Step 1: Write failing test**

Create `frontend/src/types/__tests__/workflow-types.test.ts`:

```ts
import type {
  WorkflowSummary, WorkflowDetail,
  VersionSummary, WorkflowVersionDetail,
  WorkflowDag, StepSpec, RefExpr, PredicateExpr,
  RunDetail, StepRunDetail, RunStatus,
} from '../index';

test('types compile', () => {
  const s: WorkflowSummary = { id: 'w1', name: 'n', description: 'd', created_at: '2026-04-15T00:00:00Z' };
  const r: RunStatus = 'succeeded';
  expect(s.id).toBe('w1');
  expect(r).toBe('succeeded');
});
```

**Step 2:** Run `cd frontend && npm run test -- --run workflow-types` — FAIL (types missing).

**Step 3: Add types to `frontend/src/types/index.ts`**

Append (match Phase 2 pydantic shapes + lowercase-on-wire status vocabulary):

```ts
export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  created_at: string;
  created_by?: string;
}
export interface VersionSummary {
  version_id: string;
  workflow_id: string;
  version: number;
  created_at: string;
}
export interface WorkflowDetail extends WorkflowSummary {
  latest_version?: { version: number; created_at: string };
}
export interface WorkflowVersionDetail {
  workflow_id: string;
  version: number;
  created_at: string;
  dag: WorkflowDag;
  compiled: unknown;
}

export type RefExpr =
  | { ref: { from: 'input'; path: string } }
  | { ref: { from: 'env'; path: string } }
  | { ref: { from: 'node'; node_id: string; path: string } };

export type LiteralExpr = { literal: unknown };

export type TransformExpr =
  | { op: 'coalesce' | 'concat'; args: MappingExpr[] };

export type PredicateExpr =
  | { op: 'eq' | 'in' | 'exists'; left?: MappingExpr; right?: MappingExpr; args?: MappingExpr[] }
  | { op: 'and' | 'or'; args: PredicateExpr[] }
  | { op: 'not'; arg: PredicateExpr };

export type MappingExpr = RefExpr | LiteralExpr | TransformExpr;

export interface StepSpec {
  id: string;
  agent: string;
  agent_version: number | 'latest';
  inputs: Record<string, MappingExpr>;
  when?: PredicateExpr;
  on_failure?: 'fail' | 'continue' | 'fallback';
  fallback_step_id?: string;
  parallel_group?: string;
  concurrency_group?: string;
  timeout_seconds_override?: number;
  retry_on_override?: string[];
}

export interface WorkflowDag {
  inputs_schema: Record<string, unknown>;
  steps: StepSpec[];
}

export type RunStatus =
  | 'pending' | 'running' | 'cancelling' | 'cancelled'
  | 'succeeded' | 'failed';

export type StepRunStatus =
  | 'pending' | 'running' | 'success' | 'failed'
  | 'skipped' | 'cancelled';

export interface StepRunDetail {
  id: string;
  step_id: string;
  status: StepRunStatus;
  attempt: number;
  started_at?: string;
  ended_at?: string;
  duration_ms?: number;
  output?: unknown;
  error?: { type?: string; class?: string; message?: string };
}

export interface RunDetail {
  id: string;
  workflow_version_id: string;
  status: RunStatus;
  started_at?: string;
  ended_at?: string;
  inputs: Record<string, unknown>;
  error?: { type?: string; message?: string };
  idempotency_key?: string;
  step_runs: StepRunDetail[];
}
```

**Step 4:** `npm run test -- --run workflow-types` — PASS.

**Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/types/__tests__/workflow-types.test.ts
git commit -m "types(workflows): phase 2 DAG + run shapes"
```

---

## Task 2: `services/workflows.ts` + `services/runs.ts`

**Files:**
- Create: `frontend/src/services/workflows.ts`
- Create: `frontend/src/services/runs.ts`
- Test: `frontend/src/services/__tests__/workflows.test.ts`
- Test: `frontend/src/services/__tests__/runs.test.ts`

**Step 1: Failing tests (using MSW)**

Set up MSW per-test file. In `workflows.test.ts`:

```ts
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { listWorkflows, createWorkflow, createVersion, WorkflowsDisabledError, CompileError } from '../workflows';

const server = setupServer();
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test('listWorkflows returns array', async () => {
  server.use(http.get('*/api/v4/workflows', () =>
    HttpResponse.json({ workflows: [{ id: 'w1', name: 'x', description: '', created_at: '2026-01-01T00:00:00Z' }] })));
  const result = await listWorkflows();
  expect(result).toHaveLength(1);
});

test('listWorkflows 404 throws WorkflowsDisabledError', async () => {
  server.use(http.get('*/api/v4/workflows', () => new HttpResponse(null, { status: 404 })));
  await expect(listWorkflows()).rejects.toBeInstanceOf(WorkflowsDisabledError);
});

test('createVersion 422 throws CompileError with path', async () => {
  server.use(http.post('*/api/v4/workflows/:id/versions', () =>
    HttpResponse.json({ detail: { type: 'compile_error', message: 'unknown agent', path: 'steps[0].agent' } }, { status: 422 })));
  try {
    await createVersion('w1', { inputs_schema: {}, steps: [] });
    fail('should throw');
  } catch (e: any) {
    expect(e).toBeInstanceOf(CompileError);
    expect(e.path).toBe('steps[0].agent');
  }
});
```

Similar for `runs.test.ts`: `createRun`, `getRun`, `cancelRun` (409 if terminal), `subscribeEvents` (returns EventSource — verify URL contains `run_id`).

**Step 2:** Run — FAIL.

**Step 3: Implement services**

`services/workflows.ts`:
```ts
import { API_BASE_URL } from './api';
import type { WorkflowSummary, WorkflowDetail, VersionSummary, WorkflowVersionDetail, WorkflowDag } from '../types';

export class WorkflowsDisabledError extends Error {
  constructor() { super('Workflows feature is disabled.'); this.name = 'WorkflowsDisabledError'; }
}
export class CompileError extends Error {
  constructor(public type: string, message: string, public path?: string, public errors?: unknown[]) {
    super(message); this.name = 'CompileError';
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (resp.status === 404) throw new WorkflowsDisabledError();
  if (resp.status === 422) {
    const body = await resp.json().catch(() => ({}));
    const d = body?.detail ?? {};
    throw new CompileError(d.type ?? 'compile_error', d.message ?? 'invalid', d.path, d.errors);
  }
  if (!resp.ok) throw new Error(`${init?.method ?? 'GET'} ${path} failed: ${resp.status}`);
  return resp.json();
}

export async function listWorkflows(): Promise<WorkflowSummary[]> {
  const data = await call<{ workflows: WorkflowSummary[] }>('/api/v4/workflows');
  return data.workflows;
}
export const getWorkflow = (id: string) => call<WorkflowDetail>(`/api/v4/workflows/${id}`);
export const createWorkflow = (body: { name: string; description: string; created_by?: string }) =>
  call<WorkflowDetail>('/api/v4/workflows', { method: 'POST', body: JSON.stringify(body) });
export const listVersions = (workflowId: string) =>
  call<{ versions: VersionSummary[] }>(`/api/v4/workflows/${workflowId}/versions`).then(d => d.versions);
export const getVersion = (workflowId: string, version: number) =>
  call<WorkflowVersionDetail>(`/api/v4/workflows/${workflowId}/versions/${version}`);
export const createVersion = (workflowId: string, dag: WorkflowDag) =>
  call<VersionSummary>(`/api/v4/workflows/${workflowId}/versions`, { method: 'POST', body: JSON.stringify(dag) });
```

**Note (LOCKED):** Backend does NOT currently expose `GET /api/v4/workflows/:id/versions`. Phase 3 adds this endpoint as its **only allowed backend change** — trivial additive route mirroring the `GET /:id/versions/:v` shape. Implement it as part of Task 2 with a backend test. Call it out explicitly in the PR.

`services/runs.ts` (similar structure):
```ts
export const createRun = (workflowId, body) => call(...);
export const getRun = (runId) => call<RunDetail>(`/api/v4/runs/${runId}`);
export const cancelRun = (runId) => call<RunDetail>(`/api/v4/runs/${runId}/cancel`, { method: 'POST' });
export function subscribeEvents(runId: string, lastEventId?: number): EventSource {
  const url = `${API_BASE_URL}/api/v4/runs/${runId}/events`;
  const es = new EventSource(url, { withCredentials: false });
  // Note: browser EventSource handles Last-Event-ID automatically on reconnect.
  // For explicit initial Last-Event-ID we'd need a polyfill; defer.
  return es;
}
```

**Step 4:** Tests PASS.

**Step 5: Commit**
```bash
git add frontend/src/services/workflows.ts frontend/src/services/runs.ts frontend/src/services/__tests__/
git commit -m "feat(workflows): API client (services + typed errors)"
```

---

## Task 3: `FeatureFlagsContext` with boot-time probe

**Files:**
- Create: `frontend/src/contexts/FeatureFlagsContext.tsx`
- Test: `frontend/src/contexts/__tests__/FeatureFlagsContext.test.tsx`
- Modify: `frontend/src/main.tsx` (wrap app in provider)

**Step 1: Failing test**

```tsx
test('probe 200 → workflows enabled', async () => {
  server.use(http.get('*/api/v4/workflows', () => HttpResponse.json({ workflows: [] })));
  render(<FeatureFlagsProvider><Probe /></FeatureFlagsProvider>);
  await waitFor(() => expect(screen.getByText(/workflows: on/i)).toBeInTheDocument());
});
test('probe 404 → workflows disabled', async () => { /* similar, 404 */ });
test('retry() re-probes', async () => { /* flip handler, call retry, assert flip */ });
```

**Step 2:** FAIL.

**Step 3: Implement**

```tsx
import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';

type Flags = { workflows: boolean; loading: boolean };
const Ctx = createContext<Flags & { retry: () => Promise<void> }>(null!);

export function FeatureFlagsProvider({ children }: { children: React.ReactNode }) {
  const [flags, setFlags] = useState<Flags>({ workflows: false, loading: true });
  const probe = useCallback(async () => {
    setFlags(f => ({ ...f, loading: true }));
    try {
      const r = await fetch(`${API_BASE_URL}/api/v4/workflows`);
      setFlags({ workflows: r.status !== 404, loading: false });
    } catch {
      setFlags({ workflows: false, loading: false });
    }
  }, []);
  useEffect(() => { probe(); }, [probe]);
  return <Ctx.Provider value={{ ...flags, retry: probe }}>{children}</Ctx.Provider>;
}
export const useFeatureFlags = () => useContext(Ctx);
```

Wrap `<App />` in provider inside `main.tsx`.

**Step 4:** PASS.

**Step 5: Commit** `feat(workflows): feature flag boot probe + context`

---

## Task 4: Sidebar nav gating

**Files:**
- Modify: `frontend/src/components/Layout/SidebarNav.tsx`
- Test: `frontend/src/components/Layout/__tests__/SidebarNav.test.tsx`

**Step 1: Failing test** — render nav with flag off, assert `Workflows` label absent; flag on, assert present.

**Step 2:** FAIL.

**Step 3:** In `SidebarNav`, read `useFeatureFlags()`. If `!workflows`, filter out the `workflows` + `workflows/runs` entries from the Platform group.

**Step 4:** PASS.

**Step 5: Commit** `feat(workflows): hide nav when flag off`

---

## Task 5: Route guard + `DisabledState` page

**Files:**
- Create: `frontend/src/components/Workflows/Shared/DisabledState.tsx`
- Modify: `frontend/src/router.tsx` (add guard)
- Test: `frontend/src/components/Workflows/Shared/__tests__/DisabledState.test.tsx`
- Test: `frontend/src/router.test.tsx` (route guard redirects)

**Step 1: Failing tests**

- `DisabledState` renders message + Retry button; clicking Retry calls `useFeatureFlags().retry()`.
- With flag off, visiting `/workflows` lands on `NotFound` or `DisabledState` (pick one — spec uses `DisabledState`; router redirects `/workflows*` to `DisabledState` page at `/workflows/disabled` OR simply renders `DisabledState` inline as the route element when flag off).

**Step 3:**

```tsx
export function DisabledState() {
  const { retry, loading } = useFeatureFlags();
  return (
    <div className="...">
      <p>Workflows feature is disabled in this environment.</p>
      <button onClick={() => retry()} disabled={loading}>Retry</button>
    </div>
  );
}
```

Router wraps workflow routes with a `<WorkflowsGuard>` that returns children when enabled or `<DisabledState />` when disabled.

**Step 5: Commit** `feat(workflows): route guard + disabled state`

---

## Task 6: `ValidationBanner`

**Files:**
- Create: `frontend/src/components/Workflows/Shared/ValidationBanner.tsx`
- Test: `frontend/src/components/Workflows/Shared/__tests__/ValidationBanner.test.tsx`

Accepts `errors: {path: string; message: string; stepId?: string}[]` and `onJump(stepId)`. Renders nothing if empty. Each error has a jump link if `stepId` present.

**Commit:** `feat(workflows): validation banner`

---

## Task 7: `VersionSwitcher`

**Files:**
- Create: `frontend/src/components/Workflows/Shared/VersionSwitcher.tsx`
- Test: `__tests__/VersionSwitcher.test.tsx`

Props: `{ versions: VersionSummary[]; activeVersion?: number; selectedVersion: number; onSelect(v); onFork(v); }`.
Renders dropdown of versions; selected badge = "Active" if it's latest. Below dropdown: `[View] [Edit]` buttons. View is read-only; Edit calls `onFork(v)`.

Tests: dropdown lists all; clicking Edit triggers onFork; selecting a non-latest shows "Based on vN" subhead.

**Commit:** `feat(workflows): version switcher`

---

## Task 8: `WorkflowHeader`

**Files:**
- Create: `frontend/src/components/Workflows/Shared/WorkflowHeader.tsx`
- Test: `__tests__/WorkflowHeader.test.tsx`

Composes workflow name + description, VersionSwitcher, "Save as new version" button (disabled when invalid), "Run" button.

**Commit:** `feat(workflows): builder header`

---

## Task 9: `RefPicker` + `PathAutocomplete`

**Files:**
- Create: `frontend/src/components/Workflows/Builder/RefPicker/RefPicker.tsx`
- Create: `frontend/src/components/Workflows/Builder/RefPicker/PathAutocomplete.tsx`
- Create: `frontend/src/components/Workflows/Builder/RefPicker/schemaPaths.ts` (pure helper)
- Test: `__tests__/schemaPaths.test.ts` (unit)
- Test: `__tests__/RefPicker.test.tsx` (component)

**`schemaPaths.ts`:**

```ts
export function listPaths(schema: any, prefix = ''): string[] {
  if (!schema || typeof schema !== 'object') return [];
  const out: string[] = [];
  if (schema.properties) {
    for (const [k, sub] of Object.entries<any>(schema.properties)) {
      const p = prefix ? `${prefix}.${k}` : k;
      out.push(p);
      out.push(...listPaths(sub, p));
    }
  }
  if (schema.items) out.push(...listPaths(schema.items, `${prefix}[*]`));
  return out;
}
```

**`RefPicker`:**
- Props: `{ sources: RefSource[]; value?: RefExpr; onChange(RefExpr); onClose() }`.
- `RefSource`: `{ kind: 'input' | 'node' | 'env'; label: string; nodeId?: string; schema: object }`.
- Two-step UI: pick source (radio), then path (autocomplete against `listPaths(source.schema)`). For `node` source, path is forced to start with `output.` (per Phase 2 compiler).

Tests:
- `schemaPaths` returns expected list for a nested schema.
- Selecting source then path emits correct RefExpr shape.
- Autocomplete filters.

**Commit:** `feat(workflows): ref picker with schema-aware autocomplete`

---

## Task 10: `InputMappingField` + mode toggle

**Files:**
- Create: `Builder/InputMapping/InputMappingField.tsx`
- Create: `Builder/InputMapping/MappingModeToggle.tsx`
- Test: `__tests__/InputMappingField.test.tsx`

Props: `{ fieldName; fieldSchema; value?: MappingExpr; onChange(MappingExpr); refSources: RefSource[] }`.

UI: mode toggle (Literal | Input | Node | Env | Transform). Literal uses a small inline widget based on fieldSchema (see Task 15 hybrid renderer for a reusable atom). Input/Node/Env open RefPicker. Transform is Phase-3-optional; gate behind an "Advanced" disclosure per the design's mapping UI scope. Keep mapping UI allowed ops to `coalesce` + `concat` only.

Tests: toggle switches between literal/ref/transform; value shape correct per mode.

**Commit:** `feat(workflows): input mapping field with mode toggle`

---

## Task 11: Predicate Simple mode

**Files:**
- Create: `Builder/PredicateBuilder/SimplePredicate.tsx`
- Create: `Builder/PredicateBuilder/predicateTypes.ts` (shared helpers)
- Test: `__tests__/SimplePredicate.test.tsx`

Single clause: `{field: RefExpr; op; value}` →
- `op === 'eq' | 'neq' | 'contains' | 'not_contains' | 'exists' | 'not_exists'`.
- **LOCKED:** Phase 2 `FROZEN_OPS = {coalesce, concat, eq, in, exists, and, or, not}` — no `gt/gte/lt/lte`. Simple mode does NOT expose comparison ops.
- Type-aware op list via schema lookup on the selected field (boolean fields → only `eq`/`neq`; string → add `contains`; all → `exists`).
- Emits AST:
  - `==` → `{op: 'eq', left: ref, right: {literal: value}}`
  - `!=` → `{op: 'not', arg: {op: 'eq', left: ref, right: {literal: value}}}`
  - `contains` → `{op: 'in', args: [{literal: value}, ref]}` (confirm `in` arg order against `evaluator.py` during implementation; adjust if needed).
  - `not_contains` → `{op: 'not', arg: {op: 'in', ...}}`
  - `exists` → `{op: 'exists', args: [ref]}`
  - `not_exists` → `{op: 'not', arg: {op: 'exists', args: [ref]}}`

Completeness enforced: field + op + (value if op needs one).

**Commit:** `feat(workflows): simple predicate builder`

---

## Task 12: Predicate Advanced AST builder + mode switch

**Files:**
- Create: `Builder/PredicateBuilder/AdvancedAstBuilder.tsx`
- Create: `Builder/PredicateBuilder/index.tsx` (composes Simple + Advanced + mode toggle)
- Test: `__tests__/AdvancedAstBuilder.test.tsx`
- Test: `__tests__/PredicateBuilder.switch.test.tsx`

AdvancedAstBuilder: recursive tree editor. Each node:
- Leaf: SimplePredicate
- `and` / `or`: list of child predicates + "Add clause"
- `not`: single child predicate

Mode switch (in `index.tsx`):
- Simple → Advanced: wraps single clause into `{op: 'and', args: [clause]}` OR leaves as-is if already compound; "Advanced" is always safe.
- Advanced → Simple: allowed only if top-level is a single simple clause. Else warning modal with `[Stay in advanced] [Reset to simple]`.

**Commit:** `feat(workflows): advanced predicate AST builder + mode switch`

---

## Task 13: `StepSummaryRow`

**Files:**
- Create: `Builder/StepSummaryRow.tsx`
- Test: `__tests__/StepSummaryRow.test.tsx`

Props: `{ step: StepSpec; index; active; onSelect; errors?: ValidationError[] }`. Renders compact row: id, agent+version, trigger summary (human), on_failure icon, concurrency_group pill, timeout pill. Error badge if any client-side errors for this step.

`humanTriggerSummary(when)` helper translates AST → short string (best-effort; `eq(ref, lit)` → `if node.foo == "x"`; compound → `if (...)` truncated).

**Commit:** `feat(workflows): step summary row`

---

## Task 14: `StepList` with drag-to-reorder guard

**Files:**
- Create: `Builder/StepList.tsx`
- Test: `__tests__/StepList.test.tsx`

Props: `{ steps, selectedId, onSelect, onReorder(newSteps) }`. Renders list of `StepSummaryRow`. Drag handlers reject a drop that places a step before any step it references (dependency guard). Emits `onReorder` on valid drops.

**Commit:** `feat(workflows): step list with dependency-safe reorder`

---

## Task 15: Literal widget (hybrid schema renderer — reusable atom)

**Files:**
- Create: `frontend/src/components/Workflows/Shared/SchemaField.tsx`
- Test: `__tests__/SchemaField.test.tsx`

Reusable atom used by both `InputMappingField` (for literal mode) and `InputsForm` (Task 19). Renders one widget per schema node:
- `string` → text input
- `string` + `enum` → `<select>`
- `string` + `format: date-time` → `<input type="datetime-local">`
- `integer` / `number` → numeric input
- `boolean` → checkbox
- flat `object` (depth ≤ 2) → recursive render in fieldset
- Else: returns a `{complex: true}` flag so parent can fall back to JSON mode.

Shows `description`, `required` badge, `examples[0]` as placeholder.

**Commit:** `feat(workflows): reusable schema-driven field`

---

## Task 16: `StepDrawer`

**Files:**
- Create: `Builder/StepDrawer.tsx`
- Test: `__tests__/StepDrawer.test.tsx` (multiple test cases)

Right-side drawer. Props: `{ step, catalog, allSteps, onChange(step), onDelete, onClose }`.

Sections (all collapsible, sensible defaults expanded):
1. **Agent** — catalog-backed picker (uses existing `listAgents()` from `services/catalog.ts`); version select (default latest non-deprecated).
2. **Inputs** — one `InputMappingField` per contract input; RefSources built from `input` schema + all upstream step output schemas.
3. **Trigger** — `PredicateBuilder` (Task 12); RefSources same as Inputs.
4. **Failure** — radio (fail | continue | fallback). If fallback → step picker (excludes self; future steps allowed only if deps-subset — client validates).
5. **Execution** — optional timeout (capped at contract timeout), retry_on_override (checkbox list from contract's retry_on), concurrency_group (text input).

Emits `onChange(updatedStep)` on edit.

Tests: agent pick populates inputs; mapping mode switching; trigger simple+advanced round-trip; fallback picker excludes self + shows only valid targets; timeout cap enforced.

**Commit:** `feat(workflows): step drawer`

---

## Task 17: `WorkflowBuilderPage` (composition)

**Files:**
- Create: `Builder/WorkflowBuilderPage.tsx`
- Create: `Builder/useBuilderState.ts` (hook; draft DAG, validation)
- Test: `__tests__/WorkflowBuilderPage.test.tsx`

`useBuilderState` manages:
- `draftDag: WorkflowDag` (source of truth during editing)
- `baseVersion: number | null` (which version this draft was forked from)
- `clientErrors: ValidationError[]` computed live
- `setDraftDag`, `addStep(agent)`, `updateStep(id, patch)`, `removeStep(id)`, `reorderSteps(newOrder)`
- `dirty: boolean`

Page layout:
- `WorkflowHeader` (name, VersionSwitcher, Save as new version, Run)
- Left: `StepList` + "+ Add step" button
- Right: `StepDrawer` for selected step
- Bottom: `ValidationBanner`

Save flow:
1. Compute `dag` from draft.
2. Call `createVersion(workflowId, dag)`.
3. On success → refresh version list, select new version as editor source.
4. On `CompileError` → show in ValidationBanner with `path`-to-step mapping.

Run button opens `InputsForm` modal (Task 19) pre-filled from latest version's inputs_schema.

Tests: add/remove/reorder steps, save happy path, save 422 maps to banner, run button opens modal.

**Commit:** `feat(workflows): builder page (compose all primitives)`

---

## Task 18: Workflow list landing

**Files:**
- Create: `Builder/WorkflowListPage.tsx` (the default view at `/workflows` when no workflow selected)
- Test: `__tests__/WorkflowListPage.test.tsx`

Simple list + "Create workflow" button (opens a name/description modal). Click → navigates to `/workflows/:id`.

Update router: `/workflows` → `WorkflowListPage`, `/workflows/:id` → `WorkflowBuilderPage`.

**Commit:** `feat(workflows): workflow list page + create flow`

---

## Task 19: `InputsForm` (hybrid)

**Files:**
- Create: `Runs/InputsForm.tsx`
- Test: `__tests__/InputsForm.test.tsx`

Props: `{ schema; onSubmit(inputs); onCancel; persistKey?: string }`.

Behavior:
- Check if every top-level property in `schema` is "simple" (via `SchemaField`'s complex check). If yes → auto-render form; else → JSON textarea.
- Toggle `[Form view] [JSON view]` always shown.
- AJV validator compiled from schema; both modes run the same validator.
- `persistKey` → localStorage prefill.
- "More options" disclosure for `idempotency_key` text input.

Submit → calls `onSubmit(validatedInputs, { idempotency_key })`.

**Commit:** `feat(workflows): hybrid inputs form with JSON fallback`

---

## Task 20: Run trigger wiring (builder → run detail page)

**Files:**
- Modify: `Builder/WorkflowBuilderPage.tsx`
- Modify: `frontend/src/router.tsx` (add `/workflows/runs/:runId` route)

Run button opens `InputsForm` → on submit, `createRun(workflowId, { inputs, idempotency_key })` → navigate to `/workflows/runs/:runId`.

**Commit:** `feat(workflows): builder run trigger`

---

## Task 21: `StepStatusPanel`

**Files:**
- Create: `Runs/StepStatusPanel.tsx`
- Test: `__tests__/StepStatusPanel.test.tsx`

Props: `{ stepRuns: StepRunDetail[]; liveEvents: LiveEvent[] }`.

One card per step_run with status badge, attempt, duration, error, expandable output JSON. Reduces `liveEvents` into latest-per-step state on top of the initial `stepRuns`.

Statuses visualized (Tailwind `wr-*` tokens):
- `running` → amber pulse
- `success` → emerald
- `failed` → red + error message
- `skipped` → gray italic
- `cancelled` → slate

**Commit:** `feat(workflows): step status panel (live)`

---

## Task 22: `RunDetailPage` + SSE subscription

**Files:**
- Create: `Runs/RunDetailPage.tsx`
- Create: `Runs/useRunEvents.ts` (hook wrapping EventSource)
- Create: `Runs/EventsRawStream.tsx`
- Test: `__tests__/RunDetailPage.test.tsx` (uses a fake EventSource)
- Test: `__tests__/useRunEvents.test.ts`

`useRunEvents(runId)`:
- Calls `getRun(runId)` for initial state.
- Opens `subscribeEvents(runId)`.
- Accumulates events; derives `stepRuns` state (seeded by initial `getRun` result, updated per event).
- Closes the EventSource on terminal status or unmount.

`RunDetailPage`:
- Header: workflow name, run id, run status badge, Cancel button (disabled if terminal).
- Body: `StepStatusPanel`.
- Footer: `[Show events]` toggle → `EventsRawStream`.

Cancel button → `cancelRun(runId)`; disabled on terminal status or 409 errors.

**Commit:** `feat(workflows): run detail page with SSE subscription`

---

## Task 23: `WorkflowRunsPage`

**Files:**
- Create: `Runs/WorkflowRunsPage.tsx`
- Test: `__tests__/WorkflowRunsPage.test.tsx`

Lists runs across all workflows (or filter by `?workflow_id`). "New run" button prompts workflow + version pick → `InputsForm` → navigates to `RunDetailPage`.

*(If the backend doesn't currently list runs globally, scope this page to show only the logged-in session's recent runs via localStorage tracking. Document this as a Phase 6 follow-up. Don't add new backend endpoints.)*

**Commit:** `feat(workflows): runs list page`

---

## Task 24: Playwright scaffolding

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/tsconfig.json` (or extend main)
- Modify: `frontend/package.json` — add `test:e2e` script + devDeps (`@playwright/test`)
- Modify: `.gitignore` — ignore `playwright-report/`, `test-results/`

**Config essentials:**
- `testDir: './e2e'`
- `use: { baseURL: 'http://localhost:5173' }` (Vite default)
- `webServer`: start `vite` for frontend; document that backend must be running separately with `WORKFLOWS_ENABLED=true` (CI can compose a runner).
- `projects`: chromium only for Phase 3.

Run: `npx playwright install chromium` documented in README.

**Commit:** `test(workflows): playwright scaffolding`

---

## Task 25: E2E smoke test

**Files:**
- Create: `frontend/e2e/workflows.spec.ts`
- Create: `backend/src/workflows/runners/_stub_testing.py` (test-only, gated by env)

**Problem:** The E2E must NOT hit real LLM/network. Solution: a test-only env flag `WORKFLOW_RUNNERS_STUB=true` that swaps the `log_agent` runner with a deterministic stub at startup. Check `init_runners()` in `backend/src/workflows/runners/__init__.py` — add this env check there (additive, behind flag, defaults off).

**LOCKED:** Env-flag approach approved. Additive, behind flag, default off. Call out in PR as the second of the two allowed backend changes.

**Scenario:**
1. Playwright starts Vite + (externally running) backend with `WORKFLOWS_ENABLED=true WORKFLOW_RUNNERS_STUB=true`.
2. Visit `/workflows`.
3. Create workflow "Smoke".
4. Add step A (agent log_agent v1, literal input).
5. Add step B (agent log_agent v1, ref A's output).
6. Save → version 1 created.
7. Run → fill inputs → submit.
8. Assert step cards reach SUCCESS; run status SUCCEEDED.

**Commit:** `test(workflows): e2e smoke with stub runners`

---

## Task 26: Delete legacy placeholders + update imports

**Files:**
- Delete: `frontend/src/components/Platform/WorkflowBuilder/` (whole folder)
- Delete: `frontend/src/components/Platform/WorkflowRuns/` (whole folder)
- Modify: `frontend/src/router.tsx` — remove old imports
- Verify: `git grep "Platform/Workflow"` returns nothing

**Commit:** `chore(workflows): remove legacy placeholder components`

---

## Task 27: Non-impact snapshot + verification + PR

**Files:**
- Create: `frontend/src/components/Workflows/__tests__/phase3-non-impact.test.ts`

Test asserts `fs.existsSync('src/components/Investigation/') && <unchanged count>` OR — simpler — run `git diff main..HEAD --stat -- frontend/src/components/Investigation/ backend/` via subprocess-spawn in a Vitest test and assert zero output. If that's too awkward in Node test land, keep it in `backend/tests/test_phase3_non_impact.py` using the same pattern as `test_phase2_non_impact.py`.

**Run full test suites:**

```bash
cd frontend && npm run test -- --run
python3 -m pytest backend/tests/test_phase2_non_impact.py backend/tests/test_phase3_non_impact.py backend/tests/test_phase2_e2e.py -q
cd frontend && npm run test:e2e   # requires backend running with WORKFLOWS_ENABLED + WORKFLOW_RUNNERS_STUB
```

**PR:**
- Title: `feat(workflows): phase 3 — form-based workflow builder UI`
- Body mirrors Phase 2 PR structure: Summary / What's in / Design link / Exit criteria citations / Test plan checklist.

**Commit:** `test(workflows): phase 3 non-impact snapshot`
**Final commit:** `feat(workflows): phase 3 complete` (if any post-verification fixes; otherwise just push + PR).

---

## Exit criteria checklist (copy to PR body)

- [ ] Workflow created, version 1 saved, run executes, step cards go SUCCESS, run SUCCEEDED — end-to-end
- [ ] Version switcher + fork-on-edit works; Save always creates N+1
- [ ] Step drawer supports: agent pick (from catalog), input mapping (literal + ref picker), predicate simple + advanced with mode switch guard, failure policy (fail/continue/fallback with target picker), execution overrides (timeout cap, retry_on subset)
- [ ] Inputs form: supported-subset widgets + JSON fallback + AJV validation + localStorage prefill
- [ ] Flag OFF: nav hidden, `/workflows*` shows DisabledState with working Retry
- [ ] Vitest green; Playwright smoke green (with stub runners)
- [ ] Non-impact: `backend/` unchanged except the one documented stub-runner hook; `frontend/src/components/Investigation/` unchanged; legacy `Platform/WorkflowBuilder` + `Platform/WorkflowRuns` deleted
- [ ] Phase 1 + Phase 2 backend tests still green

## Open items — all RESOLVED

1. **`GET /workflows/:id/versions`** — does NOT exist in Phase 2. Phase 3 adds it as an additive route. Only backend change in Task 2.
2. **Predicate ops** — Phase 2 frozen set is `{coalesce, concat, eq, in, exists, and, or, not}`. No `gt/gte/lt/lte`. Simple mode exposes only `eq`, `neq`, `contains`, `not_contains`, `exists`, `not_exists`.
3. **Stub runner env flag** — `WORKFLOW_RUNNERS_STUB` in `runners/__init__.py` approved. Additive, behind flag, default off.

Two allowed backend touches in Phase 3 (both trivial, both behind existing flags): list-versions endpoint + stub-runners env.

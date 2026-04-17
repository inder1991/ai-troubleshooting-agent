# Workflow Go-Live Hardening Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all bugs, silent failures, validation gaps, accessibility issues, and test gaps to make the workflow feature production-ready.

**Architecture:** No new features. Unify status enum across the entire system, wire existing toast system into all workflow components, add API input validation with Pydantic, harden accessibility, deduplicate shared constants, and fill test coverage gaps.

**Tech Stack:** FastAPI, SQLite, React + TypeScript + Tailwind (existing), Vitest, MSW.

---

## Scope

**IN:** Status unification, bug fixes, silent-catch removal, API validation, accessibility, UX polish, test gaps.
**OUT:** Drag/drop canvas, scheduled/cron, import/export, RBAC, bulk operations, deep search.

## Pre-existing State

- Toast system exists at `frontend/src/components/Workflows/Shared/Toast.tsx` with `ToastProvider` + `useToast()` hook
- `ToastProvider` is already wrapped in `frontend/src/layouts/WorkflowsLayout.tsx`
- Toast API: `showToast({ type: 'success' | 'error' | 'info', message: string, action?: { label, onClick } })`
- `StepStatus` enum + `normalize_status()` already exist in `backend/src/workflows/event_schema.py`
- Redis logging already fixed in `investigation_store.py`
- QueueFull logging already fixed in `service.py`
- Page-level tests exist for WorkflowListPage, WorkflowBuilderPage, WorkflowRunsPage, RunDetailPage

## Status Split (current state — the problem)

Two separate status domains exist today:

| Domain | Values | Where |
|--------|--------|-------|
| Run status | `succeeded`, `failed`, `cancelled`, `pending`, `running`, `cancelling` | `workflow_runs` table, API, frontend `RunStatus` type |
| Step status | `success`, `failed`, `skipped`, `cancelled`, `pending`, `running` | `workflow_step_runs` table, `StepStatus` enum, frontend `StepRunStatus` type |

The executor returns uppercase `SUCCEEDED` for runs and `SUCCESS`/`COMPLETED` for steps. The service layer maps `SUCCEEDED` → `succeeded` at line 521. The `normalize_status()` maps `COMPLETED` → `success` for steps. This split is a persistent source of bugs (B1 was caused by exactly this).

**Task 0 unifies to one canonical enum using `success` (not `succeeded`) everywhere.**

---

## Task 0: Status Unification (Breaking Change)

**Files:**
- Modify: `backend/src/workflows/event_schema.py` (add `CANCELLING` to `StepStatus`, rename to just `Status`)
- Create: `backend/src/workflows/migrations/003_unify_status.sql`
- Modify: `backend/src/workflows/executor.py:709,731,733` (change `SUCCEEDED` → `SUCCESS`)
- Modify: `backend/src/workflows/service.py:67,521` (change `succeeded` → `success` in mapping and `_TERMINAL`)
- Modify: `backend/src/api/routes_workflows.py:189` (change `_TERMINAL_RUN_STATUSES`)
- Modify: `frontend/src/types/index.ts:2618-2632` (unify `RunStatus` and `StepRunStatus` into one `Status` type)
- Modify: All frontend components using `succeeded` → `success`
- Modify: All backend tests using `succeeded` → `success`
- Modify: All frontend tests using `succeeded` → `success`

**What to do:**

### Step 1: Backend — Canonical enum

In `backend/src/workflows/event_schema.py`, rename `StepStatus` to `Status` and add `CANCELLING`:

```python
class Status(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CANCELLING = "cancelling"
    SKIPPED = "skipped"
```

Keep `StepStatus` as an alias for backward compatibility during migration:
```python
StepStatus = Status  # alias — remove after all imports updated
```

Update `_STATUS_ALIASES` to include `SUCCEEDED`:
```python
_STATUS_ALIASES: dict[str, Status] = {
    "COMPLETED": Status.SUCCESS,
    "SUCCESS": Status.SUCCESS,
    "SUCCEEDED": Status.SUCCESS,  # legacy run-level alias
    "FAILED": Status.FAILED,
    "PENDING": Status.PENDING,
    "RUNNING": Status.RUNNING,
    "SKIPPED": Status.SKIPPED,
    "CANCELLED": Status.CANCELLED,
    "CANCELLING": Status.CANCELLING,
}
```

### Step 2: DB migration

Create `backend/src/workflows/migrations/003_unify_status.sql`:

```sql
UPDATE workflow_runs SET status = 'success' WHERE status = 'succeeded';
UPDATE workflow_step_runs SET status = 'success' WHERE status = 'succeeded';
```

No CHECK constraint yet — SQLite ALTER TABLE doesn't support adding CHECK constraints to existing tables. The enum validation happens at the application layer.

### Step 3: Executor — change SUCCEEDED to SUCCESS

In `backend/src/workflows/executor.py`, change all occurrences:
- Line 709: `status = "SUCCEEDED"` → `status = "SUCCESS"`
- Line 712: comment `successful fallback...we're SUCCEEDED` → update comment
- Line 731: `status = "SUCCEEDED"` → `status = "SUCCESS"`
- Line 733: `if status == "SUCCEEDED":` → `if status == "SUCCESS":`

### Step 4: Service layer — update mappings

In `backend/src/workflows/service.py`:
- Line 67: `_TERMINAL = {"succeeded", "failed", "cancelled"}` → `_TERMINAL = {"success", "failed", "cancelled"}`
- Line 520-524: Remove the mapping dict entirely. The executor now returns `SUCCESS` which matches the DB value `success` directly. Replace:
```python
final_status = {
    "SUCCEEDED": "succeeded",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
}.get(result.status, "failed")
```
With:
```python
final_status = normalize_status(result.status).value
```

Import `normalize_status` from `event_schema` if not already imported.

### Step 5: Routes — update terminal set

In `backend/src/api/routes_workflows.py`:
- Line 189: `_TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}` → `_TERMINAL_RUN_STATUSES = {"success", "failed", "cancelled"}`

### Step 6: Frontend — unify types

In `frontend/src/types/index.ts`, replace both `RunStatus` and `StepRunStatus` with one type:

```typescript
export type Status =
  | 'pending'
  | 'running'
  | 'cancelling'
  | 'cancelled'
  | 'success'
  | 'failed'
  | 'skipped';

// Aliases for backward compatibility during migration
export type RunStatus = Status;
export type StepRunStatus = Status;
```

### Step 7: Frontend — update all `succeeded` references

Search and replace across `frontend/src/components/Workflows/`:
- All `succeeded` → `success` in STATUS_CLASSES maps, filter chips, terminal sets, test assertions
- Files: `WorkflowListPage.tsx`, `WorkflowRunsPage.tsx`, `RunDetailPage.tsx`, `StepStatusPanel.tsx`, `RunFilterBar.tsx`, `useRunEvents.ts`
- Tests: all `__tests__/` files under Workflows

In `useRunEvents.ts` line 72, change:
```typescript
parsed.type === 'run.completed' ? 'succeeded'
```
to:
```typescript
parsed.type === 'run.completed' ? 'success'
```

### Step 8: Backend tests — update all `succeeded` references

Files with `succeeded` in backend tests (update to `success`):
- `test_phase6_non_impact.py`: lines 100, 101, 108, 135, 136, 137, 150, 164
- `test_phase6_repository.py`: lines 92, 173, 244
- `test_phase6_service.py`: lines 217, 218, 219
- `test_phase6_routes.py`: line 159
- `test_workflow_repository.py`: lines 114, 117, 131, 139
- `test_workflows_run_path.py`: lines 102, 128
- `test_runs_cancel.py`: lines 135, 140
- `test_phase2_e2e.py`: lines 127, 177
- `test_runs_sse.py`: line 106
- `test_executor_*.py` files: change `assert result.status == "SUCCEEDED"` → `assert result.status == "SUCCESS"`

### Step 9: Run tests

```bash
cd backend && python3 -m pytest tests/test_phase6_repository.py tests/test_phase6_service.py tests/test_phase6_routes.py tests/test_phase6_non_impact.py tests/test_workflow_repository.py -v
cd frontend && npx vitest run src/components/Workflows
```

### Step 10: Commit

```bash
git commit -m "refactor(workflows): unify status enum — 'succeeded' → 'success' everywhere"
```

---

## Task 1: API Input Validation with Pydantic (H1 + H2)

**Files:**
- Modify: `backend/src/api/routes_workflows.py:360-398`
- Test: `backend/tests/test_phase6_routes.py`

**What to do:**

1. Replace manual query params with Pydantic model using `Depends`:

```python
from pydantic import BaseModel, conint
from typing import Literal, Optional

class ListRunsParams(BaseModel):
    status: str | None = None
    workflow_id: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    sort: Literal["started_at", "duration"] = "started_at"
    order: Literal["asc", "desc"] = "desc"
    limit: conint(ge=1, le=200) = 50
    offset: conint(ge=0) = 0

_VALID_STATUSES = {"pending", "running", "success", "failed", "cancelled", "cancelling"}
```

2. In both `list_runs` and `list_workflow_runs`, accept params via `Depends`:

```python
@router.get("/runs", dependencies=[Depends(require_flag)])
async def list_runs(
    params: ListRunsParams = Depends(),
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    statuses = None
    if params.status:
        statuses = [s.strip() for s in params.status.split(",")]
        invalid = set(statuses) - _VALID_STATUSES
        if invalid:
            raise HTTPException(status_code=400, detail=f"invalid status: {', '.join(sorted(invalid))}")
    return await svc.list_runs(
        workflow_id=params.workflow_id, statuses=statuses,
        from_date=params.from_date, to_date=params.to_date,
        sort=params.sort, order=params.order,
        limit=params.limit, offset=params.offset,
    )
```

3. Add tests:

```python
def test_list_runs_invalid_status_returns_400(client):
    r = client.get("/api/v4/runs?status=bogus")
    assert r.status_code == 400
    assert "invalid status" in r.json()["detail"]

def test_list_runs_mixed_valid_invalid_status_returns_400(client):
    r = client.get("/api/v4/runs?status=running,bogus")
    assert r.status_code == 400

def test_list_runs_valid_statuses(client):
    r = client.get("/api/v4/runs?status=running,failed")
    assert r.status_code == 200

def test_list_runs_invalid_sort_returns_422(client):
    r = client.get("/api/v4/runs?sort=nonexistent")
    assert r.status_code == 422  # Pydantic validation

def test_list_runs_invalid_order_returns_422(client):
    r = client.get("/api/v4/runs?order=sideways")
    assert r.status_code == 422

def test_list_runs_negative_offset_returns_422(client):
    r = client.get("/api/v4/runs?offset=-5")
    assert r.status_code == 422

def test_list_runs_limit_over_200_returns_422(client):
    r = client.get("/api/v4/runs?limit=999")
    assert r.status_code == 422

def test_delete_workflow_with_running_run_returns_409(client, seed):
    # seed a workflow with a running run
    r = client.delete(f"/api/v4/workflows/{seed['wf_id']}")
    assert r.status_code == 409
```

**Run:** `cd backend && python3 -m pytest tests/test_phase6_routes.py -v`

**Commit:** `fix(workflows): validate list params with Pydantic — status, sort, order, limit, offset`

---

## Task 2: Deduplicate STATUS_CLASSES + Shared Helpers (M1)

**Files:**
- Create: `frontend/src/components/Workflows/Shared/statusConstants.ts`
- Modify: `frontend/src/components/Workflows/Runs/WorkflowRunsPage.tsx`
- Modify: `frontend/src/components/Workflows/Runs/RunDetailPage.tsx`
- Modify: `frontend/src/components/Workflows/Runs/StepStatusPanel.tsx`
- Modify: `frontend/src/components/Workflows/Builder/WorkflowListPage.tsx`

**What to do:**

1. Create shared constants file:

```typescript
import type { Status } from '../../../types';

export const STATUS_BADGE_CLASSES: Record<Status, string> = {
  running: 'bg-amber-500 animate-pulse',
  pending: 'bg-neutral-500',
  cancelling: 'bg-slate-400',
  cancelled: 'bg-slate-500',
  success: 'bg-emerald-500',
  failed: 'bg-red-500',
  skipped: 'bg-neutral-400',
};

export const STATUS_DOT_CLASSES: Record<Status, string> = {
  running: 'bg-amber-500',
  pending: 'bg-neutral-500',
  cancelling: 'bg-slate-400',
  cancelled: 'bg-slate-500',
  success: 'bg-emerald-500',
  failed: 'bg-red-500',
  skipped: 'bg-neutral-400',
};

export const TERMINAL_STATUSES: ReadonlySet<Status> = new Set([
  'success', 'failed', 'cancelled',
]);

export function isTerminal(status: Status): boolean {
  return TERMINAL_STATUSES.has(status);
}
```

2. Replace local `STATUS_CLASSES` / `STATUS_DOT_CLASSES` in all 4 files with imports.

3. Replace inline `new Set(['success', 'failed', 'cancelled'])` in `RunDetailPage.tsx` with `isTerminal()`.

4. Replace inline terminal checks in `useRunEvents.ts` with `isTerminal()`.

**Run:** `cd frontend && npx vitest run`

**Commit:** `refactor(workflows): deduplicate status constants and add isTerminal() helper`

---

## Task 3: Wire Toast + Error Normalization — Replace Silent Catches (H5)

**Files:**
- Create: `frontend/src/components/Workflows/Shared/errorUtils.ts`
- Modify: `frontend/src/components/Workflows/Runs/WorkflowRunsPage.tsx`
- Modify: `frontend/src/components/Workflows/Runs/RunDetailPage.tsx`
- Modify: `frontend/src/components/Workflows/Builder/WorkflowListPage.tsx`
- Modify: `frontend/src/components/Workflows/Builder/StepDrawer.tsx`
- Modify: `frontend/src/components/Workflows/Builder/StepList.tsx`

**What to do:**

### Step 1: Create error normalization helper

```typescript
// frontend/src/components/Workflows/Shared/errorUtils.ts

interface ApiErrorBody {
  detail?: string | { message?: string };
}

export function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Response) {
    return fallback; // can't read body synchronously
  }
  if (err && typeof err === 'object' && 'status' in err) {
    const apiErr = err as { status: number; body?: ApiErrorBody };
    if (apiErr.status === 409) {
      const detail = apiErr.body?.detail;
      if (typeof detail === 'string') return detail;
      if (detail && typeof detail === 'object' && detail.message) return detail.message;
      return 'Operation conflicts with current state';
    }
  }
  if (err instanceof Error) return err.message;
  return fallback;
}
```

Check how the workflow API service functions throw errors (look at `callWorkflowsApi` in `frontend/src/services/workflows.ts`) to ensure the error shape matches what we're parsing. Adjust accordingly.

### Step 2: Wire toast into each component

Add `import { useToast } from '../Shared/Toast';` and `import { getErrorMessage } from '../Shared/errorUtils';` to each file. Call `const { showToast } = useToast();` in each component.

**WorkflowRunsPage.tsx — replace silent catches:**
```
Line 77:  .catch(() => {})
  → .catch((e) => { if (!cancelled) showToast({ type: 'error', message: getErrorMessage(e, 'Failed to load runs') }); })

Line 126: catch { // ignore }
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to load workflows') }); }

Line 141: catch { // ignore }
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to load versions') }); }

Line 157: catch { // ignore }
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to load version') }); }

Line 177: catch { // ignore }
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to create run') }); }
```

**RunDetailPage.tsx — replace silent catches:**
```
Line 29: catch {} (initial run fetch)
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to load run') }); }

Line 66: catch {} (version fetch for graph)
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to load workflow graph') }); }

Line 124-125: catch { // silently fail } (rerun)
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to rerun workflow') }); }

Line 148-149: catch { // silently fail } (rerun with changes)
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to load rerun data') }); }

Line 269-270: catch { // silently fail } (submit rerun)
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to start rerun') }); }
```

Leave line 79 (pre-fetch for rerun data) and line 141 (inner version schema fetch) as silent — they are non-critical fallbacks.

**WorkflowListPage.tsx — add error AND success toasts:**
```
Rename: catch → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to rename workflow') }); }
  Success: showToast({ type: 'success', message: 'Workflow renamed' });

Duplicate: catch → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to duplicate workflow') }); }
  Success: showToast({ type: 'success', message: `Duplicated as "${newName}"` });

Delete: catch → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to delete workflow') }); }
  Success: showToast({ type: 'success', message: 'Workflow deleted' });
```

**StepDrawer.tsx:**
```
Line 99: .catch(() => {})
  → .catch((e) => showToast({ type: 'error', message: getErrorMessage(e, 'Failed to load agent details') }))
```

**StepList.tsx:**
```
Line 129: catch {}
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to reorder steps') }); }

Line 152: catch {}
  → catch (e) { showToast({ type: 'error', message: getErrorMessage(e, 'Failed to move step') }); }
```

**What NOT to change (safe to leave silent):**
- `InputsForm.tsx` — localStorage read/write and JSON parse fallbacks
- `recentRuns.ts` — localStorage operations
- `VersionSwitcher.tsx` — localStorage fallback
- `InputMappingField.tsx` — JSON parse in UI preview

**Run:** `cd frontend && npx vitest run`

**Commit:** `fix(workflows): replace silent catches with toast notifications and error normalization`

---

## Task 4: ConfirmDeleteDialog Accessibility (M2)

**Files:**
- Modify: `frontend/src/components/Workflows/Shared/ConfirmDeleteDialog.tsx`
- Modify: `frontend/src/components/Workflows/Shared/__tests__/ConfirmDeleteDialog.test.tsx`

**What to do:**

1. Add `role="alertdialog"`, `aria-modal="true"`, `aria-labelledby="delete-dialog-title"`.
2. Add `id="delete-dialog-title"` to the `<h2>`.
3. Add Escape key handler on the overlay div.
4. Add focus trap using a panel ref.
5. Add explicit initial focus via `useEffect` + `inputRef`:

```tsx
const inputRef = useRef<HTMLInputElement>(null);
const panelRef = useRef<HTMLDivElement>(null);

useEffect(() => {
  inputRef.current?.focus();
}, []);

useEffect(() => {
  const panel = panelRef.current;
  if (!panel) return;
  const focusable = () => panel.querySelectorAll<HTMLElement>(
    'input:not([disabled]), button:not([disabled])'
  );
  function handleTab(e: KeyboardEvent) {
    if (e.key !== 'Tab') return;
    const els = focusable();
    const first = els[0];
    const last = els[els.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last?.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first?.focus();
    }
  }
  panel.addEventListener('keydown', handleTab);
  return () => panel.removeEventListener('keydown', handleTab);
}, []);
```

6. Add tests:

```typescript
test('pressing Escape calls onCancel', async () => {
  const onCancel = vi.fn();
  render(<ConfirmDeleteDialog workflowName="test" onConfirm={vi.fn()} onCancel={onCancel} />);
  await userEvent.keyboard('{Escape}');
  expect(onCancel).toHaveBeenCalled();
});

test('has role="alertdialog" and aria-modal', () => {
  render(<ConfirmDeleteDialog workflowName="test" onConfirm={vi.fn()} onCancel={vi.fn()} />);
  expect(screen.getByRole('alertdialog')).toHaveAttribute('aria-modal', 'true');
});

test('input receives initial focus', () => {
  render(<ConfirmDeleteDialog workflowName="test" onConfirm={vi.fn()} onCancel={vi.fn()} />);
  expect(document.activeElement?.tagName).toBe('INPUT');
});
```

**Run:** `cd frontend && npx vitest run src/components/Workflows/Shared/__tests__/ConfirmDeleteDialog.test.tsx`

**Commit:** `fix(workflows): add focus trap, Escape key, ARIA attributes, and initial focus to ConfirmDeleteDialog`

---

## Task 5: Three-Dot Menu Close on Outside Click (M3)

**Files:**
- Modify: `frontend/src/components/Workflows/Builder/WorkflowListPage.tsx`

**What to do:**

Use a ref instead of `data-` attribute (safer, avoids portal edge case):

```tsx
const menuRef = useRef<HTMLDivElement>(null);

useEffect(() => {
  if (!menuOpenId) return;
  function handleClick(e: MouseEvent) {
    if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
      setMenuOpenId(null);
    }
  }
  document.addEventListener('mousedown', handleClick);
  return () => document.removeEventListener('mousedown', handleClick);
}, [menuOpenId]);
```

Wrap the three-dot button + dropdown in `<div ref={menuRef}>`.

Add Escape handler on the dropdown:
```tsx
onKeyDown={(e) => { if (e.key === 'Escape') setMenuOpenId(null); }}
```

**Run:** `cd frontend && npx vitest run src/components/Workflows/Builder/__tests__/WorkflowListPage.test.tsx`

**Commit:** `fix(workflows): close three-dot menu on outside click and Escape key`

---

## Task 6: StepStatusPanel Keyboard Accessibility (M4)

**Files:**
- Modify: `frontend/src/components/Workflows/Runs/StepStatusPanel.tsx:89`
- Modify: `frontend/src/components/Workflows/Runs/__tests__/StepStatusPanel.test.tsx`

**What to do:**

Make the clickable StepCard div accessible:

```tsx
<div
  data-testid={`step-card-${step.step_id}`}
  className={...}
  onClick={() => onCardClick?.(step.step_id)}
  onKeyDown={(e) => {
    if ((e.key === 'Enter' || e.key === ' ') && onCardClick) {
      e.preventDefault();
      onCardClick(step.step_id);
    }
  }}
  role={onCardClick ? 'button' : undefined}
  tabIndex={onCardClick ? 0 : undefined}
>
```

Add test:

```typescript
test('step card responds to Enter key when clickable', async () => {
  // render with onCardClick handler
  // tab to step card, press Enter
  // assert onCardClick called with step_id
});
```

**Run:** `cd frontend && npx vitest run src/components/Workflows/Runs/__tests__/StepStatusPanel.test.tsx`

**Commit:** `fix(workflows): add keyboard accessibility to StepStatusPanel cards`

---

## Task 7: Missing Loading States in New-Run Wizard (M7)

**Files:**
- Modify: `frontend/src/components/Workflows/Runs/WorkflowRunsPage.tsx`

**What to do:**

1. Add loading state tracking:

```tsx
const [loadingWorkflows, setLoadingWorkflows] = useState(false);
const [loadingVersions, setLoadingVersions] = useState(false);
```

2. Wrap `handleNewRun` and `handleWorkflowChange` with loading states:

```tsx
const handleNewRun = useCallback(async () => {
  setNewRunStep('select');
  setLoadingWorkflows(true);
  try { ... } catch (e) { ... } finally { setLoadingWorkflows(false); }
}, [...]);

const handleWorkflowChange = useCallback(async (wfId: string) => {
  ...
  setLoadingVersions(true);
  try { ... } catch (e) { ... } finally { setLoadingVersions(false); }
}, [...]);
```

3. Show loading indicators and disable selects while loading:

```tsx
<select disabled={loadingWorkflows} ...>

{loadingWorkflows && <div className="text-xs text-wr-text-muted">Loading workflows...</div>}

<select disabled={loadingVersions} ...>

{loadingVersions && <div className="text-xs text-wr-text-muted">Loading versions...</div>}
```

4. Disable the "New run" button during submission:

```tsx
<button disabled={submitting} onClick={handleNewRun} ...>
```

**Run:** `cd frontend && npx vitest run src/components/Workflows/Runs/__tests__/WorkflowRunsPage.test.tsx`

**Commit:** `fix(workflows): add loading states and disable controls in new-run wizard`

---

## Task 8: InvestigationExecutor Tests

**Files:**
- Create: `backend/tests/test_investigation_executor.py`

**What to do:**

Read `backend/src/workflows/investigation_executor.py` to understand constructor signature and dependencies. Write unit tests mocking WorkflowExecutor and the store.

Required tests:

```python
@pytest.mark.asyncio
async def test_run_step_appends_to_dag():
    """run_step should add the step to the virtual DAG."""

@pytest.mark.asyncio
async def test_run_step_emits_running_then_final_status():
    """run_step should emit at least two events: running and success/failed."""

@pytest.mark.asyncio
async def test_run_step_returns_typed_step_result():
    """StepResult should have step_id, status, output, duration_ms etc."""

@pytest.mark.asyncio
async def test_run_step_failure_marks_step_failed():
    """If WorkflowExecutor raises, step should be marked failed."""

@pytest.mark.asyncio
async def test_run_steps_sequential():
    """run_steps should execute steps sequentially and return all results."""

@pytest.mark.asyncio
async def test_dag_persisted_to_store():
    """After run_step, DAG should be saved to the store."""

@pytest.mark.asyncio
async def test_sequence_numbers_monotonic():
    """Each event should have an incrementing sequence number."""

@pytest.mark.asyncio
async def test_step_id_convention():
    """Step IDs should follow round-{N}-{agent_name} convention."""

@pytest.mark.asyncio
async def test_cancel_marks_running_step_cancelled():
    """cancel() should mark any in-progress step as cancelled."""

@pytest.mark.asyncio
async def test_normalize_status_completed_maps_to_success():
    """COMPLETED from WorkflowExecutor should map to Status.SUCCESS."""

@pytest.mark.asyncio
async def test_duplicate_step_id_does_not_create_duplicate_dag_entry():
    """Running a step with the same step_id twice should not produce duplicate entries."""
    # This is the idempotency test — verify the executor handles
    # re-execution of a step that already completed (e.g., from retry/replay)
```

**Run:** `cd backend && python3 -m pytest tests/test_investigation_executor.py -v`

**Commit:** `test(workflows): add InvestigationExecutor unit tests including idempotency`

---

## Task 9: Route-Level Validation and Edge Case Tests

**Files:**
- Modify: `backend/tests/test_phase6_routes.py`

**What to do:**

Add tests that exercise the Pydantic validation from Task 1:

```python
def test_list_runs_invalid_status_returns_400(client):
    r = client.get("/api/v4/runs?status=bogus")
    assert r.status_code == 400
    assert "invalid status" in r.json()["detail"]

def test_list_runs_mixed_valid_invalid_status_returns_400(client):
    r = client.get("/api/v4/runs?status=running,bogus")
    assert r.status_code == 400

def test_list_runs_valid_statuses(client):
    r = client.get("/api/v4/runs?status=running,failed")
    assert r.status_code == 200

def test_list_runs_invalid_sort_returns_422(client):
    r = client.get("/api/v4/runs?sort=nonexistent")
    assert r.status_code == 422

def test_list_runs_invalid_order_returns_422(client):
    r = client.get("/api/v4/runs?order=sideways")
    assert r.status_code == 422

def test_list_runs_negative_offset_returns_422(client):
    r = client.get("/api/v4/runs?offset=-5")
    assert r.status_code == 422

def test_list_runs_limit_over_200_returns_422(client):
    r = client.get("/api/v4/runs?limit=999")
    assert r.status_code == 422

def test_delete_workflow_with_running_run_returns_409(client, seed):
    # create workflow + version + run with status='running'
    r = client.delete(f"/api/v4/workflows/{seed_wf_id}")
    assert r.status_code == 409
```

**Run:** `cd backend && python3 -m pytest tests/test_phase6_routes.py -v`

**Commit:** `test(workflows): add route-level validation and 409 conflict tests`

---

## Task 10: Frontend Page-Level Test Gaps

**Files:**
- Modify: `frontend/src/components/Workflows/Builder/__tests__/WorkflowListPage.test.tsx`
- Modify: `frontend/src/components/Workflows/Runs/__tests__/RunDetailPage.test.tsx`
- Modify: `frontend/src/components/Workflows/Runs/__tests__/WorkflowRunsPage.test.tsx`

**What to do:**

### WorkflowListPage — three-dot menu tests:

Add MSW handlers for PATCH, POST duplicate, DELETE. Then:

```typescript
test('three-dot menu: rename workflow', async () => {
  // Open three-dot menu, click Rename
  // Type new name, press Enter
  // Verify PATCH /api/v4/workflows/:id called
});

test('three-dot menu: duplicate workflow', async () => {
  // Open three-dot menu, click Duplicate
  // Verify POST /api/v4/workflows/:id/duplicate called
  // Verify navigation to new workflow
});

test('three-dot menu: delete with confirm dialog', async () => {
  // Open three-dot menu, click Delete
  // ConfirmDeleteDialog appears
  // Type workflow name, click Delete
  // Verify DELETE /api/v4/workflows/:id called
});

test('delete with active runs shows error toast', async () => {
  // Mock DELETE to return 409
  // Verify error toast
});
```

### RunDetailPage — rerun tests:

```typescript
test('rerun button disabled for running run', async () => {
  // Render with running run
  // Both rerun buttons disabled
});

test('rerun creates new run and navigates', async () => {
  // Render with terminal run (success)
  // Mock getRerunData and createRun
  // Click Rerun
  // Verify navigation to new run
});
```

### WorkflowRunsPage — filter tests:

```typescript
test('clicking status chip updates URL and refetches', async () => {
  // Click "failed" chip
  // Verify URL has ?status=failed
});

test('pagination next button works', async () => {
  // Mock total > 50
  // Click Next
  // Verify offset in API call
});
```

### Golden path E2E-style test (in Vitest + MSW):

```typescript
test('golden path: list → create → run → view → rerun → delete', async () => {
  // 1. Render WorkflowListPage, verify workflows listed
  // 2. Create new workflow
  // 3. Navigate to runs page, start a new run
  // 4. Navigate to run detail
  // 5. Rerun
  // 6. Navigate back to list, delete workflow
  // This catches wiring issues across layers
});
```

**Run:** `cd frontend && npx vitest run src/components/Workflows`

**Commit:** `test(workflows): add three-dot menu, rerun, filter, and golden path tests`

---

## Task 11: Missing Component Tests (EventsRawStream, MappingModeToggle)

**Files:**
- Create: `frontend/src/components/Workflows/Runs/__tests__/EventsRawStream.test.tsx`
- Create: `frontend/src/components/Workflows/Builder/InputMapping/__tests__/MappingModeToggle.test.tsx`

**What to do:**

Read each component first to understand props and behavior.

### EventsRawStream tests:

```typescript
test('renders "No events yet" when events array is empty');
test('renders event entries with type and timestamp');
test('shows event data when available');
```

### MappingModeToggle tests:

```typescript
test('renders toggle with current mode');
test('clicking toggle calls onChange with new mode');
test('displays correct label for each mode');
```

**Run:** `cd frontend && npx vitest run src/components/Workflows/Runs/__tests__/EventsRawStream.test.tsx src/components/Workflows/Builder/InputMapping/__tests__/MappingModeToggle.test.tsx`

**Commit:** `test(workflows): add EventsRawStream and MappingModeToggle component tests`

---

## Task 12: SSE Parse Error Logging

**Files:**
- Modify: `frontend/src/components/Workflows/Runs/useRunEvents.ts:82`

**What to do:**

Replace bare `catch { // Ignore parse errors }` with logging that includes raw event data:

```typescript
} catch (err) {
  console.warn('[useRunEvents] Failed to parse SSE event', {
    error: err,
    rawData: evt.data,
  });
}
```

**Run:** `cd frontend && npx vitest run`

**Commit:** `fix(workflows): log SSE parse errors with raw event data for debugging`

---

## Task 13: Move _find_run_by_key to Repository (H4)

**Files:**
- Modify: `backend/src/workflows/repository.py`
- Modify: `backend/src/workflows/service.py`

**What to do:**

1. Add to `repository.py`:

```python
async def find_run_by_idempotency_key(
    self, workflow_version_id: str, key: str
) -> dict[str, Any] | None:
    async with self._conn() as db:
        async with db.execute(
            "SELECT * FROM workflow_runs WHERE workflow_version_id = ? "
            "AND idempotency_key = ?",
            (workflow_version_id, key),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
```

2. In `service.py`, replace `_find_run_by_key` with:

```python
existing = await self._repo.find_run_by_idempotency_key(
    workflow_version_id=..., key=idempotency_key
)
```

3. Remove the `import aiosqlite` and the `_find_run_by_key` method from service.py.

**Run:** `cd backend && python3 -m pytest tests/test_phase6_service.py tests/test_phase6_routes.py -v`

**Commit:** `refactor(workflows): move _find_run_by_key into repository layer`

---

## Task 14: Final Full Test Suite Run

**Files:** None (verification only)

**What to do:**

1. Run full backend test suite:
```bash
cd backend && python3 -m pytest tests/ -v --ignore=tests/test_cluster_agent.py
```

2. Run full frontend test suite:
```bash
cd frontend && npx vitest run
```

3. Verify no regressions. If any test fails that is NOT pre-existing, fix it before proceeding.

**Commit:** No commit unless fixes are needed.

---

## Execution Order & Dependencies

```
Task 0 (status unification) ──────────────── MUST BE FIRST (everything depends on it)

Task 1 (API validation) ──────────────────┐
Task 12 (SSE parse logging) ──────────────┤── independent, can run in parallel
Task 13 (move _find_run_by_key) ──────────┘

Task 2 (deduplicate STATUS_CLASSES) ──────── depends on Task 0 (uses unified status values)

Task 3 (wire toasts + error normalization) ── depends on Task 2 (shared imports)

Task 4 (ConfirmDeleteDialog a11y) ────────┐
Task 5 (menu outside click) ─────────────┤── independent, can run in parallel
Task 6 (StepStatusPanel keyboard) ────────┤
Task 7 (wizard loading states) ───────────┘

Task 8 (InvestigationExecutor tests) ─────┐
Task 9 (route validation tests) ── dep 1  ┤── test tasks
Task 10 (page-level test gaps) ───────────┤
Task 11 (component test gaps) ────────────┘

Task 14 (final suite run) ───────────────── depends on ALL
```

## Exit Criteria

- [ ] Single `Status` enum used everywhere — no `succeeded` anywhere in codebase
- [ ] DB migration converts existing `succeeded` rows to `success`
- [ ] `normalize_status()` at executor boundary only — no mapping inside system
- [ ] API rejects invalid status, sort, order with 400/422 (Pydantic validation)
- [ ] API rejects negative offset, limit > 200 with 422
- [ ] 409 tested at route level for delete with active runs
- [ ] STATUS_CLASSES deduplicated into one shared file with `isTerminal()` helper
- [ ] Every user-facing action handler shows error toast with backend signal extraction
- [ ] Success toasts on duplicate, delete, rename
- [ ] ConfirmDeleteDialog: focus trap, Escape key, aria-modal, initial focus
- [ ] Three-dot menu closes on outside click (via ref) and Escape
- [ ] StepStatusPanel cards keyboard accessible (role="button", Enter/Space)
- [ ] New-run wizard shows loading states, disables controls during fetch
- [ ] InvestigationExecutor has unit tests including idempotency/duplicate protection
- [ ] Route-level tests cover validation, bounds, 409
- [ ] Page tests cover three-dot menu, rerun, filters, pagination
- [ ] Golden path test: list → create → run → rerun → delete
- [ ] EventsRawStream and MappingModeToggle have component tests
- [ ] SSE parse errors logged with raw event data
- [ ] _find_run_by_key moved to repository (no raw SQL in service)
- [ ] Full test suite green (no new regressions)

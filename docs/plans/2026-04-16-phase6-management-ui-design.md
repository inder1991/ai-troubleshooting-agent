# Phase 6: Management UI — Design

**Goal:** Make workflows usable at scale — lifecycle management (delete, rename, duplicate, version rollback/diff) and run management (filtering, rerun, scoped run lists).

**Architecture:** Backend API additions (7 new endpoints + filter params) + frontend component enhancements. No new infrastructure, no schema migrations for new tables. One migration for indexes + soft-delete column.

**Tech Stack:** FastAPI, SQLite (existing), React + TypeScript + Tailwind (existing), Vitest.

---

## 1. Non-goals

- No RBAC / multi-user auth (Phase 7+)
- No scheduled/cron execution (Phase 7+)
- No workflow import/export (deferred)
- No search across step outputs (requires indexing infrastructure)
- No archive/unarchive (hard delete + run retention is sufficient)
- No War Room UI changes
- No InvestigationExecutor/WorkflowExecutor changes

## 2. Run Snapshot Guarantee (Non-negotiable)

**Invariant:** Each run must be viewable and rerunnable without depending on the workflow table.

Current schema: `workflow_runs.workflow_version_id` FK → `workflow_versions.id` which stores `dag_json` + `compiled_json`. Steps stored in `workflow_step_runs` with full input/output.

**Delete strategy:** When a workflow is deleted, we delete the `workflows` row but **keep `workflow_versions` rows intact** (orphaned but preserved). This means:
- Runs still resolve their version FK → DAG replay works
- Step runs with inputs/outputs remain → full audit trail
- Rerun reconstructs execution from the version record, not the workflow
- Phase 4 DAG view continues to work for historical runs

**Implementation:** `DELETE FROM workflows WHERE id = ?` only. No cascade to versions or runs. SQLite FK constraints (RESTRICT, no CASCADE) enforce this naturally — we just need to SET the workflow_id reference to handle the orphan.

**Migration:** Add `deleted_at TEXT` column to `workflows` table. "Delete" sets this timestamp. Query filters exclude deleted workflows. Versions and runs are unaffected.

This is cleaner than true hard delete because:
- No FK gymnastics
- `GET /workflows/{id}/versions` still works for orphan runs
- Reversible if needed (clear `deleted_at`)

## 3. Backend Endpoints

### New Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `DELETE` | `/workflows/{id}` | Soft delete (set `deleted_at`). Fails if any runs are actively executing. |
| `PATCH` | `/workflows/{id}` | Update `name` and/or `description` |
| `POST` | `/workflows/{id}/duplicate` | Deep copy workflow + latest version → new workflow at v1 |
| `POST` | `/workflows/{id}/versions/{v}/rollback` | Create new version identical to v (append-only) |
| `GET` | `/workflows/{id}/runs` | Scoped run list with filters |
| `POST` | `/runs/{id}/rerun` | Create new run from run's stored version + inputs |

### Modified Endpoints

| Endpoint | Change |
|----------|--------|
| `GET /runs` | Add query params: `status`, `from`, `to`, `workflow_id`, `sort`, `order`, `limit`, `offset` |
| `GET /workflows` | Filter out `deleted_at IS NOT NULL` by default |

### Response Shape Consistency

`GET /runs` and `GET /workflows/{id}/runs` return identical response shape:

```json
{
  "runs": [{ "id", "workflow_version_id", "status", "started_at", "ended_at", "inputs_json" }],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

## 4. Delete Semantics

- Sets `deleted_at` timestamp on workflows row (soft delete)
- Versions and runs are **unaffected** — no FK changes, no orphaning
- `GET /workflows` excludes deleted workflows by default
- `GET /workflows/{id}` returns 404 for deleted workflows
- Runs of deleted workflows remain fully accessible via `GET /runs/{id}`
- Phase 4 DAG view works because version FK is intact
- **Guard:** Returns 409 Conflict if any runs have status `running` or `pending`
- **Idempotent:** Deleting an already-deleted workflow returns 204 (no error)
- **UI:** Confirmation dialog — user types workflow name to confirm

## 5. Duplicate Semantics

**What gets copied:**
- Workflow `name` → `"{name} (copy)"`. If collision: `"{name} (copy 2)"`, etc.
- Workflow `description` → copied as-is
- Latest version's `dag_json` + `compiled_json` → new version v1
- Latest version's `inputs_schema` (embedded in dag_json) → copied

**What gets reset:**
- `id` → new UUID
- `version` → 1
- `created_at` → now
- `created_by` → current user (or null)
- `is_active` → 1

**What is NOT copied:**
- Non-latest versions (only latest)
- Runs (new workflow starts clean)
- `deleted_at` (always null)

## 6. Version Rollback

- `POST /workflows/{id}/versions/{v}/rollback`
- Creates a **new** version with `version = max(existing) + 1`
- Copies `dag_json` and `compiled_json` from version `v`
- Sets `is_active = 1` on the new version
- Does NOT delete or mutate any existing version (append-only history)
- Returns `{ version: <new_version_number>, id: <new_version_id> }`

## 7. Run Filtering

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | string | all | Comma-separated: `running,failed,succeeded,cancelled,pending` |
| `from` | ISO 8601 | none | Inclusive start date |
| `to` | ISO 8601 | none | Inclusive end date |
| `workflow_id` | UUID | none | Filter by workflow (global `/runs` only) |
| `sort` | string | `created_at` | `created_at` or `duration` |
| `order` | string | `desc` | `desc` or `asc` |
| `limit` | int | 50 | Max 200 |
| `offset` | int | 0 | For pagination |

### Required DB Indexes (Migration)

```sql
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status_created ON workflow_runs(status, started_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_created ON workflow_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflows_deleted ON workflows(deleted_at);
```

## 8. Rerun

### Same Inputs (one-click)

- `POST /runs/{id}/rerun`
- Reads original run's `workflow_version_id` and `inputs_json`
- Creates a new run against that **same version** with **same inputs**
- Does NOT look up the workflow — uses the run's stored version FK directly
- Returns `{ run_id, workflow_id, workflow_version_id }`
- UI navigates to the new run's detail page

### With Changes (frontend-only)

- "Rerun with changes" button on RunDetailPage
- Navigates to InputsForm pre-filled with the original run's inputs
- Uses the original run's workflow version (not latest)
- No new backend endpoint — uses existing `POST /workflows/{id}/runs` with pre-filled data

## 9. Frontend Components

### WorkflowListPage Enhancements

- **Three-dot menu** per row: Rename, Duplicate, Delete
- **Inline rename:** Click name → editable input → save on blur/Enter, cancel on Escape
- **Duplicate:** Immediate action → toast "Created {name} (copy)" → navigate to new workflow
- **Delete:** Opens ConfirmDeleteDialog
- **Last run status badge** per workflow (aggregated from latest run)
- **Last run timestamp** per workflow
- **Empty state:** "Create your first workflow" with CTA button

### WorkflowBuilderPage Enhancements

- **Version selector** dropdown in header: shows all versions, current version highlighted
- **Version diff** button: opens side-by-side comparison modal between selected version and current
- **Rollback button** on non-latest versions: "Restore this version" → creates new version → navigates to it
- Active version badge

### WorkflowRunsPage Enhancements

- **RunFilterBar** component: status chips (toggle on/off), date range inputs, sort dropdown
- **URL query params** for all filters (shareable/bookmarkable)
- **Pagination** controls (previous/next, showing count)
- **Per-workflow context:** When accessed from workflow, auto-filters by workflow_id
- **Empty state:** "No runs yet — trigger one from the workflow builder"

### RunDetailPage Enhancements

- **"Rerun" button** in header (same inputs, one click)
- **"Rerun with changes" button** → navigates to InputsForm pre-filled
- Both buttons disabled for currently running/pending runs

### New Components

```
Workflows/
  Shared/
    ConfirmDeleteDialog.tsx   — type-name-to-confirm pattern
    VersionDiff.tsx           — side-by-side step comparison
  Runs/
    RunFilterBar.tsx           — status chips + date range + sort
```

## 10. Version Diff View

Side-by-side comparison of two workflow versions:

- **Matching by `step_id`** as primary key (not position)
- **Added steps** (in new, not in old): green highlight
- **Removed steps** (in old, not in new): red highlight
- **Modified steps** (same step_id, different config): amber highlight with changed fields listed
- **Unchanged steps:** dimmed/collapsed
- **Shallow field comparison:** compare agent, agent_version, inputs (top-level keys), when, on_failure, timeout. No deep JSON diff.
- Computed client-side from two version DAGs — no backend diff endpoint

## 11. Database Migration

```sql
-- 002_management_ui.sql
ALTER TABLE workflows ADD COLUMN deleted_at TEXT;

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status_created
  ON workflow_runs(status, started_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_created
  ON workflow_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflows_deleted
  ON workflows(deleted_at);
```

## 12. What Changes vs What Stays

| Component | Status |
|---|---|
| `routes_workflows.py` | **MODIFY** — add 6 endpoints + filter params |
| `repository.py` | **MODIFY** — add delete, duplicate, rollback, filter queries |
| `service.py` | **MODIFY** — add business logic for new operations |
| Migration `002_management_ui.sql` | **CREATE** — soft delete column + indexes |
| `WorkflowListPage.tsx` | **MODIFY** — menu, rename, duplicate, delete, last-run badge |
| `WorkflowBuilderPage.tsx` | **MODIFY** — version selector, diff, rollback |
| `WorkflowRunsPage.tsx` | **MODIFY** — filter bar, pagination, URL params |
| `RunDetailPage.tsx` | **MODIFY** — rerun buttons |
| `ConfirmDeleteDialog.tsx` | **CREATE** |
| `VersionDiff.tsx` | **CREATE** |
| `RunFilterBar.tsx` | **CREATE** |
| WorkflowExecutor | **UNTOUCHED** |
| InvestigationExecutor | **UNTOUCHED** |
| War Room UI | **UNTOUCHED** |
| Phase 4 DAG view | **UNTOUCHED** |

## 13. Testing Strategy

1. **Backend endpoint tests** — each new endpoint: happy path, edge cases (delete with running runs → 409, duplicate name collision, rollback nonexistent version → 404, filter combinations)
2. **Repository tests** — SQL queries return correct results with filters, pagination, soft delete filtering
3. **Frontend component tests** — ConfirmDeleteDialog (name matching, submit/cancel), RunFilterBar (state management, URL sync), VersionDiff (added/removed/modified detection)
4. **Integration** — full lifecycle: create → duplicate → rename → add version → rollback → run → filter → rerun → delete → verify orphan runs accessible
5. **Non-impact** — existing workflow/run/executor tests green

## 14. Exit Criteria

- [ ] Soft delete workflow (set deleted_at, guard against running runs, idempotent)
- [ ] Delete confirmation dialog (type name to confirm)
- [ ] Rename workflow (inline edit, PATCH endpoint)
- [ ] Duplicate workflow (copy latest version, handle name collisions)
- [ ] Version selector dropdown with active badge
- [ ] Version diff (side-by-side, match by step_id, shallow compare)
- [ ] Rollback version (append-only, creates new version from old)
- [ ] Run filtering (status, date range, sort, pagination)
- [ ] Per-workflow run list (GET /workflows/{id}/runs)
- [ ] Filter state in URL query params (shareable links)
- [ ] Rerun same inputs (one-click, reads from run snapshot)
- [ ] Rerun with changes (pre-filled InputsForm)
- [ ] Last run status/time on workflow list
- [ ] Empty states for no-workflows and no-runs
- [ ] DB indexes for filter performance
- [ ] Run snapshot integrity: deleted workflows don't break run pages or DAG view
- [ ] Response shape consistency between /runs and /workflows/{id}/runs
- [ ] WorkflowExecutor, InvestigationExecutor, War Room UI untouched
- [ ] All tests green, no regressions

## 15. Deferred

- RBAC / multi-user auth (Phase 7+)
- Scheduled/cron workflow execution
- Workflow import/export (JSON bundle)
- Deep search across step outputs (requires indexing)
- Archive/unarchive (soft delete is sufficient)
- Bulk operations (multi-select delete, multi-run export)

# Fix Pipeline Reliability — Design

**Goal:** Replace the fragile background-task fix generation with a production-grade asyncio job queue that provides bounded concurrency, automatic retry, resource management, and structured error reporting.

**Context:** The current fix generation pipeline crashes with `Errno 24 (Too many open files)` because it does full git clones in untracked temp directories, has no concurrency limits, no retry logic, and no temp dir cleanup. Errors cascade into SQLite connection failures and HTTP connection resets, taking down the entire server.

---

## 1. Root Cause Analysis

Six failure modes identified:

| # | Problem | Impact |
|---|---------|--------|
| 1 | Full git clone (`shallow=False`) on large repos | Exhausts file descriptors |
| 2 | Temp dirs never cleaned up on failure/crash | Disk leak, FD leak on retry |
| 3 | No concurrency control — multiple fix requests can run simultaneously | FD exhaustion multiplied, race conditions |
| 4 | No retry logic — clone timeout or LLM failure = instant crash | Transient failures become permanent |
| 5 | Fix background tasks untracked — can't cancel on session cleanup | Orphaned tasks consuming resources |
| 6 | Generic error messages — frontend shows "fix generation failed" | No actionable information for user |

---

## 2. Architecture: Asyncio Job Queue

### Job Queue Core

New module `backend/src/utils/fix_job_queue.py`:

```
FixJobQueue (singleton)
├── _workers: bounded asyncio worker pool (max 2 concurrent jobs)
├── _queue: asyncio.Queue (max 10 pending)
├── _jobs: dict[job_id → FixJob]  (in-memory registry)
└── _temp_dirs: set[str]  (tracked for cleanup)
```

**FixJob** tracks lifecycle:

| Field | Type | Description |
|-------|------|-------------|
| id | str (UUID) | Unique job identifier |
| session_id | str | Owning session |
| status | enum | queued, running, retrying, completed, failed, cancelled |
| created_at | datetime | When submitted |
| started_at | datetime | When worker picked it up |
| completed_at | datetime | When finished (any terminal state) |
| attempt | int | Current attempt number |
| max_attempts | int | Default 3 |
| error_message | str | Last error (if any) |
| current_stage | str | cloning, generating, verifying, staging, awaiting_review |

**Behavior:**
- `submit(session_id, state, emitter, guidance)` → returns `job_id`, enqueues job. HTTP 429 if queue full. HTTP 409 if session already has active job.
- `cancel(job_id)` → cancels running asyncio task, cleans up temp dir
- `get_status(job_id)` → returns current job state
- Workers pull from queue, execute fix generation, handle retry internally
- On server shutdown: cancel all running jobs, purge all temp dirs

**Bounded concurrency:** Max 2 workers = at most 2 clones + 2 sets of subprocess calls. Caps FD usage well within OS limits.

---

## 3. Resource Management

### Shallow Clone + Sparse Checkout

- Default: `git clone --depth 1` (shallow)
- After clone: `git sparse-checkout set <paths>` using only files identified by diagnostic evidence (`target_files` from `_collect_fix_targets`)
- Fallback: if sparse checkout fails, use full shallow clone
- Reduces a 10,000-file repo to ~5-20 files on disk

### Temp Directory Lifecycle

Each job gets a temp dir tracked in `FixJobQueue._temp_dirs`:

1. **Job completion** (success or failure) — always cleanup in `finally`
2. **Job cancellation** — cleanup immediately
3. **Queue shutdown** — purge all tracked dirs
4. **Startup orphan purge** — on `FixJobQueue.__init__`, scan `/tmp/fix_*` and delete leftover dirs from previous crashes

### FD Budget

With max 2 workers + shallow sparse checkout: ~50 FDs per job (clone files + git internals + subprocess pipes + SQLite). Well within macOS default 256 limit.

---

## 4. Retry & Error Handling

### Retry Strategy — 3 attempts with exponential backoff

| Stage | Retryable? | Backoff | Notes |
|-------|-----------|---------|-------|
| Clone | Yes | 2s, 4s, 8s | Network timeout, auth failure |
| LLM call (generate_fix) | Yes | 3s, 6s, 12s | API timeout, rate limit |
| LLM call (verify) | Yes | 3s, 6s | After 2 failures, skip verification and continue |
| Validation (syntax/lint) | No | — | Self-correction already exists. Proceed with warning if still fails |
| Git staging (branch/commit) | No | — | Local operation. Fatal if it fails |
| GitHub PR creation | Yes | 2s, 4s | Network/rate limit. 401/403 = fatal (bad token) |

### Fatal (Non-Retryable) Errors

- No repo URL → fail immediately with clear message
- No target files found → fail immediately
- Path traversal detected → fail immediately
- Session no longer exists → cancel job

### Structured Error Events to Frontend

```python
{
    "stage": "cloning",
    "attempt": 2,
    "max_attempts": 3,
    "error": "Clone timeout after 120s",
    "retrying": True,
    "suggestion": "Check GitHub token and repo access"
}
```

Frontend shows: "Cloning failed (attempt 2/3) — retrying in 4s..." instead of generic "Fix generation failed".

---

## 5. Concurrency Control & API Changes

### Route Changes (`routes_v4.py`)

Current:
```
POST /fix/generate → background_tasks.add_task(supervisor.start_fix_generation)
```

New:
```
POST /fix/generate → fix_job_queue.submit(...) → {job_id, status: "queued"}
GET  /fix/status   → enhanced with job queue info (position, attempt, stage)
DELETE /fix/{job_id} → cancel a running/queued job
```

### Concurrency Guards

- Queue rejects duplicate submissions for same `session_id` (HTTP 409)
- Job queue is the single source of truth for "is fix running?" — replaces `fix_result.fix_status` checks
- Session cleanup cancels any active job via `fix_job_queue.cancel()`

### Supervisor Changes

- Core logic extracted into `_execute_fix_generation` called by queue worker
- Supervisor no longer manages temp dirs or retries — queue handles both
- Human-in-the-loop approval wait stays in supervisor (session-specific state)

---

## 6. Files Changed

| File | Action | Description |
|------|--------|-------------|
| `backend/src/utils/fix_job_queue.py` | **CREATE** | FixJobQueue singleton, FixJob model, worker pool, retry logic, temp dir tracking, orphan purge |
| `backend/src/utils/repo_manager.py` | **MODIFY** | Add sparse checkout support, retry-friendly clone method |
| `backend/src/agents/supervisor.py` | **MODIFY** | Extract `_execute_fix_generation`, remove temp dir management and retry responsibility |
| `backend/src/api/routes_v4.py` | **MODIFY** | Route through job queue, add cancel endpoint, enhance status endpoint, session cleanup integration |
| `backend/src/agents/agent3/fix_generator.py` | **MODIFY** | Raise typed exceptions instead of generic, structured error context |
| `frontend/src/components/Investigation/FixPipelinePanel.tsx` | **MODIFY** | Show retry progress, queue position, stage-specific error messages |
| `frontend/src/services/api.ts` | **MODIFY** | Add `cancelFix()` API call, update `generateFix` to return `job_id` |

## What Does NOT Change

- Campaign orchestrator — uses same queue (one job per repo)
- Code agent verification — called by supervisor as before
- Validators, stagers — unchanged
- WebSocket event structure — same `TaskEvent`, just richer `details`
- Human-in-the-loop approval flow — stays in supervisor

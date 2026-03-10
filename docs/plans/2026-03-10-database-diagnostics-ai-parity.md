# Database Diagnostics AI Parity — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the database diagnostics module from a heuristic monitoring dashboard into a full AI-powered investigation platform with session integration, LLM-powered agents, chat, War Room UI, dossier generation, and safety-hardened remediation.

**Architecture:** Extend V4Session to support `database_diagnostics` as a first-class capability with two investigation modes (standalone and contextual/app-linked). Replace heuristic agents with LLM-powered agents using a tool-first pattern (Haiku for extraction, Opus for synthesis). All remediation follows Plan->Verify->Approve->Execute with immutable plans and JWT-signed approvals.

**Tech Stack:** FastAPI, LangGraph (StateGraph), asyncpg, Anthropic SDK (Haiku/Sonnet/Opus), React + TypeScript + Tailwind, Framer Motion, TanStack Query

**Design Doc:** `docs/plans/2026-03-10-database-diagnostics-ai-parity-design.md`

---

## Phase 1: Foundation — Evidence Store & Extended Models

### Task 1: Evidence Artifacts Table

**Files:**
- Create: `backend/src/database/evidence_store.py`
- Test: `backend/tests/test_evidence_store.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_evidence_store.py
import pytest
from src.database.evidence_store import EvidenceStore


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    return EvidenceStore(db_path)


def test_create_and_get_artifact(store):
    artifact = store.create(
        session_id="S-1",
        evidence_id="e-9001",
        source_agent="query_analyst",
        artifact_type="explain_plan",
        summary_json={"rows_estimated": 12000000, "scan_type": "Seq Scan"},
        full_content='{"Plan": {"Node Type": "Seq Scan", "Rows": 12000000}}',
        preview="Seq Scan on orders (rows=12M)",
    )
    assert artifact["artifact_id"].startswith("art-")
    assert artifact["source_agent"] == "query_analyst"

    fetched = store.get(artifact["artifact_id"])
    assert fetched is not None
    assert fetched["evidence_id"] == "e-9001"
    assert fetched["preview"] == "Seq Scan on orders (rows=12M)"


def test_list_by_session(store):
    store.create(session_id="S-1", evidence_id="e-1", source_agent="query_analyst",
                 artifact_type="pg_stat", summary_json={}, full_content="raw1", preview="p1")
    store.create(session_id="S-1", evidence_id="e-2", source_agent="health_analyst",
                 artifact_type="conn_pool", summary_json={}, full_content="raw2", preview="p2")
    store.create(session_id="S-2", evidence_id="e-3", source_agent="query_analyst",
                 artifact_type="pg_stat", summary_json={}, full_content="raw3", preview="p3")

    results = store.list_by_session("S-1")
    assert len(results) == 2


def test_get_nonexistent_returns_none(store):
    assert store.get("art-does-not-exist") is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_evidence_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.database.evidence_store'`

**Step 3: Write minimal implementation**

```python
# backend/src/database/evidence_store.py
"""Evidence artifact storage for database diagnostic sessions.

Stores large tool outputs (EXPLAIN plans, pg_stat dumps) outside
LLM context. Agents receive compact summaries; full content is
retrievable by artifact_id for UI preview and audit.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional


class EvidenceStore:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence_artifacts (
                    artifact_id   TEXT PRIMARY KEY,
                    session_id    TEXT NOT NULL,
                    evidence_id   TEXT NOT NULL,
                    source_agent  TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    summary_json  TEXT NOT NULL,
                    full_content  TEXT NOT NULL,
                    preview       TEXT,
                    timestamp     TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_evidence_session
                ON evidence_artifacts(session_id)
            """)

    def create(
        self,
        session_id: str,
        evidence_id: str,
        source_agent: str,
        artifact_type: str,
        summary_json: dict,
        full_content: str,
        preview: Optional[str] = None,
    ) -> dict:
        artifact_id = f"art-{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        row = {
            "artifact_id": artifact_id,
            "session_id": session_id,
            "evidence_id": evidence_id,
            "source_agent": source_agent,
            "artifact_type": artifact_type,
            "summary_json": json.dumps(summary_json),
            "full_content": full_content,
            "preview": preview,
            "timestamp": timestamp,
        }
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO evidence_artifacts
                   (artifact_id, session_id, evidence_id, source_agent,
                    artifact_type, summary_json, full_content, preview, timestamp)
                   VALUES (:artifact_id, :session_id, :evidence_id, :source_agent,
                           :artifact_type, :summary_json, :full_content, :preview, :timestamp)""",
                row,
            )
        row["summary_json"] = summary_json
        return row

    def get(self, artifact_id: str) -> Optional[dict]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM evidence_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["summary_json"] = json.loads(result["summary_json"])
        return result

    def list_by_session(self, session_id: str) -> list[dict]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM evidence_artifacts WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r["summary_json"] = json.loads(r["summary_json"])
            results.append(r)
        return results
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_evidence_store.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add backend/src/database/evidence_store.py backend/tests/test_evidence_store.py
git commit -m "feat(db): add EvidenceStore for diagnostic artifact persistence"
```

---

### Task 2: Extended Finding & Plan Pydantic Models

**Files:**
- Modify: `backend/src/database/models.py`
- Test: `backend/tests/test_db_models.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_db_models.py
import pytest
from src.database.models import DBFindingV2, RemediationPlanV2, EvidenceSnippet, PlanStep


def test_finding_v2_with_evidence():
    snippet = EvidenceSnippet(
        id="e-9001",
        summary="pg_stat_statements: total_time=1.47E6ms calls=820",
        artifact_id="art-9001",
    )
    finding = DBFindingV2(
        finding_id="f-0001",
        agent="query_analyst",
        category="slow_query",
        title="High p95 latency for SQL sha:0xabc",
        severity="high",
        confidence_raw=0.86,
        confidence_calibrated=0.78,
        detail="Query scanning 12M rows",
        evidence_ids=["e-9001"],
        evidence_snippets=[snippet],
        affected_entities={"database": "orders_db", "tables": ["orders"]},
        recommendation="Add covering index",
        remediation_available=True,
        remediation_plan_id="p-77",
        rule_check="index_suggested: explain.rows_estimated > 100000",
        meta={"sql_sha": "0xabc", "agent_version": "query_analyst-v2"},
    )
    assert finding.confidence_calibrated == 0.78
    assert finding.evidence_snippets[0].artifact_id == "art-9001"


def test_plan_v2_with_steps():
    step = PlanStep(
        step_id="s1",
        type="create_index",
        description="Create index on replica",
        command="CREATE INDEX CONCURRENTLY idx_orders_user ON orders (user_id);",
        run_target="replica1",
        estimated_time_minutes=8,
    )
    plan = RemediationPlanV2(
        plan_id="p-77",
        profile_id="prof-1",
        created_by="query_analyst",
        summary="Create index to reduce seq scans",
        scope={"type": "schema_change", "database": "orders_db"},
        steps=[step],
        prechecks=[{"id": "p1", "type": "replica_available", "required": True}],
        required_approvals=[{"role": "dba", "min_count": 1}],
        policy_tags=["safe-index", "no-downtime"],
        estimated_risk="low",
        immutable_hash="sha256:abc123",
    )
    assert plan.steps[0].run_target == "replica1"
    assert plan.estimated_risk == "low"
    assert plan.status == "created"


def test_finding_v2_rejects_invalid_severity():
    with pytest.raises(Exception):
        DBFindingV2(
            finding_id="f-bad",
            agent="test",
            category="slow_query",
            title="Bad",
            severity="mega_critical",  # Invalid
            confidence_raw=0.5,
            detail="test",
        )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_db_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'DBFindingV2'`

**Step 3: Write minimal implementation**

Add to bottom of `backend/src/database/models.py`:

```python
# --- V2 Models for AI-Powered Database Diagnostics ---

class EvidenceSnippet(BaseModel):
    id: str
    summary: str
    artifact_id: str


class DBFindingV2(BaseModel):
    finding_id: str
    agent: str
    category: Literal[
        "slow_query", "lock", "replication", "connections",
        "storage", "schema", "index_candidate", "memory",
        "configuration", "deadlock",
    ]
    title: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence_raw: float
    confidence_calibrated: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    detail: str
    evidence_ids: list[str] = []
    evidence_snippets: list[EvidenceSnippet] = []
    affected_entities: dict = {}
    recommendation: str = ""
    remediation_available: bool = False
    remediation_plan_id: Optional[str] = None
    rule_check: str = ""
    meta: dict = {}


class PlanStep(BaseModel):
    step_id: str
    type: str
    description: str
    command: str
    run_target: str
    estimated_time_minutes: Optional[int] = None
    checks: list[dict] = []


class RemediationPlanV2(BaseModel):
    plan_id: str
    profile_id: str
    created_by: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    summary: str
    scope: dict = {}
    steps: list[PlanStep] = []
    prechecks: list[dict] = []
    required_approvals: list[dict] = []
    approval_status: str = "pending"
    approvals: list[dict] = []
    immutable_hash: str = ""
    policy_tags: list[str] = []
    estimated_risk: Literal["low", "medium", "high", "critical"] = "medium"
    status: str = "created"
    finding_id: Optional[str] = None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_db_models.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add backend/src/database/models.py backend/tests/test_db_models.py
git commit -m "feat(db): add V2 finding and remediation plan models with evidence"
```

---

### Task 3: Job Queue with Concurrency Limiter

**Files:**
- Create: `backend/src/database/job_queue.py`
- Test: `backend/tests/test_job_queue.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_job_queue.py
import asyncio
import pytest
from src.database.job_queue import JobQueue


@pytest.fixture
def queue():
    return JobQueue(max_concurrent_per_profile=1)


@pytest.mark.asyncio
async def test_enqueue_and_execute(queue):
    results = []

    async def work():
        results.append("done")
        return {"status": "ok"}

    job_id = await queue.enqueue("prof-1", "run_explain", work)
    assert job_id.startswith("J-")

    # Wait for completion
    result = await queue.wait_for(job_id, timeout=5.0)
    assert result["status"] == "ok"
    assert results == ["done"]


@pytest.mark.asyncio
async def test_concurrency_limit(queue):
    """Only 1 job per profile runs at a time."""
    order = []

    async def slow_work(label):
        order.append(f"{label}-start")
        await asyncio.sleep(0.1)
        order.append(f"{label}-end")
        return label

    j1 = await queue.enqueue("prof-1", "tool-a", lambda: slow_work("A"))
    j2 = await queue.enqueue("prof-1", "tool-b", lambda: slow_work("B"))

    await queue.wait_for(j2, timeout=5.0)

    # B should not start until A finishes
    assert order.index("A-start") < order.index("A-end")
    assert order.index("A-end") <= order.index("B-start")


@pytest.mark.asyncio
async def test_get_status(queue):
    async def work():
        await asyncio.sleep(0.05)
        return "result"

    job_id = await queue.enqueue("prof-1", "tool", work)
    status = queue.get_status(job_id)
    assert status["status"] in ("pending", "running")

    await queue.wait_for(job_id, timeout=5.0)
    status = queue.get_status(job_id)
    assert status["status"] == "completed"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_job_queue.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/database/job_queue.py
"""Async job queue with per-profile concurrency limiting.

Heavy diagnostic operations (EXPLAIN ANALYZE, full pg_stat scans)
are enqueued here instead of running inline. Each profile gets at
most max_concurrent_per_profile simultaneous jobs.
"""

import asyncio
import uuid
from typing import Any, Callable, Coroutine, Optional


class JobQueue:
    def __init__(self, max_concurrent_per_profile: int = 1):
        self._max = max_concurrent_per_profile
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._jobs: dict[str, dict] = {}
        self._events: dict[str, asyncio.Event] = {}

    def _get_semaphore(self, profile_id: str) -> asyncio.Semaphore:
        if profile_id not in self._semaphores:
            self._semaphores[profile_id] = asyncio.Semaphore(self._max)
        return self._semaphores[profile_id]

    async def enqueue(
        self,
        profile_id: str,
        tool_name: str,
        coro_factory: Callable[[], Coroutine],
    ) -> str:
        job_id = f"J-{uuid.uuid4().hex[:8]}"
        event = asyncio.Event()
        self._events[job_id] = event
        self._jobs[job_id] = {
            "job_id": job_id,
            "profile_id": profile_id,
            "tool": tool_name,
            "status": "pending",
            "result": None,
            "error": None,
        }

        asyncio.create_task(self._run(job_id, profile_id, coro_factory, event))
        return job_id

    async def _run(
        self,
        job_id: str,
        profile_id: str,
        coro_factory: Callable[[], Coroutine],
        event: asyncio.Event,
    ) -> None:
        sem = self._get_semaphore(profile_id)
        async with sem:
            self._jobs[job_id]["status"] = "running"
            try:
                result = await coro_factory()
                self._jobs[job_id]["result"] = result
                self._jobs[job_id]["status"] = "completed"
            except Exception as e:
                self._jobs[job_id]["error"] = str(e)
                self._jobs[job_id]["status"] = "failed"
            finally:
                event.set()

    async def wait_for(self, job_id: str, timeout: float = 30.0) -> Any:
        event = self._events.get(job_id)
        if event is None:
            raise ValueError(f"Unknown job: {job_id}")
        await asyncio.wait_for(event.wait(), timeout=timeout)
        job = self._jobs[job_id]
        if job["status"] == "failed":
            raise RuntimeError(job["error"])
        return job["result"]

    def get_status(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            return {"status": "unknown", "job_id": job_id}
        return {
            "job_id": job["job_id"],
            "profile_id": job["profile_id"],
            "tool": job["tool"],
            "status": job["status"],
        }

    def queue_length(self, profile_id: str) -> int:
        return sum(
            1 for j in self._jobs.values()
            if j["profile_id"] == profile_id and j["status"] == "pending"
        )

    def active_count(self, profile_id: str) -> int:
        return sum(
            1 for j in self._jobs.values()
            if j["profile_id"] == profile_id and j["status"] == "running"
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_job_queue.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add backend/src/database/job_queue.py backend/tests/test_job_queue.py
git commit -m "feat(db): add async job queue with per-profile concurrency limiter"
```

---

## Phase 2: Session Integration

### Task 4: Add `database_diagnostics` to CapabilityType

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add the new capability**

In `frontend/src/types/index.ts`, find the `CapabilityType` union (around line 551) and add `'database_diagnostics'`:

```typescript
export type CapabilityType =
  | 'troubleshoot_app'
  | 'pr_review'
  | 'github_issue_fix'
  | 'cluster_diagnostics'
  | 'network_troubleshooting'
  | 'database_diagnostics';
```

Add the form type below the existing form types (around line 606):

```typescript
export interface DatabaseDiagnosticsForm {
  capability: 'database_diagnostics';
  profile_id: string;
  time_window: '15m' | '1h' | '6h' | '24h';
  focus: ('queries' | 'connections' | 'replication' | 'storage' | 'schema')[];
  table_filter?: string[];
  database_type: 'postgres';
  sampling_mode: 'light' | 'standard' | 'deep';
  include_explain_plans: boolean;
  parent_session_id?: string;
  context_source?: 'user_selected' | 'auto_triggered';
}
```

Add to the `CapabilityFormData` union:

```typescript
export type CapabilityFormData =
  | TroubleshootAppForm
  | PRReviewForm
  | GithubIssueFixForm
  | ClusterDiagnosticsForm
  | NetworkTroubleshootingForm
  | DatabaseDiagnosticsForm;
```

**Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add database_diagnostics to CapabilityType and form types"
```

---

### Task 5: Database Diagnostics Form Fields Component

**Files:**
- Create: `frontend/src/components/ActionCenter/forms/DatabaseDiagnosticsFields.tsx`

**Step 1: Write the component**

```typescript
// frontend/src/components/ActionCenter/forms/DatabaseDiagnosticsFields.tsx
import React, { useState, useEffect } from 'react';
import type { DatabaseDiagnosticsForm } from '../../../types';
import { fetchDBProfiles } from '../../../services/api';

interface DatabaseDiagnosticsFieldsProps {
  data: DatabaseDiagnosticsForm;
  onChange: (data: DatabaseDiagnosticsForm) => void;
}

interface DBProfile {
  id: string;
  name: string;
  engine: string;
  host: string;
  port: number;
  database: string;
}

const FOCUS_OPTIONS = [
  { value: 'queries' as const, label: 'Queries', icon: 'query_stats' },
  { value: 'connections' as const, label: 'Connections', icon: 'cable' },
  { value: 'replication' as const, label: 'Replication', icon: 'sync' },
  { value: 'storage' as const, label: 'Storage', icon: 'storage' },
  { value: 'schema' as const, label: 'Schema', icon: 'account_tree' },
];

const inputClass =
  'w-full rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-gray-600 bg-[#0f2023] border border-[#224349] focus:border-[#07b6d5] focus:ring-1 focus:ring-[#07b6d5]/30 outline-none transition-colors';

const DatabaseDiagnosticsFields: React.FC<DatabaseDiagnosticsFieldsProps> = ({
  data,
  onChange,
}) => {
  const [profiles, setProfiles] = useState<DBProfile[]>([]);

  useEffect(() => {
    fetchDBProfiles().then(setProfiles).catch(() => {});
  }, []);

  const toggleFocus = (area: DatabaseDiagnosticsForm['focus'][number]) => {
    const current = data.focus || [];
    const next = current.includes(area)
      ? current.filter((f) => f !== area)
      : [...current, area];
    onChange({ ...data, focus: next });
  };

  return (
    <div className="space-y-5">
      {/* Database Profile */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Database Profile *
        </label>
        <select
          className={inputClass}
          value={data.profile_id || ''}
          onChange={(e) => onChange({ ...data, profile_id: e.target.value })}
          required
        >
          <option value="">Select a database profile...</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.engine} — {p.host}:{p.port}/{p.database})
            </option>
          ))}
        </select>
      </div>

      {/* Time Window */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Time Window
        </label>
        <select
          className={inputClass}
          value={data.time_window}
          onChange={(e) =>
            onChange({ ...data, time_window: e.target.value as DatabaseDiagnosticsForm['time_window'] })
          }
        >
          <option value="15m">Last 15 minutes</option>
          <option value="1h">Last 1 hour</option>
          <option value="6h">Last 6 hours</option>
          <option value="24h">Last 24 hours</option>
        </select>
      </div>

      {/* Focus Areas */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Focus Areas
        </label>
        <div className="flex flex-wrap gap-2">
          {FOCUS_OPTIONS.map((opt) => {
            const active = data.focus?.includes(opt.value);
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => toggleFocus(opt.value)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  active
                    ? 'bg-duck-accent/20 border-duck-accent text-duck-accent'
                    : 'bg-duck-surface border-duck-border text-slate-400 hover:text-white hover:border-slate-500'
                }`}
              >
                <span className="material-symbols-outlined text-[14px]">{opt.icon}</span>
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Sampling Mode */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Sampling Depth
        </label>
        <div className="flex gap-3">
          {(['light', 'standard', 'deep'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => onChange({ ...data, sampling_mode: mode })}
              className={`flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider border transition-all ${
                data.sampling_mode === mode
                  ? 'bg-duck-accent/20 border-duck-accent text-duck-accent'
                  : 'bg-duck-surface border-duck-border text-slate-400 hover:text-white'
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-slate-500 mt-1">
          {data.sampling_mode === 'deep'
            ? 'Deep: Runs EXPLAIN ANALYZE on replica. Most thorough but adds DB load.'
            : data.sampling_mode === 'standard'
            ? 'Standard: Collects pg_stat data + EXPLAIN (no ANALYZE). Balanced.'
            : 'Light: Quick health check with cached snapshots. Minimal DB load.'}
        </p>
      </div>

      {/* Include Explain Plans */}
      {data.sampling_mode === 'deep' && (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={data.include_explain_plans}
            onChange={(e) => onChange({ ...data, include_explain_plans: e.target.checked })}
            className="rounded border-duck-border bg-duck-surface text-duck-accent focus:ring-duck-accent/30"
          />
          <span className="text-sm text-slate-300">
            Include EXPLAIN ANALYZE (runs on replica only)
          </span>
        </label>
      )}

      {/* Table Filter */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Table Filter (optional)
        </label>
        <input
          className={inputClass}
          placeholder="orders, payments, users (comma-separated)"
          value={data.table_filter?.join(', ') || ''}
          onChange={(e) =>
            onChange({
              ...data,
              table_filter: e.target.value
                ? e.target.value.split(',').map((s) => s.trim()).filter(Boolean)
                : undefined,
            })
          }
        />
      </div>

      {/* Related App Session (optional) */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Related App Session (optional)
        </label>
        <input
          className={inputClass}
          placeholder="e.g. APP-184 (auto-fills in contextual mode)"
          value={data.parent_session_id || ''}
          onChange={(e) =>
            onChange({
              ...data,
              parent_session_id: e.target.value || undefined,
              context_source: e.target.value ? 'user_selected' : undefined,
            })
          }
        />
        <p className="text-[10px] text-slate-500 mt-1">
          Link to an app investigation to focus agents on that service's queries and connections.
        </p>
      </div>
    </div>
  );
};

export default DatabaseDiagnosticsFields;
```

**Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/ActionCenter/forms/DatabaseDiagnosticsFields.tsx
git commit -m "feat(ui): add DatabaseDiagnosticsFields form component"
```

---

### Task 6: Wire Form into CapabilityForm + Add Launcher Card

**Files:**
- Modify: `frontend/src/components/ActionCenter/CapabilityForm.tsx`
- Modify: `frontend/src/components/Home/CapabilityLauncher.tsx`

**Step 1: Add to CapabilityForm**

In `CapabilityForm.tsx`, add the import and rendering case:

```typescript
// Add import at top
import DatabaseDiagnosticsFields from './forms/DatabaseDiagnosticsFields';
```

In the switch/conditional that renders form fields by capability, add:

```typescript
case 'database_diagnostics':
  return (
    <DatabaseDiagnosticsFields
      data={formData as DatabaseDiagnosticsForm}
      onChange={(d) => setFormData(d)}
    />
  );
```

Add default form data initializer for database_diagnostics:

```typescript
case 'database_diagnostics':
  return {
    capability: 'database_diagnostics',
    profile_id: '',
    time_window: '1h',
    focus: ['queries', 'connections', 'storage'],
    database_type: 'postgres',
    sampling_mode: 'standard',
    include_explain_plans: false,
  } as DatabaseDiagnosticsForm;
```

**Step 2: Add Launcher Card**

In `CapabilityLauncher.tsx`, add to the capabilities array:

```typescript
{
  type: 'database_diagnostics' as CapabilityType,
  title: 'Database Diagnostics',
  description: 'AI-powered PostgreSQL investigation with query analysis, lock detection, and performance tuning',
  icon: 'database',
  iconClasses: 'text-violet-400',
  ctaText: 'Investigate Database',
  ctaClasses: 'bg-violet-500/20 text-violet-400 hover:bg-violet-500/30',
  badge: 'NEW',
},
```

**Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/ActionCenter/CapabilityForm.tsx frontend/src/components/Home/CapabilityLauncher.tsx
git commit -m "feat(ui): wire database diagnostics into capability form and launcher"
```

---

### Task 7: Backend Session Endpoint for Database Diagnostics

**Files:**
- Modify: `backend/src/api/routes_v4.py`
- Test: `backend/tests/test_db_session.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_db_session.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from src.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_start_db_session(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v4/session/start", json={
            "capability": "database_diagnostics",
            "serviceName": "orders-db-primary",
            "profile_id": "prof-1",
            "time_window": "1h",
            "focus": ["queries", "connections"],
            "database_type": "postgres",
            "sampling_mode": "standard",
            "include_explain_plans": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data.get("capability") == "database_diagnostics"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_db_session.py -v`
Expected: FAIL — capability not recognized or missing handler

**Step 3: Add handler in routes_v4.py**

In `routes_v4.py`, inside the `start_session` endpoint, add a new capability branch after the existing ones (after `cluster_diagnostics`, before the default `troubleshoot_app`):

```python
elif request.capability == "database_diagnostics":
    profile_id = getattr(request, "profile_id", None) or request.extra.get("profile_id", "")
    sessions[session_id] = {
        "service_name": request.serviceName or f"db-{profile_id}",
        "incident_id": incident_id,
        "phase": "initial",
        "capability": "database_diagnostics",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "emitter": EventEmitter(session_id=session_id, websocket_manager=manager),
        "state": None,
        "chat_history": [],
        "db_context": {
            "profile_id": profile_id,
            "time_window": request.extra.get("time_window", "1h"),
            "focus": request.extra.get("focus", ["queries", "connections", "storage"]),
            "database_type": request.extra.get("database_type", "postgres"),
            "sampling_mode": request.extra.get("sampling_mode", "standard"),
            "include_explain_plans": request.extra.get("include_explain_plans", False),
            "parent_session_id": request.extra.get("parent_session_id"),
            "table_filter": request.extra.get("table_filter"),
        },
    }
    session_locks[session_id] = asyncio.Lock()

    # TODO Phase 3: Launch DB diagnostic orchestrator in background
    # background_tasks.add_task(run_db_diagnosis, session_id, ...)

    return StartSessionResponse(
        session_id=session_id,
        incident_id=incident_id,
        capability="database_diagnostics",
    )
```

Also update the `StartSessionRequest` model to accept the extra DB fields. The cleanest way is to add an `extra` dict field if it doesn't already exist, or add specific optional fields.

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_db_session.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_db_session.py
git commit -m "feat(api): add database_diagnostics capability to V4 session start"
```

---

### Task 8: Frontend Routing for DB Investigation View

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Add routing**

In `App.tsx`, inside the `handleFormSubmit` callback, add a case for `database_diagnostics`:

```typescript
case 'database_diagnostics': {
  const dbData = data as DatabaseDiagnosticsForm;
  const response = await startSessionV4({
    capability: 'database_diagnostics',
    serviceName: `db-${dbData.profile_id}`,
    profile_id: dbData.profile_id,
    time_window: dbData.time_window,
    focus: dbData.focus,
    database_type: dbData.database_type,
    sampling_mode: dbData.sampling_mode,
    include_explain_plans: dbData.include_explain_plans,
    parent_session_id: dbData.parent_session_id,
    table_filter: dbData.table_filter,
  });
  const newSession: V4Session = {
    session_id: response.session_id,
    incident_id: response.incident_id,
    service_name: `db-${dbData.profile_id}`,
    status: 'initial',
    confidence: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    capability: 'database_diagnostics',
  };
  setSessions((prev) => [newSession, ...prev]);
  setActiveSession(newSession);
  setViewState('investigation');  // Reuse investigation view for now
  break;
}
```

Note: This initially routes to the existing InvestigationView. Task 12 (Phase 4) will create the dedicated DatabaseWarRoom component and update this routing.

**Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(ui): add database_diagnostics routing in App.tsx form submission"
```

---

## Phase 3: LLM Agent Tools

### Task 9: Read-Only PostgreSQL Tool Functions

**Files:**
- Create: `backend/src/agents/database/tools/__init__.py`
- Create: `backend/src/agents/database/tools/pg_read_tools.py`
- Test: `backend/tests/test_pg_read_tools.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_pg_read_tools.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.database.tools.pg_read_tools import (
    run_explain,
    query_pg_stat_statements,
    query_pg_stat_activity,
    query_pg_locks,
    inspect_table_stats,
    inspect_index_usage,
    get_connection_pool,
)
from src.database.evidence_store import EvidenceStore


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.execute_diagnostic_query = AsyncMock(return_value={
        "columns": ["QUERY PLAN"],
        "rows": [['{"Plan": {"Node Type": "Seq Scan"}}']],
        "row_count": 1,
    })
    adapter.get_active_queries = AsyncMock(return_value=[])
    adapter.get_connection_pool = AsyncMock(return_value=MagicMock(
        active=10, idle=5, waiting=0, max_connections=100
    ))
    return adapter


@pytest.fixture
def evidence_store(tmp_path):
    return EvidenceStore(str(tmp_path / "test.db"))


@pytest.mark.asyncio
async def test_run_explain(mock_adapter, evidence_store):
    result = await run_explain(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="query_analyst",
        sql="SELECT * FROM orders WHERE user_id = 1",
    )
    assert "artifact_id" in result
    assert "summary" in result
    mock_adapter.execute_diagnostic_query.assert_called_once()


@pytest.mark.asyncio
async def test_get_connection_pool(mock_adapter, evidence_store):
    result = await get_connection_pool(
        adapter=mock_adapter,
        evidence_store=evidence_store,
        session_id="S-1",
        agent_name="health_analyst",
    )
    assert result["summary"]["active"] == 10
    assert result["summary"]["utilization_pct"] == 10.0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_pg_read_tools.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/src/agents/database/tools/__init__.py
"""Database diagnostic tool functions for LLM agents."""

# backend/src/agents/database/tools/pg_read_tools.py
"""Read-only PostgreSQL diagnostic tools.

Every tool returns a ToolOutput dict with:
- summary: compact dict for LLM consumption
- artifact_id: reference to evidence_artifacts row
- evidence_id: unique fingerprint for citation
"""

import uuid
from typing import Any

from src.database.evidence_store import EvidenceStore


def _evidence_id() -> str:
    return f"e-{uuid.uuid4().hex[:8]}"


async def run_explain(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
    sql: str,
    analyze: bool = False,
) -> dict:
    """Run EXPLAIN (FORMAT JSON) on a query. ANALYZE only when explicitly allowed."""
    explain_prefix = "EXPLAIN (FORMAT JSON, ANALYZE)" if analyze else "EXPLAIN (FORMAT JSON)"
    result = await adapter.execute_diagnostic_query(f"{explain_prefix} {sql}")

    full_content = str(result)
    rows = result.get("rows", [])
    plan_summary = "No plan returned"
    if rows and rows[0]:
        plan_summary = str(rows[0][0])[:200]

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id,
        evidence_id=eid,
        source_agent=agent_name,
        artifact_type="explain_plan",
        summary_json={"plan_preview": plan_summary, "analyze": analyze},
        full_content=full_content,
        preview=plan_summary[:100],
    )
    return {"summary": {"plan_preview": plan_summary, "analyze": analyze},
            "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_pg_stat_statements(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
    top_n: int = 20,
    order_by: str = "total_exec_time",
) -> dict:
    sql = f"""
        SELECT queryid, query, calls, total_exec_time, mean_exec_time,
               rows, shared_blks_hit, shared_blks_read
        FROM pg_stat_statements
        ORDER BY {order_by} DESC
        LIMIT {top_n}
    """
    result = await adapter.execute_diagnostic_query(sql)
    rows = result.get("rows", [])
    columns = result.get("columns", [])

    summary = {"top_queries_count": len(rows), "order_by": order_by}
    if rows:
        summary["top_query_preview"] = str(rows[0])[:200]

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="pg_stat_statements",
        summary_json=summary,
        full_content=str({"columns": columns, "rows": rows}),
        preview=f"Top {len(rows)} queries by {order_by}",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_pg_stat_activity(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    queries = await adapter.get_active_queries()
    query_list = [
        {"pid": q.pid, "duration_ms": q.duration_ms, "state": q.state, "query": q.query[:100]}
        for q in queries
    ] if queries else []

    summary = {
        "active_count": len(query_list),
        "slow_count": sum(1 for q in query_list if q["duration_ms"] > 5000),
    }

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="pg_stat_activity",
        summary_json=summary,
        full_content=str(query_list),
        preview=f"{summary['active_count']} active queries, {summary['slow_count']} slow (>5s)",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_pg_locks(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    sql = """
        SELECT l.pid, l.locktype, l.mode, l.granted, l.relation::regclass AS relation,
               a.query, a.state, a.wait_event_type
        FROM pg_locks l
        JOIN pg_stat_activity a ON l.pid = a.pid
        WHERE NOT l.granted
        ORDER BY a.query_start
    """
    result = await adapter.execute_diagnostic_query(sql)
    rows = result.get("rows", [])

    summary = {"blocked_count": len(rows)}
    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="pg_locks",
        summary_json=summary,
        full_content=str(result),
        preview=f"{len(rows)} blocked lock requests",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def inspect_table_stats(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
    table_filter: list[str] | None = None,
) -> dict:
    where_clause = ""
    if table_filter:
        tables = ", ".join(f"'{t}'" for t in table_filter)
        where_clause = f"WHERE relname IN ({tables})"

    sql = f"""
        SELECT relname, seq_scan, idx_scan, n_tup_ins, n_tup_upd, n_tup_del,
               n_dead_tup, n_live_tup, last_vacuum, last_autovacuum, last_analyze
        FROM pg_stat_user_tables
        {where_clause}
        ORDER BY n_dead_tup DESC
        LIMIT 50
    """
    result = await adapter.execute_diagnostic_query(sql)
    rows = result.get("rows", [])

    summary = {"tables_scanned": len(rows)}
    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="table_stats",
        summary_json=summary,
        full_content=str(result),
        preview=f"Stats for {len(rows)} tables",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def inspect_index_usage(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    sql = """
        SELECT s.relname AS table, s.indexrelname AS index, s.idx_scan,
               pg_relation_size(s.indexrelid) AS index_size
        FROM pg_stat_user_indexes s
        ORDER BY s.idx_scan ASC
        LIMIT 50
    """
    result = await adapter.execute_diagnostic_query(sql)
    rows = result.get("rows", [])

    unused = [r for r in rows if r and len(r) > 2 and r[2] == 0]
    summary = {"indexes_checked": len(rows), "unused_indexes": len(unused)}

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="index_usage",
        summary_json=summary,
        full_content=str(result),
        preview=f"{len(rows)} indexes checked, {len(unused)} unused",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def get_connection_pool(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    pool = await adapter.get_connection_pool()
    utilization = round((pool.active / pool.max_connections) * 100, 1) if pool.max_connections else 0

    summary = {
        "active": pool.active,
        "idle": pool.idle,
        "waiting": pool.waiting,
        "max": pool.max_connections,
        "utilization_pct": utilization,
    }

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="connection_pool",
        summary_json=summary,
        full_content=str(summary),
        preview=f"Connections: {pool.active}/{pool.max_connections} ({utilization}%)",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_pg_read_tools.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add backend/src/agents/database/tools/
git add backend/tests/test_pg_read_tools.py
git commit -m "feat(db-agents): add read-only PostgreSQL tool functions with evidence storage"
```

---

## Phase 4: LLM Agent Graph V2

### Task 10: Agent Prompt Templates

**Files:**
- Create: `backend/src/agents/database/prompts/__init__.py`
- Create: `backend/src/agents/database/prompts/templates.py`

**Step 1: Write prompt templates**

```python
# backend/src/agents/database/prompts/__init__.py
"""Database diagnostic agent prompt templates."""

# backend/src/agents/database/prompts/templates.py
"""Structured prompts for database diagnostic agents.

Each agent gets a system prompt with investigation context
and tool descriptions. All agents must return JSON-only responses.
"""

QUERY_ANALYST_SYSTEM = """You are a PostgreSQL query performance analyst for Debug Duck, an AI-powered database diagnostic platform.

DATABASE: {profile_name} ({host}:{port}/{database})
INVESTIGATION MODE: {investigation_mode}
{contextual_section}
SAMPLING MODE: {sampling_mode}
FOCUS AREAS: {focus_list}

You have access to these tools:
- run_explain: Run EXPLAIN (FORMAT JSON) on a query
- query_pg_stat_statements: Get top N queries by execution time
- query_pg_stat_activity: Get currently active queries
- capture_query_sample: Fetch parameterized query samples by SQL hash

RULES:
1. Always call tools first to gather evidence before making claims
2. Never execute destructive operations — create remediation plans instead
3. Include confidence scores (0.0-1.0) with every finding
4. If confidence < 0.7, set needs_human_review: true
5. Cite specific evidence_ids for every finding
6. Return ONLY valid JSON matching the DBFindingV2 schema

TASK: Analyze query performance. Look for slow queries (>1s mean), sequential scans on large tables, missing indexes, and query plan regressions.

Return a JSON array of findings."""

HEALTH_ANALYST_SYSTEM = """You are a PostgreSQL health analyst for Debug Duck, an AI-powered database diagnostic platform.

DATABASE: {profile_name} ({host}:{port}/{database})
INVESTIGATION MODE: {investigation_mode}
{contextual_section}

You have access to these tools:
- get_connection_pool: Get active/idle/waiting/max connections
- query_pg_locks: Get blocked lock requests
- get_replication_status: Get replication lag and replica list
- get_config_setting: Get current value of any pg_setting

RULES:
1. Always call tools first to gather evidence before making claims
2. Include confidence scores (0.0-1.0) with every finding
3. If confidence < 0.7, set needs_human_review: true
4. Cite specific evidence_ids for every finding
5. Return ONLY valid JSON matching the DBFindingV2 schema

TASK: Analyze database health. Check connection pool saturation (>80% warning), lock contention, replication lag, deadlock detection, cache hit ratio (<0.9 warning).

Return a JSON array of findings."""

SCHEMA_ANALYST_SYSTEM = """You are a PostgreSQL schema analyst for Debug Duck, an AI-powered database diagnostic platform.

DATABASE: {profile_name} ({host}:{port}/{database})
INVESTIGATION MODE: {investigation_mode}
{contextual_section}

You have access to these tools:
- inspect_table_stats: Get table-level stats (seq scans, dead tuples, bloat)
- inspect_index_usage: Get index scan counts and sizes
- inspect_schema: Get column definitions and constraints

RULES:
1. Always call tools first to gather evidence before making claims
2. Include confidence scores (0.0-1.0) with every finding
3. If confidence < 0.7, set needs_human_review: true
4. Cite specific evidence_ids for every finding
5. Return ONLY valid JSON matching the DBFindingV2 schema

TASK: Analyze schema health. Look for table bloat (dead tuples > 10% of live), unused indexes, missing indexes suggested by sequential scans on large tables, and schema anti-patterns.

Return a JSON array of findings."""

SYNTHESIZER_SYSTEM = """You are the root cause analyst for Debug Duck. You receive findings from three specialist agents (query_analyst, health_analyst, schema_analyst) and must synthesize them into a coherent root cause analysis.

DATABASE: {profile_name}
INVESTIGATION MODE: {investigation_mode}
{contextual_section}

TASK:
1. Review all findings from specialist agents
2. Identify the primary root cause
3. Trace the causal chain (root cause → cascading symptoms → correlated anomalies)
4. Assign causal_role to each finding: "root_cause", "cascading_failure", or "correlated_anomaly"
5. Generate an executive summary (3 sentences max)
6. Rank all findings by severity * confidence

Return JSON with:
- summary: string (3-sentence executive summary)
- root_cause: string (one-sentence root cause)
- findings: array of findings with causal_role assigned
- needs_human_review: boolean (true if any finding confidence < 0.7)"""

CONTEXTUAL_SECTION_TEMPLATE = """LINKED APP INVESTIGATION: {parent_session_id}
TRIGGERING SERVICE: {service_name}
APP FINDINGS: {app_findings_summary}
FOCUS: Prioritize queries and connections related to {service_name}."""

STANDALONE_SECTION = """No linked app investigation. Run broad diagnostics across all workloads."""
```

**Step 2: Commit**

```bash
git add backend/src/agents/database/prompts/
git commit -m "feat(db-agents): add structured prompt templates for LLM-powered agents"
```

---

### Task 11: LangGraph V2 Agent Graph

**Files:**
- Create: `backend/src/agents/database/graph_v2.py`
- Test: `backend/tests/test_db_graph_v2.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_db_graph_v2.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.database.graph_v2 import build_db_diagnostic_graph_v2, DBDiagnosticStateV2


@pytest.mark.asyncio
async def test_graph_compiles():
    graph = build_db_diagnostic_graph_v2()
    assert graph is not None


@pytest.mark.asyncio
async def test_connection_validator_fails_gracefully():
    graph = build_db_diagnostic_graph_v2()

    mock_adapter = AsyncMock()
    mock_adapter.health_check = AsyncMock(return_value=MagicMock(
        status="unreachable", error="Connection refused"
    ))

    initial_state: DBDiagnosticStateV2 = {
        "run_id": "R-1",
        "session_id": "S-1",
        "profile_id": "prof-1",
        "profile_name": "test-db",
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "engine": "postgresql",
        "investigation_mode": "standalone",
        "sampling_mode": "standard",
        "focus": ["queries"],
        "status": "running",
        "findings": [],
        "summary": "",
        "_adapter": mock_adapter,
    }

    result = await graph.ainvoke(initial_state)
    assert result["status"] == "failed"
    assert result["connected"] is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_db_graph_v2.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the graph**

```python
# backend/src/agents/database/graph_v2.py
"""LangGraph V2 for AI-powered database diagnostics.

Replaces heuristic graph.py with LLM-powered agents using a tool-first
pattern. Haiku for extraction agents, Opus for synthesizer/dossier.
"""

import asyncio
import logging
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)


class DBDiagnosticStateV2(TypedDict, total=False):
    # Session identity
    run_id: str
    session_id: str
    profile_id: str
    profile_name: str
    host: str
    port: int
    database: str
    engine: str

    # Investigation config
    investigation_mode: str  # "standalone" | "contextual"
    sampling_mode: str  # "light" | "standard" | "deep"
    focus: list[str]
    table_filter: list[str]
    include_explain_plans: bool
    parent_session_id: str
    app_context: dict  # Findings from parent app session

    # Runtime injections
    _adapter: object
    _evidence_store: object
    _job_queue: object
    _emitter: object

    # Execution state
    status: str  # "running" | "completed" | "failed"
    connected: bool
    health_latency_ms: float
    error: Optional[str]

    # Results
    findings: list[dict]
    query_findings: list[dict]
    health_findings: list[dict]
    schema_findings: list[dict]
    summary: str
    root_cause: str
    needs_human_review: bool
    dossier: dict


# --- Node: Connection Validator (no LLM) ---

async def connection_validator(state: DBDiagnosticStateV2) -> dict:
    adapter = state["_adapter"]
    emitter = state.get("_emitter")

    if emitter:
        await emitter.emit("connection_validator", "started", "Checking database connectivity")

    try:
        health = await adapter.health_check()
    except Exception as e:
        logger.error("Connection validation failed: %s", e)
        if emitter:
            await emitter.emit("connection_validator", "error", f"Connection failed: {e}")
        return {"connected": False, "status": "failed", "error": str(e)}

    if health.status == "unreachable" or health.status == "degraded":
        if emitter:
            await emitter.emit("connection_validator", "error",
                              f"Database unreachable: {health.error}")
        return {"connected": False, "status": "failed", "error": health.error}

    if emitter:
        await emitter.emit("connection_validator", "success",
                          f"Connected ({health.latency_ms}ms)")

    return {
        "connected": True,
        "health_latency_ms": getattr(health, "latency_ms", 0),
    }


def should_continue(state: DBDiagnosticStateV2) -> str:
    if state.get("connected"):
        return "context_loader"
    return END


# --- Node: Context Loader (no LLM) ---

async def context_loader(state: DBDiagnosticStateV2) -> dict:
    """Load parent app session findings if in contextual mode."""
    emitter = state.get("_emitter")
    parent_id = state.get("parent_session_id")

    if state.get("investigation_mode") != "contextual" or not parent_id:
        if emitter:
            await emitter.emit("context_loader", "success", "Standalone mode — no app context")
        return {"app_context": {}, "investigation_mode": "standalone"}

    if emitter:
        await emitter.emit("context_loader", "started",
                          f"Loading context from app session {parent_id}")

    # TODO: Fetch findings from parent session via internal API
    # For now, return empty context
    return {"app_context": {"parent_session_id": parent_id}}


# --- Node: Query Analyst (LLM + tools) ---

async def query_analyst(state: DBDiagnosticStateV2) -> dict:
    """Analyze query performance using LLM with read-only PG tools."""
    emitter = state.get("_emitter")
    if emitter:
        await emitter.emit("query_analyst", "started", "Analyzing query performance")

    # Phase 1: Use heuristic analysis (same as v1 but with evidence storage)
    # Phase 2: Replace with LLM tool-calling agent (Haiku)
    adapter = state["_adapter"]
    evidence_store = state.get("_evidence_store")
    findings = []

    try:
        queries = await adapter.get_active_queries()
        slow = [q for q in queries if q.duration_ms > 5000]

        for q in slow:
            severity = "critical" if q.duration_ms > 30000 else "high" if q.duration_ms > 10000 else "medium"
            findings.append({
                "finding_id": f"f-qa-{q.pid}",
                "agent": "query_analyst",
                "category": "slow_query",
                "title": f"Slow query (pid={q.pid}, {q.duration_ms}ms)",
                "severity": severity,
                "confidence_raw": 0.9,
                "confidence_calibrated": 0.85,
                "detail": f"Query running for {q.duration_ms}ms: {q.query[:200]}",
                "evidence_ids": [],
                "recommendation": "Review query plan and consider adding indexes",
                "remediation_available": True,
                "rule_check": f"duration_ms={q.duration_ms} > 5000",
            })
    except Exception as e:
        logger.error("Query analyst failed: %s", e)
        if emitter:
            await emitter.emit("query_analyst", "error", str(e))

    if emitter:
        await emitter.emit("query_analyst", "success", f"Found {len(findings)} query issues")

    return {"query_findings": findings}


# --- Node: Health Analyst (LLM + tools) ---

async def health_analyst(state: DBDiagnosticStateV2) -> dict:
    """Analyze database health metrics."""
    emitter = state.get("_emitter")
    if emitter:
        await emitter.emit("health_analyst", "started", "Analyzing database health")

    adapter = state["_adapter"]
    findings = []

    try:
        pool = await adapter.get_connection_pool()
        if pool.max_connections and pool.active / pool.max_connections > 0.8:
            utilization = round(pool.active / pool.max_connections * 100, 1)
            findings.append({
                "finding_id": "f-ha-conn-sat",
                "agent": "health_analyst",
                "category": "connections",
                "title": f"Connection pool saturation ({utilization}%)",
                "severity": "critical" if utilization > 95 else "high",
                "confidence_raw": 0.95,
                "confidence_calibrated": 0.90,
                "detail": f"Active: {pool.active}, Max: {pool.max_connections}",
                "evidence_ids": [],
                "recommendation": "Increase max_connections or reduce connection leaks",
                "remediation_available": True,
                "rule_check": f"utilization={utilization}% > 80%",
            })

        perf = await adapter.get_performance_stats()
        if perf.cache_hit_ratio < 0.9:
            findings.append({
                "finding_id": "f-ha-cache",
                "agent": "health_analyst",
                "category": "memory",
                "title": f"Low cache hit ratio ({perf.cache_hit_ratio:.2%})",
                "severity": "medium",
                "confidence_raw": 0.85,
                "confidence_calibrated": 0.80,
                "detail": f"Cache hit ratio is {perf.cache_hit_ratio:.2%}, below 90% threshold",
                "evidence_ids": [],
                "recommendation": "Increase shared_buffers or review query access patterns",
                "remediation_available": True,
                "rule_check": f"cache_hit_ratio={perf.cache_hit_ratio:.4f} < 0.9",
            })

        if perf.deadlocks > 0:
            findings.append({
                "finding_id": "f-ha-deadlock",
                "agent": "health_analyst",
                "category": "deadlock",
                "title": f"{perf.deadlocks} deadlocks detected",
                "severity": "high",
                "confidence_raw": 0.80,
                "confidence_calibrated": 0.75,
                "detail": f"Deadlock count: {perf.deadlocks}",
                "evidence_ids": [],
                "recommendation": "Review lock ordering and transaction isolation",
                "remediation_available": False,
                "rule_check": f"deadlocks={perf.deadlocks} > 0",
            })
    except Exception as e:
        logger.error("Health analyst failed: %s", e)
        if emitter:
            await emitter.emit("health_analyst", "error", str(e))

    if emitter:
        await emitter.emit("health_analyst", "success", f"Found {len(findings)} health issues")

    return {"health_findings": findings}


# --- Node: Schema Analyst (LLM + tools) ---

async def schema_analyst(state: DBDiagnosticStateV2) -> dict:
    """Analyze schema health and index usage."""
    emitter = state.get("_emitter")
    if emitter:
        await emitter.emit("schema_analyst", "started", "Analyzing schema health")

    # Placeholder — will be enhanced with LLM tool-calling in Phase 2
    findings = []

    if emitter:
        await emitter.emit("schema_analyst", "success", f"Found {len(findings)} schema issues")

    return {"schema_findings": findings}


# --- Node: Synthesizer (Sonnet/Opus) ---

async def synthesizer(state: DBDiagnosticStateV2) -> dict:
    """Combine all findings, identify root cause, generate summary."""
    emitter = state.get("_emitter")
    if emitter:
        await emitter.emit("synthesizer", "started", "Synthesizing root cause analysis")

    all_findings = (
        state.get("query_findings", [])
        + state.get("health_findings", [])
        + state.get("schema_findings", [])
    )

    # Sort by severity priority * confidence
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    all_findings.sort(
        key=lambda f: severity_order.get(f.get("severity", "info"), 0)
        * f.get("confidence_raw", 0),
        reverse=True,
    )

    needs_review = any(f.get("confidence_calibrated", 1.0) < 0.7 for f in all_findings)

    root_cause = all_findings[0]["title"] if all_findings else "No issues detected"
    finding_count = len(all_findings)
    critical_count = sum(1 for f in all_findings if f.get("severity") == "critical")

    summary = (
        f"Investigated {state.get('profile_name', 'unknown')} database. "
        f"Found {finding_count} issue(s), {critical_count} critical. "
        f"Primary concern: {root_cause}."
    )

    if emitter:
        await emitter.emit("synthesizer", "success", summary)
        if needs_review:
            await emitter.emit("synthesizer", "warning",
                              "Low confidence findings detected — human review recommended")

    return {
        "findings": all_findings,
        "summary": summary,
        "root_cause": root_cause,
        "needs_human_review": needs_review,
        "status": "completed",
    }


# --- Graph Builder ---

def build_db_diagnostic_graph_v2():
    graph = StateGraph(DBDiagnosticStateV2)

    graph.add_node("connection_validator", connection_validator)
    graph.add_node("context_loader", context_loader)
    graph.add_node("query_analyst", query_analyst)
    graph.add_node("health_analyst", health_analyst)
    graph.add_node("schema_analyst", schema_analyst)
    graph.add_node("synthesizer", synthesizer)

    graph.set_entry_point("connection_validator")

    graph.add_conditional_edges(
        "connection_validator",
        should_continue,
        {"context_loader": "context_loader", END: END},
    )

    # After context_loader, dispatch all analysts in parallel
    graph.add_edge("context_loader", "query_analyst")
    graph.add_edge("context_loader", "health_analyst")
    graph.add_edge("context_loader", "schema_analyst")

    # All analysts feed into synthesizer
    graph.add_edge("query_analyst", "synthesizer")
    graph.add_edge("health_analyst", "synthesizer")
    graph.add_edge("schema_analyst", "synthesizer")

    graph.add_edge("synthesizer", END)

    return graph.compile()
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_db_graph_v2.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add backend/src/agents/database/graph_v2.py backend/tests/test_db_graph_v2.py
git commit -m "feat(db-agents): add LangGraph V2 with parallel analyst agents and synthesizer"
```

---

## Phase 5: DB War Room UI

### Task 12: Database War Room Component

**Files:**
- Create: `frontend/src/components/Investigation/DatabaseWarRoom.tsx`

This is the three-column layout adapted for database context: Investigator (col-3), Evidence Findings (col-5), Navigator (col-4). For the initial implementation, it reuses existing components (AgentFindingCard, CausalRoleBadge) and adds DB-specific elements.

**Step 1: Write the component**

Create `frontend/src/components/Investigation/DatabaseWarRoom.tsx` with:
- Props: `session: V4Session`, `events: TaskEvent[]`, `wsConnected: boolean`, `phase`, `confidence`
- Three-column CSS grid matching `InvestigationView.tsx` pattern
- Left column: DB profile banner, event timeline, chat trigger
- Center column: Findings list with AgentFindingCard
- Right column: Connection pool gauge (simple div), metric summary

The implementation should follow the exact same grid pattern as `InvestigationView.tsx` line 155-179:

```typescript
<div className="grid grid-cols-12 flex-1 overflow-hidden">
  <div className="col-span-3 ...">  {/* DB Investigator */}
  <div className="col-span-5 ...">  {/* Evidence Findings */}
  <div className="col-span-4 ...">  {/* DB Navigator */}
</div>
```

**Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Update App.tsx routing**

In `App.tsx`, update the rendering conditional to route `database_diagnostics` sessions to DatabaseWarRoom instead of InvestigationView. Add the import and conditional:

```typescript
// When activeSession.capability === 'database_diagnostics':
<ChatProvider sessionId={activeSessionId} events={currentTaskEvents} ...>
  <DatabaseWarRoom session={activeSession} events={currentTaskEvents} ... />
</ChatProvider>
```

**Step 4: Commit**

```bash
git add frontend/src/components/Investigation/DatabaseWarRoom.tsx frontend/src/App.tsx
git commit -m "feat(ui): add DatabaseWarRoom three-column layout for DB investigations"
```

---

## Phase 6: Dossier Generation

### Task 13: Database Dossier View Component

**Files:**
- Create: `frontend/src/components/Investigation/DatabaseDossierView.tsx`

Follow the exact same pattern as `PostMortemDossierView.tsx`:
- Props: `sessionId: string`, `onBack: () => void`
- Fetch findings via `getFindings(sessionId)`
- Sections: Executive Summary, Root Cause Analysis, Findings by Agent, Performance Recommendations, Remediation Plans, Health Scorecard
- Export button (PDF placeholder)

**Step 1: Write the component following PostMortemDossierView.tsx patterns**

**Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`

**Step 3: Commit**

```bash
git add frontend/src/components/Investigation/DatabaseDossierView.tsx
git commit -m "feat(ui): add DatabaseDossierView report component"
```

---

## Phase 7: Visualization Components

### Task 14: Connection Pool Gauge

**Files:**
- Create: `frontend/src/components/Investigation/db-viz/ConnectionPoolGauge.tsx`

Simple SVG arc gauge showing active/max connections with color thresholds (green <60%, yellow 60-80%, red >80%).

### Task 15: Slow Query Timeline

**Files:**
- Create: `frontend/src/components/Investigation/db-viz/SlowQueryTimeline.tsx`

Horizontal timeline with query dots sized by duration, colored by severity.

### Task 16: EXPLAIN Plan Tree

**Files:**
- Create: `frontend/src/components/Investigation/db-viz/ExplainPlanTree.tsx`

Expandable tree view of EXPLAIN JSON output (Node Type, Rows, Cost, etc.).

**For each visualization:**

**Step 1:** Write the component
**Step 2:** Run `cd frontend && npx tsc --noEmit` — 0 errors
**Step 3:** Commit each one individually

```bash
git commit -m "feat(db-viz): add ConnectionPoolGauge SVG component"
git commit -m "feat(db-viz): add SlowQueryTimeline horizontal timeline"
git commit -m "feat(db-viz): add ExplainPlanTree expandable tree view"
```

---

## Phase 8: Wire Background Diagnosis Execution

### Task 17: DB Diagnosis Background Runner

**Files:**
- Modify: `backend/src/api/routes_v4.py`

**Step 1:** Add `run_db_diagnosis` function following the `run_diagnosis` pattern (line 533-559):

```python
async def run_db_diagnosis(session_id: str, db_context: dict, emitter):
    from src.agents.database.graph_v2 import build_db_diagnostic_graph_v2
    from src.database.evidence_store import EvidenceStore
    from src.database.adapters.registry import adapter_registry

    lock = session_locks.get(session_id, asyncio.Lock())
    try:
        adapter = adapter_registry.get_by_profile(db_context["profile_id"])
        if not adapter:
            await emitter.emit("supervisor", "error", "No adapter found for profile")
            async with lock:
                sessions[session_id]["phase"] = "error"
            return

        evidence_store = EvidenceStore(db_path)
        graph = build_db_diagnostic_graph_v2()

        initial_state = {
            "run_id": f"R-{session_id[:8]}",
            "session_id": session_id,
            "profile_id": db_context["profile_id"],
            # ... populate from db_context
            "_adapter": adapter,
            "_evidence_store": evidence_store,
            "_emitter": emitter,
            "status": "running",
            "findings": [],
        }

        result = await asyncio.wait_for(graph.ainvoke(initial_state), timeout=180)

        async with lock:
            if session_id in sessions:
                sessions[session_id]["state"] = result
                sessions[session_id]["phase"] = "complete" if result.get("status") == "completed" else "error"
                sessions[session_id]["confidence"] = 0.85  # From synthesizer

    except Exception as e:
        logger.error("DB diagnosis failed: %s", e)
        async with lock:
            if session_id in sessions:
                sessions[session_id]["phase"] = "error"
        await emitter.emit("supervisor", "error", f"DB diagnosis failed: {e}")
```

**Step 2:** Update the `database_diagnostics` branch in `start_session` to call:

```python
background_tasks.add_task(run_db_diagnosis, session_id, sessions[session_id]["db_context"], emitter)
```

**Step 3:** Commit

```bash
git add backend/src/api/routes_v4.py
git commit -m "feat(api): wire database diagnostics background execution via LangGraph V2"
```

---

## Summary: Task Dependency Graph

```
Phase 1 (Foundation)
  Task 1: Evidence Store         ──┐
  Task 2: V2 Models              ──┤
  Task 3: Job Queue              ──┘
                                    │
Phase 2 (Session Integration)       ▼
  Task 4: CapabilityType         ──┐
  Task 5: Form Fields            ──┤
  Task 6: Wire Form + Launcher   ──┤
  Task 7: Backend Session        ──┤
  Task 8: Frontend Routing       ──┘
                                    │
Phase 3 (Agent Tools)               ▼
  Task 9: PG Read Tools          ──┐
                                    │
Phase 4 (Agent Graph)               ▼
  Task 10: Prompt Templates      ──┐
  Task 11: LangGraph V2          ──┘
                                    │
Phase 5 (War Room UI)               ▼
  Task 12: DatabaseWarRoom       ──┐
                                    │
Phase 6 (Dossier)                   ▼
  Task 13: DatabaseDossierView   ──┐
                                    │
Phase 7 (Visualizations)            ▼
  Task 14: ConnectionPoolGauge   ──┐
  Task 15: SlowQueryTimeline     ──┤ (parallel)
  Task 16: ExplainPlanTree       ──┘
                                    │
Phase 8 (Wire Execution)            ▼
  Task 17: Background Runner     ──┘
```

Total: **17 tasks**, estimated **8 phases**

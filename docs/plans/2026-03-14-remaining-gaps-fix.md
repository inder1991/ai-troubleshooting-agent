# Remaining Gaps Fix Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 10 remaining gaps (P0+P1+P2) in DB diagnostics: index suggestions, verification SQL, schema filtering, multi-query EXPLAIN, impact estimation, XSS sanitization, randomized mocks, empty DB handling, network disconnect UI, concurrent scan warning.

**Architecture:** Backend adapter fixes + graph agent improvements + frontend edge case handling. No infrastructure changes.

**Tech Stack:** Python, TypeScript, React

---

## Stream A: Backend — Adapter + Agent Improvements

### Task A1: Schema filtering + batch table detail

**Files:** `backend/src/database/adapters/postgres.py`, `backend/src/database/adapters/mock_adapter.py`

**Fixes:**
- Add `WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')` to all schema queries in postgres.py (_fetch_schema_snapshot, get_table_detail, get_table_access_patterns)
- Same filter in get_autovacuum_status

### Task A2: EXPLAIN top 3 queries (not just worst)

**Files:** `backend/src/agents/database/graph_v2.py`

**Fix:** In query_analyst, change from explaining only the worst query to the top 3:
```python
# Instead of:
if slow:
    worst = max(slow, key=lambda q: q.duration_ms)
    explain_plan = await adapter.explain_query(worst.query)

# Change to:
explain_plans = []
for q in sorted(slow, key=lambda q: q.duration_ms, reverse=True)[:3]:
    try:
        plan = await adapter.explain_query(q.query)
        if plan:
            explain_plans.append({
                "plan": plan,
                "query": q.query[:500],
                "pid": q.pid,
                "duration_ms": q.duration_ms,
                "user": getattr(q, 'user', ''),
            })
    except Exception:
        pass
```

Then emit as `"explain_plans": explain_plans` (list) instead of `"explain_plan": single_plan`.

Update DatabaseWarRoom.tsx to extract `explain_plans` (list) and pass the first one to ExplainPlanTree, or show a tab/selector if multiple plans exist.

### Task A3: Index suggestions from EXPLAIN

**Files:** `backend/src/agents/database/graph_v2.py`

**Fix:** After running EXPLAIN, detect Seq Scans with Filter clauses and generate CREATE INDEX findings:

```python
def detect_index_suggestions(plan_data: dict, query_text: str) -> list[dict]:
    """Scan EXPLAIN plan for Seq Scans with filters — suggest indexes."""
    suggestions = []
    def scan_nodes(node):
        node_type = node.get('Node Type', '')
        if 'Seq Scan' in node_type and node.get('Relation Name') and node.get('Filter'):
            table = node['Relation Name']
            filter_text = node['Filter']
            # Extract column names from filter
            import re
            cols = re.findall(r'\b([a-z_]+)\s*[>=<]', filter_text)
            if cols:
                suggestions.append({
                    "table": table,
                    "columns": cols,
                    "filter": filter_text,
                    "rows_scanned": node.get('Plan Rows', 0),
                })
        for child in node.get('Plans', []):
            scan_nodes(child)
    scan_nodes(plan_data)
    return suggestions
```

For each suggestion, create a finding with:
```python
DBFindingV2(
    category="index_candidate",
    title=f"Missing index: {table} ({', '.join(cols)})",
    remediation_sql=f"CREATE INDEX CONCURRENTLY idx_{table}_{'_'.join(cols)} ON {table} ({', '.join(cols)});",
    remediation_warning="CREATE INDEX CONCURRENTLY is non-blocking but may take minutes on large tables.",
)
```

### Task A4: Verification SQL + Impact estimation per fix

**Files:** `backend/src/agents/database/graph_v2.py` (synthesizer section)

**Fix:** In the fix_recommendations builder, add `verification_sql` and `estimated_impact` fields:

```python
if cat == "slow_query":
    verification_sql = f"SELECT pid, state, query FROM pg_stat_activity WHERE pid = {pid};\n-- Should return 0 rows (query terminated)"
    estimated_impact = "Immediate — query stops, connection freed"
elif cat == "bloat":
    table_size_mb = ... # from finding detail
    verification_sql = f"SELECT relname, n_dead_tup, n_live_tup FROM pg_stat_user_tables WHERE relname = '{table}';\n-- n_dead_tup should be near 0"
    estimated_impact = f"~{max(1, int(table_size_mb / 500))} minutes for {table_size_mb}MB table. Table locked during VACUUM FULL."
elif cat == "index_candidate":
    verification_sql = f"EXPLAIN SELECT ... -- Should show Index Scan instead of Seq Scan"
    estimated_impact = f"~{max(1, int(rows / 100000))} minutes to create. Non-blocking with CONCURRENTLY."
elif cat == "memory":
    verification_sql = "SHOW shared_buffers;\nSELECT round(heap_blks_hit::numeric / (heap_blks_hit + heap_blks_read) * 100, 1) AS cache_hit_pct FROM pg_statio_user_tables;\n-- Should improve after restart"
    estimated_impact = "Requires PostgreSQL restart. Plan 30-60 second downtime."
```

### Task A5: Randomized mock data

**Files:** `backend/src/database/adapters/mock_adapter.py`

**Fix:** Add variance to mock data using `random`:
```python
import random

# In _fetch_active_queries:
duration_ms = random.randint(8000, 35000)  # Instead of hardcoded 31000

# In _fetch_performance_stats:
cache_hit_ratio = round(random.uniform(0.78, 0.92), 2)  # Instead of fixed 0.82
deadlocks = random.randint(0, 5)

# In get_table_detail:
bloat_ratio = round(random.uniform(0.3, 0.75), 2) for audit_log  # Vary each scan
```

This prevents "every scan looks identical" during testing.

---

## Stream B: Frontend — Edge Cases

### Task B1: XSS sanitization in query text rendering

**Files:** `frontend/src/components/Investigation/db-viz/SlowQueryTimeline.tsx`, `frontend/src/components/Investigation/db-board/CaseFile.tsx`

**Fix:** React already escapes JSX text content by default (`{q.query}` is safe). The risk is only if we use `dangerouslySetInnerHTML` — verify none of the db-viz components use it. If any do, remove and use safe rendering.

Also verify the `<pre>` blocks in ExplainPlanTree and SlowQueryTimeline don't use innerHTML.

### Task B2: Empty database handling

**Files:** `frontend/src/components/Investigation/DatabaseWarRoom.tsx`, `backend/src/agents/database/graph_v2.py`

**Backend:** In schema_analyst, if schema snapshot returns 0 tables:
```python
if not schema.tables:
    await emitter.emit("schema_analyst", "reasoning", "Database has no user tables")
    await emitter.emit("schema_analyst", "success", "No tables to analyze")
    return {"schema_findings": []}
```

**Frontend:** PanelZone already shows "No issues found" when agent completes without data. Verify this works for all panels when DB is empty.

### Task B3: Network disconnect banner

**Files:** `frontend/src/components/Investigation/DatabaseWarRoom.tsx`

**Fix:** The DatabaseWarRoom already polls via REST (getSessionEvents every 3s). If polling fails 3+ times consecutively, show a banner:

```tsx
const [pollFailCount, setPollFailCount] = useState(0);

// In poll effect, on error:
setPollFailCount(c => c + 1);
// On success:
setPollFailCount(0);

// In render:
{pollFailCount >= 3 && (
  <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-[11px] text-red-400 flex items-center gap-2">
    <span className="material-symbols-outlined text-sm">wifi_off</span>
    Connection lost — retrying...
  </div>
)}
```

### Task B4: Concurrent scan warning

**Files:** `frontend/src/components/Database/DBDiagnosticsPage.tsx`

**Fix:** Before creating a new session, check if any existing DB session against the same profile is still running:

```tsx
const handleNewDiagnostic = useCallback(async (formData) => {
    // Check for running session against same profile
    const running = dbSessions.find(s =>
        !['complete', 'error', 'cancelled'].includes(s.status) &&
        s.service_name.includes(formData.profile_id.slice(0, 8))
    );
    if (running) {
        addToast('warning', 'A diagnostic is already running against this profile. Wait for it to complete or cancel it.');
        return;
    }
    // ... proceed with session creation
});
```

---

## Stream C: Frontend — Fix Recommendations Enrichment

### Task C1: Show verification SQL + impact in FixRecommendations

**Files:** `frontend/src/components/Investigation/db-board/FixRecommendations.tsx`

**Fix:** Add `verification_sql` and `estimated_impact` to the Fix interface. Show in expanded section after the warning:

```tsx
{fix.estimated_impact && (
    <p className="text-[9px] text-slate-400 mt-1">
        Impact: {fix.estimated_impact}
    </p>
)}
{fix.verification_sql && (
    <details className="mt-1.5">
        <summary className="text-[9px] text-duck-accent cursor-pointer">Verify fix</summary>
        <pre className="text-[9px] font-mono text-slate-400 bg-duck-bg/50 rounded px-2 py-1 mt-1 whitespace-pre-wrap">
            {fix.verification_sql}
        </pre>
    </details>
)}
```

### Task C2: Show multiple EXPLAIN plans

**Files:** `frontend/src/components/Investigation/DatabaseWarRoom.tsx`, `frontend/src/components/Investigation/db-viz/ExplainPlanTree.tsx`

**Fix:** DatabaseWarRoom extracts `explain_plans` (list) from events. If multiple plans exist, show a simple tab selector above the tree:

```tsx
const [activePlanIdx, setActivePlanIdx] = useState(0);
const plans = explainPlans || (explainPlan ? [explainPlan] : []);

// In render:
{plans.length > 1 && (
    <div className="flex gap-1 mb-2">
        {plans.map((p, i) => (
            <button key={i} onClick={() => setActivePlanIdx(i)}
                className={`text-[9px] px-1.5 py-0.5 rounded ${i === activePlanIdx ? 'bg-duck-accent/20 text-duck-accent' : 'text-slate-400'}`}>
                pid:{p.pid}
            </button>
        ))}
    </div>
)}
{plans[activePlanIdx] && <ExplainPlanTree plan={plans[activePlanIdx]} />}
```

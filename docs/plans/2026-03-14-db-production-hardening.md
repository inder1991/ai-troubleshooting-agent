# DB Diagnostics Production Hardening Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 12 production-readiness issues in the Database Diagnostics pipeline — connection resilience, real data collection, error handling, and safety guardrails.

**Architecture:** Backend-focused changes across adapters, graph agents, and frontend panel state handling. No infrastructure changes (no Redis, no new databases).

**Tech Stack:** Python (asyncio, asyncpg), TypeScript, React

---

## Stream A: PostgreSQL Adapter Hardening (Tasks 1-3)

### Task 1: Connection timeout + retry logic

**Files:**
- Modify: `backend/src/database/adapters/base.py`
- Modify: `backend/src/database/adapters/postgres.py`

**What:** Add connection timeout (10s default) and retry with exponential backoff (3 attempts) to `connect()`. Add query timeout (30s) to all diagnostic queries.

In `base.py`, add to `__init__`:
```python
self.connect_timeout = connect_timeout or 10
self.query_timeout = query_timeout or 30
```

In `postgres.py`, wrap `connect()`:
```python
async def connect(self) -> None:
    for attempt in range(3):
        try:
            self._conn = await asyncio.wait_for(
                asyncpg.connect(
                    host=self.host, port=self.port,
                    database=self.database,
                    user=self.username, password=self.password,
                    timeout=self.connect_timeout,
                ),
                timeout=self.connect_timeout + 2,
            )
            self._connected = True
            return
        except (asyncio.TimeoutError, Exception) as e:
            if attempt == 2:
                raise ConnectionError(f"Failed to connect after 3 attempts: {e}")
            await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
```

Add timeout to `execute_diagnostic_query`:
```python
async def execute_diagnostic_query(self, sql: str) -> QueryResult:
    result = await asyncio.wait_for(
        self._conn.fetch(sql),
        timeout=self.query_timeout,
    )
    ...
```

---

### Task 2: Permission pre-check

**Files:**
- Modify: `backend/src/database/adapters/base.py` (add abstract method)
- Modify: `backend/src/database/adapters/postgres.py`
- Modify: `backend/src/database/adapters/mock_adapter.py`
- Modify: `backend/src/agents/database/graph_v2.py` (connection_validator node)

**What:** Before running agents, verify the DB user has required permissions. Add `check_permissions()` method that tests access to `pg_stat_activity`, `pg_stat_user_tables`, `pg_stat_user_indexes`.

In `base.py`:
```python
async def check_permissions(self) -> dict:
    """Check if the connected user has required permissions. Returns {view_name: bool}."""
    raise NotImplementedError
```

In `postgres.py`:
```python
async def check_permissions(self) -> dict:
    checks = {
        'pg_stat_activity': 'SELECT 1 FROM pg_stat_activity LIMIT 1',
        'pg_stat_user_tables': 'SELECT 1 FROM pg_stat_user_tables LIMIT 1',
        'pg_stat_user_indexes': 'SELECT 1 FROM pg_stat_user_indexes LIMIT 1',
        'pg_stat_replication': 'SELECT 1 FROM pg_stat_replication LIMIT 0',
    }
    result = {}
    for view, sql in checks.items():
        try:
            await self._conn.fetch(sql)
            result[view] = True
        except Exception:
            result[view] = False
    return result
```

In `mock_adapter.py`:
```python
async def check_permissions(self) -> dict:
    return {
        'pg_stat_activity': True,
        'pg_stat_user_tables': True,
        'pg_stat_user_indexes': True,
        'pg_stat_replication': True,
    }
```

In `graph_v2.py` `connection_validator` node, after health check:
```python
    # Check permissions
    perms = await adapter.check_permissions()
    missing = [v for v, ok in perms.items() if not ok]
    if missing:
        if emitter:
            await emitter.emit("connection_validator", "warning",
                f"Missing access to: {', '.join(missing)}. Some diagnostics may be limited.")
```

---

### Task 3: pg_stat_statements + real index scan counts

**Files:**
- Modify: `backend/src/database/adapters/postgres.py`
- Modify: `backend/src/database/adapters/mock_adapter.py`
- Modify: `backend/src/agents/database/graph_v2.py`

**What:**

Add `get_slow_queries_from_stats()` to PostgresAdapter that queries `pg_stat_statements` for historical slow queries (if extension is available):
```python
async def get_slow_queries_from_stats(self) -> list[dict]:
    """Get top slow queries from pg_stat_statements. Returns [] if extension not available."""
    try:
        rows = await self._conn.fetch("""
            SELECT queryid, query, calls, mean_exec_time, total_exec_time,
                   rows, shared_blks_hit, shared_blks_read
            FROM pg_stat_statements
            ORDER BY mean_exec_time DESC
            LIMIT 10
        """)
        return [dict(r) for r in rows]
    except Exception:
        return []  # Extension not installed
```

Add real index scan counts to `get_table_detail()`:
```python
# In get_table_detail, query pg_stat_user_indexes for real scan counts:
idx_rows = await self._conn.fetch("""
    SELECT indexrelname, idx_scan, pg_relation_size(indexrelid) as size_bytes
    FROM pg_stat_user_indexes
    WHERE schemaname = $1 AND relname = $2
""", schema, table_name)
```

In `mock_adapter.py`, add mock version:
```python
async def get_slow_queries_from_stats(self) -> list[dict]:
    return [
        {"queryid": 1001, "query": "SELECT * FROM orders WHERE created_at > $1", "calls": 15420, "mean_exec_time": 245.5, "total_exec_time": 3789510.0, "rows": 89000, "shared_blks_hit": 45000, "shared_blks_read": 12000},
        {"queryid": 1002, "query": "UPDATE inventory SET stock = stock - 1 WHERE product_id = $1", "calls": 8900, "mean_exec_time": 89.2, "total_exec_time": 793880.0, "rows": 8900, "shared_blks_hit": 18000, "shared_blks_read": 2400},
        {"queryid": 1003, "query": "SELECT COUNT(*) FROM events GROUP BY event_type", "calls": 342, "mean_exec_time": 4521.0, "total_exec_time": 1546182.0, "rows": 342, "shared_blks_hit": 800, "shared_blks_read": 95000},
    ]
```

In `graph_v2.py` `query_analyst`, combine active queries with pg_stat_statements:
```python
    # Also check pg_stat_statements for historical slow queries
    if hasattr(adapter, 'get_slow_queries_from_stats'):
        stats_queries = await adapter.get_slow_queries_from_stats()
        if stats_queries and emitter:
            await emitter.emit("query_analyst", "reasoning",
                f"pg_stat_statements: {len(stats_queries)} historically slow queries found")
            for sq in stats_queries[:3]:
                await emitter.emit("query_analyst", "reasoning",
                    f"  avg {sq['mean_exec_time']:.0f}ms × {sq['calls']} calls — {sq['query'][:80]}...")
```

---

## Stream B: EXPLAIN + Error Handling (Tasks 4-6)

### Task 4: Add EXPLAIN ANALYZE for top slow query

**Files:**
- Modify: `backend/src/database/adapters/postgres.py`
- Modify: `backend/src/database/adapters/mock_adapter.py`
- Modify: `backend/src/agents/database/graph_v2.py`

**What:** Run `EXPLAIN (FORMAT JSON)` on the top slow query and emit the plan as `details.explain_plan`.

In `postgres.py`:
```python
async def explain_query(self, sql: str) -> dict | None:
    """Run EXPLAIN (FORMAT JSON) on a query. Returns plan node or None."""
    try:
        # Safety: only EXPLAIN, never EXPLAIN ANALYZE on production
        clean_sql = sql.strip().rstrip(';')
        rows = await asyncio.wait_for(
            self._conn.fetch(f"EXPLAIN (FORMAT JSON) {clean_sql}"),
            timeout=10,
        )
        if rows:
            plan = rows[0][0]
            return plan[0]["Plan"] if isinstance(plan, list) else plan
    except Exception:
        return None
```

In `mock_adapter.py`:
```python
async def explain_query(self, sql: str) -> dict | None:
    return {
        "Node Type": "Sort",
        "Startup Cost": 1250.5,
        "Total Cost": 1350.8,
        "Plan Rows": 5000,
        "Plans": [
            {
                "Node Type": "Seq Scan",
                "Relation Name": "orders",
                "Startup Cost": 0.0,
                "Total Cost": 1100.0,
                "Plan Rows": 120000,
                "Filter": "(created_at > (now() - '24:00:00'::interval))",
            }
        ],
    }
```

In `graph_v2.py` `query_analyst`, after finding slow queries:
```python
    # Run EXPLAIN on the worst slow query
    explain_plan = None
    if slow and hasattr(adapter, 'explain_query'):
        worst = slow[0]
        try:
            explain_plan = await adapter.explain_query(worst.query)
            if explain_plan and emitter:
                await emitter.emit("query_analyst", "reasoning",
                    f"EXPLAIN on worst query (pid:{worst.pid}): root node is {explain_plan.get('Node Type', '?')}")
        except Exception:
            pass
```

Then include in the finding event details:
```python
    await emitter.emit("query_analyst", "finding", ..., details={
        "slow_queries": slow_queries_data,
        "explain_plan": explain_plan,  # NEW
    })
```

---

### Task 5: Fix panel error state handling

**Files:**
- Modify: `frontend/src/components/Investigation/db-board/PanelZone.tsx`
- Modify: `frontend/src/components/Investigation/DatabaseWarRoom.tsx`

**What:** Add an `'error'` panel state. When an agent emits an error event, the panel should show "Error" instead of staying stuck at "Analyzing...".

In `PanelZone.tsx`, add `'error'` to `PanelState`:
```tsx
export type PanelState = 'dormant' | 'scanning' | 'lit' | 'error';
```

Add error state rendering after the scanning AnimatePresence block:
```tsx
{state === 'error' && (
  <motion.div
    key="error"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0 }}
    className="flex-1 flex items-center justify-center border border-red-500/20 rounded-lg bg-red-500/[0.03]"
  >
    <div className="flex items-center gap-1.5 text-[10px] text-red-400">
      <span className="material-symbols-outlined text-[14px]">error</span>
      Failed to collect data
    </div>
  </motion.div>
)}
```

In `DatabaseWarRoom.tsx`, update `derivePanelState` to detect errors:
```tsx
function derivePanelState(agentEvents: TaskEvent[], dataKey: string): PanelState {
  if (agentEvents.length === 0) return 'dormant';
  const hasFinding = agentEvents.some((e) => e.event_type === 'finding' && e.details?.[dataKey]);
  if (hasFinding) return 'lit';
  const hasError = agentEvents.some((e) => e.event_type === 'error');
  const isComplete = agentEvents.some((e) => e.event_type === 'success');
  if (hasError && !isComplete) return 'error';
  if (isComplete) return 'dormant';
  const hasActivity = agentEvents.some((e) => ['started', 'progress'].includes(e.event_type));
  if (hasActivity) return 'scanning';
  return 'dormant';
}
```

---

### Task 6: Single-node replication message + event size limits

**Files:**
- Modify: `frontend/src/components/Investigation/DatabaseWarRoom.tsx`
- Modify: `backend/src/agents/database/graph_v2.py`

**What:**

**Replication:** When health_analyst detects no replicas, show "Single node" instead of "Awaiting replication data":

In DatabaseWarRoom right column, update the replication section:
```tsx
{replication ? (
  replication.replicas && replication.replicas.length > 0 ? (
    <ReplicationTopologySVG ... />
  ) : (
    <div className="flex items-center gap-2 py-3 px-3 bg-duck-surface/20 rounded-lg">
      <span className="material-symbols-outlined text-slate-400 text-sm">dns</span>
      <span className="text-[10px] text-slate-400">Single node — no replication configured</span>
    </div>
  )
) : (
  <div className="flex items-center justify-center h-28 border border-dashed border-duck-border/30 rounded-lg">
    <span className="text-[10px] text-slate-400 italic">Awaiting replication data</span>
  </div>
)}
```

**Event size limits:** In `graph_v2.py`, truncate query text in events to prevent huge WS frames:
```python
# In query_analyst, when building slow_queries_data:
slow_queries_data = [{"pid": q.pid, "duration_ms": q.duration_ms, "query": q.query[:500]} for q in slow]

# In reasoning events, truncate query text:
await emitter.emit("query_analyst", "reasoning",
    f"[{sev}] pid:{q.pid} running {q.duration_ms/1000:.1f}s — {q.query[:100]}...")
```

---

## Stream C: Safety & MongoDB (Tasks 7-9)

### Task 7: SQL warnings in fix recommendations

**Files:**
- Modify: `backend/src/agents/database/graph_v2.py`

**What:** Add a `warning` field to each fix recommendation explaining the risk:

```python
# In the fix_recommendations builder:
if cat == "slow_query":
    sql = f"SELECT pg_terminate_backend({pid});"
    warning = "Terminates the query immediately. Active transactions will be rolled back."
elif cat == "bloat":
    sql = f"VACUUM FULL {table};"
    warning = "Locks the table for the duration. Schedule during maintenance window."
elif cat == "connections":
    sql = "ALTER SYSTEM SET max_connections = 200;\n..."
    warning = "Requires PostgreSQL restart to take effect. Plan for brief downtime."
elif cat == "memory":
    sql = "ALTER SYSTEM SET shared_buffers = '1GB';\n..."
    warning = "Requires PostgreSQL restart. Ensure server has enough RAM."
elif cat == "deadlock":
    sql = "-- Investigate current locks:\n..."
    warning = "Diagnostic query only. Review results before taking action."
elif cat == "replication":
    sql = "-- Check replication status:\n..."
    warning = "Diagnostic query only. Do not modify replication settings without DBA review."

fix_recommendations.append({
    ...,
    "warning": warning,
})
```

Update frontend `FixRecommendations.tsx` to show the warning:
```tsx
{fix.warning && (
  <p className="text-[9px] text-amber-400/70 mt-1 flex items-start gap-1">
    <span className="material-symbols-outlined text-[12px] shrink-0 mt-px">warning</span>
    {fix.warning}
  </p>
)}
```

---

### Task 8: MongoDB-specific reasoning

**Files:**
- Modify: `backend/src/agents/database/graph_v2.py`

**What:** When `engine === 'mongodb'`, agents should emit MongoDB-specific reasoning instead of PG-specific terms.

Add engine-aware messaging in health_analyst:
```python
if engine == 'mongodb':
    pool_term = 'connection pool (maxPoolSize)'
    cache_term = 'WiredTiger cache'
    lock_term = 'write conflicts'
else:
    pool_term = 'connection pool (max_connections)'
    cache_term = 'shared_buffers cache'
    lock_term = 'deadlocks'
```

Use these terms in reasoning events instead of hardcoded PG terms.

In the synthesizer SQL generation, add MongoDB equivalents:
```python
if engine == 'mongodb':
    if cat == "slow_query":
        sql = f"// Kill operation:\ndb.killOp({pid})"
    elif cat == "connections":
        sql = "// Check connections:\ndb.serverStatus().connections"
    elif cat == "memory":
        sql = "// Check cache:\ndb.serverStatus().wiredTiger.cache"
```

---

### Task 9: Scan cancellation support

**Files:**
- Modify: `backend/src/api/db_session_endpoints.py`
- Modify: `backend/src/api/routes_v4.py`
- Modify: `frontend/src/components/Investigation/DatabaseWarRoom.tsx`

**What:** Add a cancel endpoint and cancel button.

Backend — add cancel endpoint:
```python
@router_v4.post("/session/{session_id}/cancel")
async def cancel_session(session_id: str):
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["phase"] = "cancelled"
    # Signal the graph to stop via a shared flag
    session["_cancelled"] = True
    emitter = session.get("emitter")
    if emitter:
        await emitter.emit("supervisor", "warning", "Investigation cancelled by user")
    return {"status": "cancelled"}
```

Frontend — add cancel button to DatabaseWarRoom header when running:
```tsx
{phase && !['complete', 'error', 'cancelled'].includes(phase) && (
  <button
    onClick={handleCancel}
    className="text-[10px] text-slate-400 hover:text-red-400 transition-colors"
  >
    Cancel
  </button>
)}
```

---

## Stream D: Frontend Robustness (Tasks 10-12)

### Task 10: Large result pagination in IndexUsageMatrix + TableBloatHeatmap

**Files:**
- Modify: `frontend/src/components/Investigation/db-viz/IndexUsageMatrix.tsx`
- Modify: `frontend/src/components/Investigation/db-viz/TableBloatHeatmap.tsx`

**What:** Add a "Show more" pattern. Default show top 20 items, expandable.

Wrap the data with a limit:
```tsx
const [showAll, setShowAll] = useState(false);
const displayed = showAll ? indexes : indexes.slice(0, 20);

// After the table:
{indexes.length > 20 && !showAll && (
  <button onClick={() => setShowAll(true)} className="text-[10px] text-duck-accent mt-2">
    Show all {indexes.length} indexes
  </button>
)}
```

Same pattern for TableBloatHeatmap.

---

### Task 11: Add `'cancelled'` phase to frontend

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/Investigation/DatabaseWarRoom.tsx`

**What:** Add `'cancelled'` to `DiagnosticPhase` type. Show cancelled state in the header.

---

### Task 12: Add `warning` field to FixRecommendations display

**Files:**
- Modify: `frontend/src/components/Investigation/db-board/FixRecommendations.tsx`

**What:** Show the warning text below the SQL in each expanded fix. Amber text with warning icon.

```tsx
{fix.warning && (
  <p className="text-[9px] text-amber-400/70 mt-1.5 flex items-start gap-1">
    <span className="material-symbols-outlined text-[12px] shrink-0 mt-px" aria-hidden="true">warning</span>
    {fix.warning}
  </p>
)}
```

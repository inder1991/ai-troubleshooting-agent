# LLM-Powered Database Diagnostic Agents — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace heuristic rule-based database diagnostic agents with LLM-powered tool-calling agents (Haiku for extraction, Sonnet for synthesis) with production guardrails: tool policy enforcement, provenance linking, confidence calibration, SQL sanitization, and heuristic fallback.

**Architecture:** Create a ToolPolicyEnforcer + ToolCallExecutor layer that mediates between the LLM and database adapter tools. Each agent (query_analyst, health_analyst, schema_analyst) runs a ReAct tool-calling loop with max 5 iterations and 60s timeout. The DiagnosticOrchestrator runs agents in parallel, merges findings, validates provenance, calibrates confidence, then passes everything to a Sonnet-powered synthesizer for root cause correlation.

**Tech Stack:** Python 3.14, Anthropic SDK (AsyncAnthropic), LangGraph, asyncio, asyncpg

---

## Task 1: Add 5 new adapter methods (wait events, lock chains, long transactions, autovacuum, table access patterns)

**Files:**
- Modify: `backend/src/database/adapters/base.py`
- Modify: `backend/src/database/adapters/postgres.py`
- Modify: `backend/src/database/adapters/mock_adapter.py`

**Step 1: Add abstract methods to base.py**

Add these 5 methods to the `DatabaseAdapter` class after the existing `get_slow_queries_from_stats`:

```python
async def get_wait_events(self) -> list[dict]:
    """Get current wait events from pg_stat_activity. Returns [{wait_event_type, wait_event, count, pids}]."""
    return []

async def get_lock_chains(self) -> list[dict]:
    """Get blocking lock chains. Returns [{blocked_pid, blocked_query, blocking_pid, blocking_query}]."""
    return []

async def get_long_transactions(self) -> list[dict]:
    """Get transactions idle in transaction > 5 minutes. Returns [{pid, user, state, query, age_seconds}]."""
    return []

async def get_autovacuum_status(self) -> dict:
    """Get autovacuum progress and last vacuum times. Returns {running: [], stale: []}."""
    return {"running": [], "stale": []}

async def get_table_access_patterns(self) -> list[dict]:
    """Get sequential vs index scan ratios. Returns [{table, seq_scan, idx_scan, seq_ratio}]."""
    return []
```

**Step 2: Implement in postgres.py**

Add after `get_slow_queries_from_stats`:

```python
async def get_wait_events(self) -> list[dict]:
    try:
        rows = await asyncio.wait_for(self._conn.fetch("""
            SELECT wait_event_type, wait_event, count(*) as cnt,
                   array_agg(pid) as pids
            FROM pg_stat_activity
            WHERE wait_event IS NOT NULL AND pid != pg_backend_pid()
            GROUP BY wait_event_type, wait_event
            ORDER BY cnt DESC LIMIT 10
        """), timeout=self.query_timeout)
        return [dict(r) for r in rows]
    except Exception:
        return []

async def get_lock_chains(self) -> list[dict]:
    try:
        rows = await asyncio.wait_for(self._conn.fetch("""
            SELECT blocked.pid AS blocked_pid,
                   blocked.query AS blocked_query,
                   blocking.pid AS blocking_pid,
                   blocking.query AS blocking_query,
                   blocked.wait_event_type, blocked.wait_event
            FROM pg_stat_activity blocked
            JOIN pg_locks bl ON bl.pid = blocked.pid AND NOT bl.granted
            JOIN pg_locks blk ON blk.locktype = bl.locktype
                AND blk.database IS NOT DISTINCT FROM bl.database
                AND blk.relation IS NOT DISTINCT FROM bl.relation
                AND blk.granted
            JOIN pg_stat_activity blocking ON blocking.pid = blk.pid
            WHERE blocked.pid != pg_backend_pid()
            LIMIT 5
        """), timeout=self.query_timeout)
        return [dict(r) for r in rows]
    except Exception:
        return []

async def get_long_transactions(self) -> list[dict]:
    try:
        rows = await asyncio.wait_for(self._conn.fetch("""
            SELECT pid, usename AS user, state, query,
                   EXTRACT(EPOCH FROM now() - xact_start)::int AS age_seconds,
                   EXTRACT(EPOCH FROM now() - state_change)::int AS idle_seconds
            FROM pg_stat_activity
            WHERE xact_start IS NOT NULL
              AND state = 'idle in transaction'
              AND EXTRACT(EPOCH FROM now() - xact_start) > 300
              AND pid != pg_backend_pid()
            ORDER BY age_seconds DESC LIMIT 5
        """), timeout=self.query_timeout)
        return [dict(r) for r in rows]
    except Exception:
        return []

async def get_autovacuum_status(self) -> dict:
    result = {"running": [], "stale": []}
    try:
        running = await asyncio.wait_for(self._conn.fetch("""
            SELECT relid::regclass::text AS relname, phase,
                   heap_blks_total, heap_blks_scanned, heap_blks_vacuumed
            FROM pg_stat_progress_vacuum
        """), timeout=self.query_timeout)
        result["running"] = [dict(r) for r in running]

        stale = await asyncio.wait_for(self._conn.fetch("""
            SELECT relname, last_autovacuum, last_autoanalyze,
                   n_dead_tup, n_live_tup
            FROM pg_stat_user_tables
            WHERE n_dead_tup > 1000
            ORDER BY n_dead_tup DESC LIMIT 10
        """), timeout=self.query_timeout)
        result["stale"] = [dict(r) for r in stale]
    except Exception:
        pass
    return result

async def get_table_access_patterns(self) -> list[dict]:
    try:
        rows = await asyncio.wait_for(self._conn.fetch("""
            SELECT relname AS table_name, seq_scan, idx_scan,
                   seq_tup_read, idx_tup_fetch,
                   n_tup_ins, n_tup_upd, n_tup_del,
                   CASE WHEN seq_scan + idx_scan > 0
                        THEN round(seq_scan::numeric / (seq_scan + idx_scan), 2)
                        ELSE 0 END AS seq_scan_ratio
            FROM pg_stat_user_tables
            ORDER BY seq_scan DESC LIMIT 10
        """), timeout=self.query_timeout)
        return [dict(r) for r in rows]
    except Exception:
        return []
```

**Step 3: Implement in mock_adapter.py**

Add mock implementations returning realistic test data. Each returns 2-5 items with varied severity to test all UI paths.

```python
async def get_wait_events(self) -> list[dict]:
    return [
        {"wait_event_type": "Lock", "wait_event": "relation", "cnt": 5, "pids": [4201, 4202, 4205, 4206, 4207]},
        {"wait_event_type": "IO", "wait_event": "DataFileRead", "cnt": 3, "pids": [4203, 4208, 4209]},
        {"wait_event_type": "LWLock", "wait_event": "BufferMapping", "cnt": 2, "pids": [4210, 4211]},
    ]

async def get_lock_chains(self) -> list[dict]:
    return [
        {"blocked_pid": 4205, "blocked_query": "UPDATE orders SET status='shipped' WHERE id=9823",
         "blocking_pid": 4201, "blocking_query": "SELECT * FROM orders WHERE created_at > now() - interval '24h' FOR UPDATE",
         "wait_event_type": "Lock", "wait_event": "transactionid"},
    ]

async def get_long_transactions(self) -> list[dict]:
    return [
        {"pid": 4204, "user": "etl_worker", "state": "idle in transaction",
         "query": "INSERT INTO audit_log SELECT * FROM staging_audit",
         "age_seconds": 1847, "idle_seconds": 1800},
    ]

async def get_autovacuum_status(self) -> dict:
    return {
        "running": [],
        "stale": [
            {"relname": "audit_log", "last_autovacuum": "2026-03-10T08:00:00", "last_autoanalyze": "2026-03-10T08:01:00", "n_dead_tup": 892000, "n_live_tup": 5400000},
            {"relname": "orders", "last_autovacuum": "2026-03-12T14:00:00", "last_autoanalyze": "2026-03-12T14:01:00", "n_dead_tup": 245000, "n_live_tup": 1200000},
        ],
    }

async def get_table_access_patterns(self) -> list[dict]:
    return [
        {"table_name": "orders", "seq_scan": 45000, "idx_scan": 1200000, "seq_tup_read": 54000000, "idx_tup_fetch": 1200000, "n_tup_ins": 5000, "n_tup_upd": 12000, "n_tup_del": 200, "seq_scan_ratio": 0.04},
        {"table_name": "audit_log", "seq_scan": 890, "idx_scan": 120, "seq_tup_read": 4800000, "idx_tup_fetch": 120, "n_tup_ins": 50000, "n_tup_upd": 0, "n_tup_del": 0, "seq_scan_ratio": 0.88},
        {"table_name": "events", "seq_scan": 342, "idx_scan": 0, "seq_tup_read": 18000000, "idx_tup_fetch": 0, "n_tup_ins": 100000, "n_tup_upd": 0, "n_tup_del": 5000, "seq_scan_ratio": 1.0},
    ]
```

**Step 4: Verify**
```bash
cd backend && python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ['src/database/adapters/base.py', 'src/database/adapters/postgres.py', 'src/database/adapters/mock_adapter.py']]"
```

**Step 5: Commit**
```bash
git add backend/src/database/adapters/
git commit -m "feat(db): add 5 new diagnostic adapter methods (wait events, locks, long txn, autovacuum, access patterns)"
```

---

## Task 2: Create Tool Policy Engine

**Files:**
- Create: `backend/src/agents/database/tool_policy.py`

**Step 1: Create the file**

This file contains: `ToolPolicyEnforcer`, `ToolCallRecord`, `ToolResult`, `ToolCallExecutor`, `sanitize_sql_for_explain`, and the `TOOL_POLICIES` dict.

See the design doc (`docs/plans/2026-03-14-llm-agent-upgrade-design.md`) for the complete code of:
- `TOOL_POLICIES` dict with all 3 agents and their 13 tools
- `ToolPolicyEnforcer` class with `validate()` and `record()` methods
- `ToolCallRecord` dataclass for audit trail
- `ToolResult` dataclass for size-controlled results
- `sanitize_sql_for_explain()` function
- `FORBIDDEN_PATTERNS` regex
- `ToolCallExecutor` class with `process_response()`, `_execute_tool_call()`, `_format_result()`, `_looks_like_tool_call()`

The `_format_result()` method must apply the per-tool item limits from the design doc table (10 for queries, 5 for lock chains, etc.).

**Step 2: Verify**
```bash
cd backend && python3 -c "import py_compile; py_compile.compile('src/agents/database/tool_policy.py', doraise=True)"
```

**Step 3: Commit**
```bash
git add backend/src/agents/database/tool_policy.py
git commit -m "feat(db): add ToolPolicyEnforcer + ToolCallExecutor with audit trail"
```

---

## Task 3: Create Tool Definitions (Anthropic schema)

**Files:**
- Create: `backend/src/agents/database/tool_definitions.py`

**Step 1: Create Anthropic tool schemas**

Define tool schemas in the format Anthropic's API expects. Each tool has: name, description, input_schema (JSON Schema).

```python
QUERY_ANALYST_TOOLS = [
    {
        "name": "get_active_queries",
        "description": "Get currently running queries. Returns top 10 by duration with pid, query text, duration_ms, state, user, waiting flag.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_slow_queries_from_stats",
        "description": "Get historically slow queries from pg_stat_statements. Returns top 10 by mean execution time with queryid, query, calls, mean_exec_time, total_exec_time, rows.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "explain_query",
        "description": "Run EXPLAIN (FORMAT JSON) on a SELECT query. Returns the query plan tree with node types, costs, and row estimates. Only accepts SELECT queries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "The SELECT query to explain"}
            },
            "required": ["sql"],
        },
    },
    {
        "name": "get_wait_events",
        "description": "Get current wait events showing what queries are waiting on (IO, Lock, LWLock, etc). Returns top 10 wait events with count and affected pids.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_long_transactions",
        "description": "Get transactions idle in transaction for more than 5 minutes. These block VACUUM and hold locks. Returns pid, user, query, age in seconds.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

HEALTH_ANALYST_TOOLS = [
    {
        "name": "get_connection_pool",
        "description": "Get connection pool snapshot: active, idle, waiting, max_connections counts and utilization percentage.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_performance_stats",
        "description": "Get database performance metrics: cache_hit_ratio, transactions_per_sec, deadlocks, uptime_seconds.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_replication_status",
        "description": "Get replication topology: is_replica flag, list of replicas with lag_seconds and state.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_lock_chains",
        "description": "Get blocking lock chains: which PIDs are blocking which other PIDs, with query text for both sides.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_autovacuum_status",
        "description": "Get autovacuum status: currently running vacuums with progress, and tables with stale vacuum (high dead tuples).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

SCHEMA_ANALYST_TOOLS = [
    {
        "name": "get_schema_snapshot",
        "description": "Get database schema overview: top 20 tables by size with row counts and sizes, plus index list.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_table_detail",
        "description": "Get detailed info for one table: columns, indexes with scan counts, bloat ratio, row estimate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Name of the table to inspect"}
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "get_table_access_patterns",
        "description": "Get sequential vs index scan ratios for top tables. High seq_scan_ratio suggests missing indexes.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

# Finding output schema — LLM must output findings in this format
FINDING_OUTPUT_TOOL = {
    "name": "report_findings",
    "description": "Report your diagnostic findings. Call this when you've completed your analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["title", "severity", "category", "detail", "confidence", "evidence_sources", "recommendation", "remediation_sql", "remediation_warning"],
                    "properties": {
                        "title": {"type": "string"},
                        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                        "category": {"type": "string", "enum": ["slow_query", "lock", "replication", "connections", "storage", "schema", "index_candidate", "memory", "configuration", "deadlock", "bloat", "long_transaction", "wait_event", "autovacuum"]},
                        "detail": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "evidence_sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["tool_call_id", "data_snippet"],
                                "properties": {
                                    "tool_call_id": {"type": "string"},
                                    "data_snippet": {"type": "string"},
                                }
                            }
                        },
                        "recommendation": {"type": "string"},
                        "remediation_sql": {"type": "string"},
                        "remediation_warning": {"type": "string"},
                        "related_findings": {"type": "array", "items": {"type": "string"}},
                    }
                }
            }
        },
        "required": ["findings"],
    },
}
```

**Step 2: Commit**
```bash
git add backend/src/agents/database/tool_definitions.py
git commit -m "feat(db): add Anthropic tool schemas for 13 diagnostic tools + finding output schema"
```

---

## Task 4: Create Agent System Prompts

**Files:**
- Create: `backend/src/agents/database/prompts.py`

**Step 1: Create prompts file**

Contains system prompts for each agent and the synthesizer. See the design doc for full prompt text. Key requirements:

- Engine-aware: prompts adjust for PostgreSQL vs MongoDB
- Tool-calling instructions: tell the LLM to use tools, not speculate
- Evidence requirement: "cite tool_call_id for every finding"
- Output format: "call report_findings tool with structured findings"
- Guardrail instructions: "only use provided tools, do not attempt SQL directly"

Include: `QUERY_ANALYST_PROMPT`, `HEALTH_ANALYST_PROMPT`, `SCHEMA_ANALYST_PROMPT`, `SYNTHESIZER_PROMPT` (all parameterized by engine type).

**Step 2: Commit**
```bash
git add backend/src/agents/database/prompts.py
git commit -m "feat(db): add agent system prompts with engine-aware instructions"
```

---

## Task 5: Create LLM Agent Loop

**Files:**
- Create: `backend/src/agents/database/llm_agents.py`

**Step 1: Create the ReAct agent loop**

This is the core LLM tool-calling loop used by all 3 extraction agents:

```python
async def run_llm_agent(
    agent_name: str,
    adapter: DatabaseAdapter,
    emitter: EventEmitter,
    engine: str,
    tools: list[dict],          # Anthropic tool schemas
    system_prompt: str,
    context: dict,              # Profile info, focus areas, etc.
    max_iterations: int = 5,
    timeout: float = 60.0,
) -> tuple[list[DBFindingV2], list[ToolCallRecord]]:
```

The loop:
1. Create `ToolPolicyEnforcer` and `ToolCallExecutor` for this agent
2. Build initial messages with context
3. Call `AnthropicClient.chat_with_tools()` with system prompt + tools + messages
4. For each response:
   - Text blocks → emit as `reasoning` events
   - `tool_use` blocks → validate via policy → execute → add result to messages
   - `report_findings` tool call → parse findings, validate provenance, return
5. If max iterations reached without `report_findings`, emit warning and return empty
6. On any exception, return empty findings (caller will use heuristic fallback)

**Key:** The `report_findings` tool is how the LLM outputs structured findings. It's a "virtual tool" — not executed against the adapter, just parsed.

**Step 2: Commit**
```bash
git add backend/src/agents/database/llm_agents.py
git commit -m "feat(db): add ReAct LLM agent loop with tool policy enforcement"
```

---

## Task 6: Create Diagnostic Orchestrator + Findings Merger

**Files:**
- Create: `backend/src/agents/database/orchestrator.py`

**Step 1: Create orchestrator**

```python
class DiagnosticOrchestrator:
    async def run(self, state: DBDiagnosticStateV2) -> DBDiagnosticStateV2:
        # 1. connection_validator (no LLM)
        # 2. context_loader (no LLM)
        # 3. Run 3 LLM agents in parallel with 60s timeout each, 120s total
        # 4. Heuristic fallback for any failed agent
        # 5. FindingsMerger.merge() — deduplicate by title similarity
        # 6. validate_provenance() — verify evidence sources
        # 7. calibrate_confidence() — adjust by evidence quality
        # 8. root_cause_synthesizer() — Sonnet call
        # 9. Return updated state with dossier + fix_recommendations
```

Include `FindingsMerger` class with deduplication by normalized title.
Include `validate_provenance()` function.
Include `calibrate_confidence()` function.

**Step 2: Commit**
```bash
git add backend/src/agents/database/orchestrator.py
git commit -m "feat(db): add DiagnosticOrchestrator with parallel agents + FindingsMerger"
```

---

## Task 7: Create LLM-Powered Synthesizer

**Files:**
- Create: `backend/src/agents/database/synthesizer_llm.py`

**Step 1: Create Sonnet-powered synthesizer**

```python
async def root_cause_synthesizer(
    state: DBDiagnosticStateV2,
    all_findings: list[DBFindingV2],
) -> DBDiagnosticStateV2:
```

This function:
1. Builds a prompt with: all findings as JSON, database context (engine, version, server config), profile info
2. Calls Sonnet via `AnthropicClient.chat()` with `SYNTHESIZER_PROMPT`
3. Parses structured JSON response: root_cause, causal_chain, evidence_weight_map, alternative_hypotheses, remediation_plan, prevention_measures
4. Builds the 7-section dossier from LLM output
5. Generates fix_recommendations with context-aware SQL from LLM
6. Emits `synthesizer:success` event with summary
7. Falls back to deterministic synthesizer (current code) if LLM fails

**Step 2: Commit**
```bash
git add backend/src/agents/database/synthesizer_llm.py
git commit -m "feat(db): add Sonnet-powered root cause synthesizer with causal chains"
```

---

## Task 8: Update models (EvidenceSource, updated DBFindingV2)

**Files:**
- Modify: `backend/src/database/models.py`

**Step 1: Add EvidenceSource model and update DBFindingV2**

```python
class EvidenceSource(BaseModel):
    tool_call_id: str
    tool_name: str
    data_snippet: str
    truncated: bool = False

# Update DBFindingV2 to include:
# evidence_sources: list[EvidenceSource] = []
# related_findings: list[str] = []
# remediation_sql: str = ""
# remediation_warning: str = ""
```

**Step 2: Commit**
```bash
git add backend/src/database/models.py
git commit -m "feat(db): add EvidenceSource model + provenance fields on DBFindingV2"
```

---

## Task 9: Wire orchestrator into graph_v2.py

**Files:**
- Modify: `backend/src/agents/database/graph_v2.py`

**Step 1: Replace heuristic nodes with orchestrator**

Keep `connection_validator` and `context_loader` as-is (no LLM needed).

Replace the 3 heuristic agent nodes (`query_analyst`, `health_analyst`, `schema_analyst`) and `synthesizer` with calls to the orchestrator.

The graph structure changes from 6 nodes to:
```
connection_validator → context_loader → orchestrator_node → END
```

Where `orchestrator_node` internally runs:
1. 3 LLM agents in parallel (with heuristic fallback)
2. FindingsMerger
3. Provenance validation
4. Confidence calibration
5. LLM synthesizer

Keep the old heuristic functions (renamed with `_heuristic` suffix) as fallbacks.

**Step 2: Commit**
```bash
git add backend/src/agents/database/graph_v2.py
git commit -m "feat(db): wire DiagnosticOrchestrator into LangGraph, keep heuristic fallback"
```

---

## Task 10: Update db_session_endpoints to use orchestrator

**Files:**
- Modify: `backend/src/api/db_session_endpoints.py`

**Step 1: Update run_db_diagnosis**

The `run_db_diagnosis` function should use the orchestrator instead of directly invoking the graph. The orchestrator handles the full pipeline including LLM agents.

If `ANTHROPIC_API_KEY` is not set, automatically use heuristic-only mode (no LLM calls).

**Step 2: Commit**
```bash
git add backend/src/api/db_session_endpoints.py
git commit -m "feat(db): use DiagnosticOrchestrator in session endpoint, auto-detect LLM availability"
```

---

## Task 11: Update frontend to show provenance + evidence weights

**Files:**
- Modify: `frontend/src/components/Investigation/db-board/RootCauseVerdict.tsx`
- Modify: `frontend/src/components/Investigation/db-board/FixRecommendations.tsx`
- Modify: `frontend/src/components/Investigation/db-board/CaseFile.tsx`

**Step 1: RootCauseVerdict — show causal chain + evidence weights**

Add rendering for:
- `causal_chain` — ordered list of cause → effect steps
- `evidence_weight_map` — horizontal bar showing which findings contributed what weight
- `alternative_hypotheses` — collapsible section

**Step 2: FixRecommendations — show provenance**

Each fix now has `evidence_sources`. Show a small "Evidence" link that expands to show which tool calls support this finding.

**Step 3: CaseFile — show tool calls in agent sections**

When an agent emits `progress` events for tool calls, show them as distinct entries (not just reasoning text):
```
  🔧 get_active_queries() → 10 results
  💭 "3 queries exceed 5s threshold..."
  🔧 explain_query(SELECT...) → Seq Scan
  💭 "Missing index on orders.created_at..."
```

**Step 4: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```

**Step 5: Commit**
```bash
git add frontend/src/components/Investigation/db-board/
git commit -m "feat(db): show causal chains, evidence weights, and tool provenance in UI"
```

---

## Task 12: End-to-end verification

**Step 1: Backend syntax check**
```bash
cd backend && python3 -c "
import py_compile
files = [
    'src/agents/database/tool_policy.py',
    'src/agents/database/tool_definitions.py',
    'src/agents/database/prompts.py',
    'src/agents/database/llm_agents.py',
    'src/agents/database/orchestrator.py',
    'src/agents/database/synthesizer_llm.py',
    'src/agents/database/graph_v2.py',
    'src/database/adapters/base.py',
    'src/database/adapters/postgres.py',
    'src/database/adapters/mock_adapter.py',
    'src/database/models.py',
    'src/api/db_session_endpoints.py',
]
for f in files:
    py_compile.compile(f, doraise=True)
    print(f'✓ {f}')
"
```

**Step 2: Frontend TypeScript check**
```bash
cd frontend && npx tsc --noEmit
```

**Step 3: Test with mock adapter (no API key)**
- Start backend without `ANTHROPIC_API_KEY`
- Should fall back to heuristic mode automatically
- Verify Investigation Board still works

**Step 4: Test with API key (LLM mode)**
- Set `ANTHROPIC_API_KEY` in environment
- Start backend
- Run a DB diagnostic against mock profile
- Verify CaseFile shows LLM reasoning (not just heuristic messages)
- Verify Root Cause shows causal chain
- Verify Fix Recommendations show context-aware SQL

**Step 5: Final commit**
```bash
git add -A
git commit -m "feat(db): LLM-powered diagnostic agents with production guardrails — complete"
```

# LLM-Powered Database Diagnostic Agents — Design Document

## Overview

Upgrade the database diagnostic pipeline from heuristic rule-based agents to LLM-powered tool-calling agents with production guardrails. Each extraction agent (query_analyst, health_analyst, schema_analyst) becomes a ReAct-style agent using Haiku with read-only database tools. The synthesizer uses Sonnet for root cause correlation and dossier generation.

## Goals

1. **Agents reason adaptively** — LLM decides which tools to call based on context, not hardcoded rules
2. **Cross-agent correlation** — synthesizer identifies causal chains across agent findings
3. **Production-safe** — tool policy enforcement, SQL sanitization, result size limits, heuristic fallback
4. **Auditable** — full tool call log with provenance linking from findings to evidence
5. **Dynamic recommendations** — context-aware SQL based on actual server config, not templates
6. **5 new diagnostic dimensions** — wait events, lock chains, long transactions, autovacuum status, table access patterns

## Architecture

```
                    DiagnosticOrchestrator
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
  query_analyst      health_analyst     schema_analyst
  (Haiku + 5 tools)  (Haiku + 5 tools)  (Haiku + 3 tools)
        │                  │                  │
        │    ToolPolicyEnforcer (per agent)    │
        │    ToolCallExecutor (structured)     │
        │    ToolCallRecord[] (audit log)      │
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
                    FindingsMerger
                    (deduplicate, validate provenance)
                           │
                           ▼
                    RootCauseSynthesizer (Sonnet)
                    (causal chains, evidence weights)
                           │
                           ▼
                    Dossier + Fixes + Events
```

## Component Design

### 1. Tool Policy Engine

Controls which tools each agent can call, in what order, and how many times.

```python
TOOL_POLICIES = {
    "query_analyst": {
        "get_active_queries": {"allowed_anytime": True, "max_calls": 1},
        "get_slow_queries_from_stats": {"allowed_anytime": True, "max_calls": 1},
        "explain_query": {
            "requires_any": ["get_active_queries", "get_slow_queries_from_stats"],
            "max_calls": 3,
        },
        "get_wait_events": {
            "requires_any": ["get_active_queries"],
            "max_calls": 1,
        },
        "get_long_transactions": {"allowed_anytime": True, "max_calls": 1},
    },
    "health_analyst": {
        "get_connection_pool": {"allowed_anytime": True, "max_calls": 1},
        "get_performance_stats": {"allowed_anytime": True, "max_calls": 1},
        "get_replication_status": {"allowed_anytime": True, "max_calls": 1},
        "get_lock_chains": {
            "requires_any": ["get_active_queries", "get_performance_stats"],
            "max_calls": 1,
        },
        "get_autovacuum_status": {"allowed_anytime": True, "max_calls": 1},
    },
    "schema_analyst": {
        "get_schema_snapshot": {"allowed_anytime": True, "max_calls": 1},
        "get_table_detail": {
            "requires": ["get_schema_snapshot"],
            "max_calls": 5,
        },
        "get_table_access_patterns": {
            "requires": ["get_schema_snapshot"],
            "max_calls": 1,
        },
    },
}
```

**Enforcement:**
- Reject tool calls that violate policy (missing dependency, exceeded max)
- Log rejections for audit
- Return rejection reason to LLM so it can adjust

### 2. Structured Tool-Call Interface

LLM communicates ONLY through Anthropic's native `tool_use` blocks.

**ToolCallExecutor responsibilities:**
- Parse `tool_use` blocks from LLM response
- Validate via ToolPolicyEnforcer before execution
- Execute tool with 30s timeout
- Format result as ToolResult (summary + limited data)
- Record ToolCallRecord for audit trail
- Detect and reject free-text tool attempts (log for training)

**ToolCallRecord (audit):**
```python
@dataclass
class ToolCallRecord:
    call_id: str              # Anthropic tool_use_id
    tool_name: str
    args: dict
    status: str               # "success" | "rejected" | "timeout" | "error"
    reason: str = ""
    result_summary: str = ""
    result_count: int = 0
    truncated: bool = False
    timestamp: str = ""
```

### 3. Tool Result Size Control

Every tool returns summary + top N items:

| Tool | Max Items | Summary Fields |
|---|---|---|
| get_active_queries | 10 | total_count, slow_count, avg_duration |
| get_slow_queries_from_stats | 10 | total_count, worst_avg_ms |
| explain_query | 1 plan | node_type, cost, rows |
| get_wait_events | 10 | total_count, top_wait_type |
| get_long_transactions | 5 | total_count, oldest_age |
| get_connection_pool | 1 snapshot | utilization_pct |
| get_lock_chains | 5 chains | total_blocked, deepest_chain |
| get_autovacuum_status | 5 tables | running_count, oldest |
| get_schema_snapshot | 20 tables | total_tables, total_size |
| get_table_detail | 1 table | bloat_pct, index_count |
| get_table_access_patterns | 10 tables | total_seq_scans |

### 4. SQL Sanitization

```python
FORBIDDEN_PATTERNS = re.compile(
    r'\b(DROP|DELETE|TRUNCATE|ALTER\s+TABLE|INSERT|UPDATE|CREATE|GRANT|REVOKE)\b',
    re.IGNORECASE
)

def sanitize_sql_for_explain(sql: str) -> str | None:
    clean = sql.strip().rstrip(';')
    if FORBIDDEN_PATTERNS.search(clean):
        return None
    if not clean.upper().startswith('SELECT'):
        return None
    return clean
```

### 5. Agent System Prompts

**query_analyst (Haiku):**
```
You are a PostgreSQL query performance specialist. You have read-only access to a live database through diagnostic tools.

Your job: Investigate query performance issues methodically.

Approach:
1. Start with get_active_queries() to see what's running now
2. Check get_slow_queries_from_stats() for historical patterns
3. For the worst queries, use explain_query() to understand WHY they're slow
4. Check get_wait_events() if queries are waiting on something
5. Check get_long_transactions() for transactions holding resources

For each issue found, report a finding with:
- Clear title
- Severity (critical/high/medium/low)
- Evidence from specific tool calls (cite tool_call_id)
- Confidence (0.0-1.0)
- Specific remediation SQL

Be precise. Don't speculate without evidence. If data is truncated, note it.
```

**health_analyst (Haiku):**
```
You are a PostgreSQL health and infrastructure specialist. You have read-only access to a live database through diagnostic tools.

Your job: Assess database health across connections, performance, replication, and locking.

Approach:
1. Check get_connection_pool() for pool saturation
2. Check get_performance_stats() for cache, TPS, deadlocks
3. Check get_replication_status() for replica lag
4. If deadlocks or high contention, check get_lock_chains()
5. Check get_autovacuum_status() for vacuum health

For each issue, explain WHY it matters (not just "value > threshold").
Correlate findings: is pool saturation caused by slow queries? Is bloat caused by autovacuum not running?
```

**schema_analyst (Haiku):**
```
You are a PostgreSQL schema and storage specialist. You have read-only access to a live database through diagnostic tools.

Your job: Analyze schema health, index efficiency, and storage bloat.

Approach:
1. Start with get_schema_snapshot() for overview
2. For the largest/most bloated tables, use get_table_detail()
3. Check get_table_access_patterns() for sequential vs index scan ratios

Focus on:
- Tables with high bloat ratio (>15%)
- Unused indexes (scan_count = 0) — wasting space and slowing writes
- Missing indexes — tables with high sequential scan ratio
- Oversized tables that may need partitioning
```

### 6. Finding Schema with Provenance

```python
class EvidenceSource(BaseModel):
    tool_call_id: str
    tool_name: str
    data_snippet: str
    truncated: bool = False

class DBFindingV2(BaseModel):
    finding_id: str
    agent: str
    category: Literal[
        "slow_query", "lock", "replication", "connections",
        "storage", "schema", "index_candidate", "memory",
        "configuration", "deadlock", "bloat", "long_transaction",
        "wait_event", "autovacuum",
    ]
    title: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence_raw: float
    confidence_calibrated: float
    detail: str
    evidence: list[str]
    evidence_sources: list[EvidenceSource]   # Provenance
    recommendation: str
    remediation_sql: str
    remediation_warning: str
    remediation_available: bool
    rule_check: str
    related_findings: list[str]             # Cross-agent correlation
    meta: dict = {}
```

### 7. Provenance Validation

After LLM outputs findings, verify each `tool_call_id` exists in the call log:

```python
def validate_provenance(findings, call_log):
    valid_ids = {r.call_id for r in call_log if r.status == "success"}
    for finding in findings:
        unverified = [s for s in finding.evidence_sources if s.tool_call_id not in valid_ids]
        if unverified:
            finding.confidence_calibrated *= 0.5
            finding.meta["provenance_warning"] = f"{len(unverified)} unverifiable sources"
    return findings
```

### 8. Confidence Calibration

Rule-based calibration (Phase 1):

```python
def calibrate_confidence(finding, call_log):
    raw = finding.confidence_raw
    source_count = len(finding.evidence_sources)
    if source_count == 0: return raw * 0.3
    elif source_count == 1: raw *= 0.8
    truncated_sources = sum(1 for s in finding.evidence_sources if s.truncated)
    if truncated_sources > 0: raw *= 0.9
    if finding.meta.get("provenance_warning"): raw *= 0.5
    if finding.related_findings: raw = min(raw * 1.15, 0.99)
    return round(min(max(raw, 0.05), 0.99), 2)
```

Future: Historical calibration with Brier score from user feedback.

### 9. Root Cause Synthesizer (Sonnet)

Single LLM call with all merged findings + database context.

**Required output fields:**
- `root_cause.causal_chain` — ordered list of cause → effect relationships
- `root_cause.evidence_weight_map` — which findings contribute what weight to confidence (must sum to 1.0)
- `alternative_hypotheses` — other possible explanations with evidence for/against
- `remediation_plan` — prioritized actions with context-aware SQL
- `prevention_measures` — with cadence and rationale

### 10. Diagnostic Orchestrator

```python
class DiagnosticOrchestrator:
    async def run(self, state):
        # 1. Validate connection
        state = await connection_validator(state)
        if not state["connected"]: return state

        # 2. Load context
        state = await context_loader(state)

        # 3. Run agents in parallel (120s total timeout)
        results = await asyncio.wait_for(
            asyncio.gather(
                self._run_agent("query_analyst", state),
                self._run_agent("health_analyst", state),
                self._run_agent("schema_analyst", state),
                return_exceptions=True,
            ),
            timeout=120,
        )

        # 4. Merge + deduplicate findings
        all_findings = FindingsMerger.merge(results)

        # 5. Validate provenance
        all_findings = validate_provenance(all_findings, self.all_call_records)

        # 6. Calibrate confidence
        for f in all_findings:
            f.confidence_calibrated = calibrate_confidence(f, self.all_call_records)

        # 7. Synthesize root cause (Sonnet)
        state = await root_cause_synthesizer(state, all_findings)

        return state

    async def _run_agent(self, name, state):
        try:
            return await asyncio.wait_for(
                self._llm_agent(name, state), timeout=60)
        except Exception as e:
            # Fallback to heuristic
            await state["_emitter"].emit(name, "warning",
                f"LLM timed out, using heuristic: {e}")
            return await self._heuristic_agent(name, state)
```

### 11. New Adapter Methods (5 new tools)

**get_wait_events():**
```sql
SELECT wait_event_type, wait_event, count(*), array_agg(pid)
FROM pg_stat_activity
WHERE wait_event IS NOT NULL AND pid != pg_backend_pid()
GROUP BY wait_event_type, wait_event
ORDER BY count DESC LIMIT 10
```

**get_lock_chains():**
```sql
SELECT blocked.pid, blocked.query, blocking.pid AS blocking_pid, blocking.query AS blocking_query,
       blocked.wait_event_type, blocked.wait_event
FROM pg_stat_activity blocked
JOIN pg_locks bl ON bl.pid = blocked.pid AND NOT bl.granted
JOIN pg_locks blk ON blk.locktype = bl.locktype AND blk.database IS NOT DISTINCT FROM bl.database
     AND blk.relation IS NOT DISTINCT FROM bl.relation AND blk.granted
JOIN pg_stat_activity blocking ON blocking.pid = blk.pid
WHERE blocked.pid != pg_backend_pid()
LIMIT 5
```

**get_long_transactions():**
```sql
SELECT pid, usename, state, query,
       EXTRACT(EPOCH FROM now() - xact_start) AS age_seconds,
       EXTRACT(EPOCH FROM now() - state_change) AS idle_seconds
FROM pg_stat_activity
WHERE xact_start IS NOT NULL AND state = 'idle in transaction'
      AND EXTRACT(EPOCH FROM now() - xact_start) > 300
      AND pid != pg_backend_pid()
ORDER BY age_seconds DESC LIMIT 5
```

**get_autovacuum_status():**
```sql
-- Currently running autovacuums
SELECT relname, phase, heap_blks_total, heap_blks_scanned, heap_blks_vacuumed
FROM pg_stat_progress_vacuum;

-- Last autovacuum per table
SELECT relname, last_autovacuum, last_autoanalyze, n_dead_tup, n_live_tup
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC LIMIT 10;
```

**get_table_access_patterns():**
```sql
SELECT relname, seq_scan, idx_scan, seq_tup_read, idx_tup_fetch,
       n_tup_ins, n_tup_upd, n_tup_del,
       CASE WHEN seq_scan + idx_scan > 0
            THEN round(seq_scan::numeric / (seq_scan + idx_scan), 2)
            ELSE 0 END AS seq_scan_ratio
FROM pg_stat_user_tables
ORDER BY seq_scan DESC LIMIT 10
```

### 12. Heuristic Fallback

When LLM fails, each agent falls back to the current rule-based logic. The fallback findings get `meta.source = "heuristic"` and lower default confidence (0.7 instead of LLM's assessed confidence).

### 13. Models

| Component | Model | Cost/call | Timeout |
|---|---|---|---|
| query_analyst | claude-haiku-4-5-20251001 | ~$0.002 | 60s |
| health_analyst | claude-haiku-4-5-20251001 | ~$0.002 | 60s |
| schema_analyst | claude-haiku-4-5-20251001 | ~$0.002 | 60s |
| synthesizer | claude-sonnet-4-20250514 | ~$0.02 | 60s |
| **Total per scan** | | **~$0.03** | **~120s** |

### 14. Event Emission During LLM Loop

Each LLM text response block is emitted as a `reasoning` event in real-time:

```python
for block in response.content:
    if block.type == "text":
        await emitter.emit(agent_name, "reasoning", block.text)
    elif block.type == "tool_use":
        await emitter.emit(agent_name, "progress",
            f"Calling {block.name}({json.dumps(block.input)[:100]})")
```

This populates the CaseFile left column with live LLM thinking.

## Files to Create/Modify

**New files:**
- `backend/src/agents/database/tool_policy.py` — ToolPolicyEnforcer, ToolCallExecutor, ToolCallRecord
- `backend/src/agents/database/tool_definitions.py` — Anthropic tool schemas for all 13 tools
- `backend/src/agents/database/llm_agents.py` — LLM agent loop per agent type
- `backend/src/agents/database/orchestrator.py` — DiagnosticOrchestrator, FindingsMerger
- `backend/src/agents/database/prompts.py` — System prompts per agent + synthesizer

**Modified files:**
- `backend/src/database/adapters/base.py` — 5 new abstract methods
- `backend/src/database/adapters/postgres.py` — 5 new implementations
- `backend/src/database/adapters/mock_adapter.py` — 5 new mock implementations
- `backend/src/database/models.py` — EvidenceSource model, updated DBFindingV2
- `backend/src/agents/database/graph_v2.py` — Replace node functions with orchestrator calls
- `backend/src/api/db_session_endpoints.py` — Use orchestrator instead of direct graph

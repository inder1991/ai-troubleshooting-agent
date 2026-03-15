"""Anthropic API tool schemas for database diagnostic agents.

Each tool follows the Anthropic tool format:
    {"name": str, "description": str, "input_schema": {JSON Schema}}

Tools are grouped by specialist agent. The FINDING_OUTPUT_TOOL is shared
across all agents for structured output.
"""

# ── Query Analyst Tools (5) ──

QUERY_ANALYST_TOOLS: list[dict] = [
    {
        "name": "get_active_queries",
        "description": (
            "Get the top 10 currently running queries from pg_stat_activity. "
            "Returns pid, duration_ms, state (active/idle in transaction), "
            "wait_event_type, and truncated SQL. Use this FIRST to see what the "
            "database is doing right now."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_slow_queries_from_stats",
        "description": (
            "Get the top 10 historically slowest queries from pg_stat_statements, "
            "ordered by total_exec_time. Returns queryid, query text, calls, "
            "total_exec_time, mean_exec_time, rows, shared_blks_hit, and "
            "shared_blks_read. High mean_exec_time (>1s) or low hit ratio "
            "(shared_blks_hit / (hit + read)) indicates trouble."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "explain_query",
        "description": (
            "Run EXPLAIN (FORMAT JSON) on a SQL query to get its execution plan. "
            "Returns the planner's chosen strategy: Seq Scan vs Index Scan, "
            "join methods, estimated rows vs actual cost. Use this on the worst "
            "queries from get_active_queries or get_slow_queries_from_stats to "
            "understand WHY they are slow. Look for Seq Scans on large tables, "
            "nested loops with high row estimates, and Sort operations spilling "
            "to disk."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SQL query to explain. Do NOT include EXPLAIN prefix — it is added automatically.",
                },
            },
            "required": ["sql"],
        },
    },
    {
        "name": "get_wait_events",
        "description": (
            "Get aggregated wait event counts from pg_stat_activity grouped by "
            "wait_event_type and wait_event. Reveals what queries are waiting on: "
            "Lock (row/table locks), IO (disk reads), LWLock (internal buffers), "
            "Client (waiting for client response), or IPC (inter-process). "
            "High Lock waits correlate with lock contention; high IO waits suggest "
            "undersized shared_buffers or bloated tables."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_long_transactions",
        "description": (
            "Get transactions that have been idle in transaction for more than "
            "5 minutes. Returns pid, xact_start, state_change, duration, and "
            "query text. Long idle-in-transaction sessions hold row locks and "
            "prevent VACUUM from reclaiming dead tuples, causing table bloat. "
            "These are often the hidden cause of cascading performance problems."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

# ── Health Analyst Tools (5) ──

HEALTH_ANALYST_TOOLS: list[dict] = [
    {
        "name": "get_connection_pool",
        "description": (
            "Get a snapshot of the connection pool: active, idle, waiting, and "
            "max_connections. Returns utilization_pct. Pool saturation (>80%) "
            "causes connection queuing; >95% means new connections are rejected. "
            "Cross-reference with active queries to see if slow queries are "
            "holding connections."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_performance_stats",
        "description": (
            "Get key performance metrics: cache_hit_ratio (should be >0.99), "
            "transactions_per_second, deadlock_count, temp_files_created, and "
            "checkpoints_timed vs checkpoints_req. A cache_hit_ratio <0.95 means "
            "too many disk reads. Rising deadlock_count indicates lock ordering "
            "bugs. Frequent requested checkpoints suggest checkpoint_timeout or "
            "max_wal_size is too low."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_replication_status",
        "description": (
            "Get replication lag and replica health. Returns replica name, state "
            "(streaming/catchup), sent_lsn, write_lsn, flush_lsn, replay_lsn, "
            "and lag_bytes. High lag means replicas serve stale reads. If a "
            "replica is in catchup state, it may be overloaded or the network "
            "link is saturated."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_lock_chains",
        "description": (
            "Get blocking lock chains showing which PIDs are blocking which. "
            "Returns blocker_pid, blocked_pid, blocker_query, blocked_query, "
            "lock_type, and duration. Long blocking chains cause cascading "
            "slowdowns — a single long-running UPDATE can block dozens of "
            "queries. Check this when get_wait_events shows high Lock waits."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_autovacuum_status",
        "description": (
            "Get autovacuum worker status and per-table vacuum health. Returns "
            "currently running autovacuum workers, tables with highest dead tuple "
            "ratios, last_vacuum and last_autovacuum timestamps, and "
            "n_dead_tup / n_live_tup ratio. Tables with dead_ratio >0.2 and no "
            "recent vacuum are bloating. If max autovacuum workers are all busy, "
            "vacuum cannot keep up with write load."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

# ── Schema Analyst Tools (3) ──

SCHEMA_ANALYST_TOOLS: list[dict] = [
    {
        "name": "get_schema_snapshot",
        "description": (
            "Get an overview of the top 20 tables by size. Returns table_name, "
            "total_size (including indexes and TOAST), table_size (heap only), "
            "index_size, row_estimate, and bloat_estimate_pct. Use this first "
            "to identify which tables need deeper inspection with get_table_detail."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_table_detail",
        "description": (
            "Get detailed information about a single table: columns with types "
            "and nullability, all indexes with columns and sizes, foreign keys, "
            "constraints, dead tuple count, sequential scan count, index scan "
            "count, and estimated bloat percentage. Use this on tables flagged "
            "by get_schema_snapshot as bloated or oversized."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Fully qualified table name (e.g., 'public.orders') or just the table name.",
                },
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "get_table_access_patterns",
        "description": (
            "Get sequential scan vs index scan ratios for all user tables. "
            "Returns table_name, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch. "
            "Tables with high seq_scan and low idx_scan on large row counts are "
            "missing indexes. Tables with seq_tup_read >> idx_tup_fetch are doing "
            "full table scans when they should use indexes."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

# ── Finding Output Tool (1) ──
# Virtual tool used by the LLM to emit structured findings.
# Not backed by a real function — the orchestrator intercepts this tool call
# and parses the input as the agent's output.

FINDING_OUTPUT_TOOL: dict = {
    "name": "report_findings",
    "description": (
        "Output your diagnostic findings as structured data. Call this tool "
        "ONCE when you have completed your analysis. Each finding must cite "
        "specific tool_call_ids from the tools you invoked as evidence. Do not "
        "speculate — only report findings backed by tool evidence."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "description": "Array of diagnostic findings, ordered by severity (critical first).",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short finding title, e.g., 'Sequential scan on orders table'.",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "warning", "info"],
                            "description": "critical = immediate action needed, warning = should fix soon, info = optimization opportunity.",
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "slow_query",
                                "missing_index",
                                "table_bloat",
                                "lock_contention",
                                "connection_saturation",
                                "replication_lag",
                                "cache_pressure",
                                "vacuum_debt",
                                "long_transaction",
                                "deadlock",
                                "checkpoint_pressure",
                                "schema_issue",
                                "resource_exhaustion",
                            ],
                            "description": "Diagnostic category for grouping and filtering.",
                        },
                        "detail": {
                            "type": "string",
                            "description": "Detailed explanation of what was found and why it matters. Include specific numbers from the evidence.",
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Confidence score. 1.0 = certain from direct evidence, 0.7 = strong inference, <0.5 = speculative.",
                        },
                        "evidence_sources": {
                            "type": "array",
                            "description": "References to tool calls that support this finding.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "tool_call_id": {
                                        "type": "string",
                                        "description": "The tool_use id from the tool call that produced this evidence.",
                                    },
                                    "data_snippet": {
                                        "type": "string",
                                        "description": "Key data point extracted from the tool result, e.g., 'mean_exec_time: 4523ms'.",
                                    },
                                },
                                "required": ["tool_call_id", "data_snippet"],
                            },
                        },
                        "recommendation": {
                            "type": "string",
                            "description": "What the operator should do to fix this, in plain English.",
                        },
                        "remediation_sql": {
                            "type": "string",
                            "description": "Ready-to-run SQL to fix the issue (e.g., CREATE INDEX, ALTER TABLE, SET). Empty string if not applicable.",
                        },
                        "remediation_warning": {
                            "type": "string",
                            "description": "Risks or caveats for the remediation SQL (e.g., 'Will acquire ACCESS EXCLUSIVE lock for ~30s on a 50GB table').",
                        },
                    },
                    "required": [
                        "title",
                        "severity",
                        "category",
                        "detail",
                        "confidence",
                        "evidence_sources",
                        "recommendation",
                        "remediation_sql",
                        "remediation_warning",
                    ],
                },
            },
        },
        "required": ["findings"],
    },
}

# Database Diagnostics AI Parity Upgrade — Design Document

**Date:** 2026-03-10
**Author:** Architecture Team
**Status:** Approved

---

## 1. Problem Statement

The database diagnostics module is a functional monitoring dashboard but operates as an isolated silo. It has zero LLM integration, no chat interface, no investigation session workflow, no dossier generation, and no parity with the app diagnostics experience. All diagnostic logic is heuristic-based (hardcoded thresholds), and the module cannot reason about root causes, correlate findings across systems, or provide intelligent remediation guidance.

### Current Gaps (Scorecard)

| Dimension | Score | Verdict |
|-----------|-------|---------|
| LLM/AI Intelligence | 0/10 | No LLM calls at all |
| Chat Interface | 0/10 | Missing entirely |
| Error Handling | 4/10 | Basic try-catch, no retry/circuit-breaker |
| Dossier/Reporting | 0/10 | Missing entirely |
| Proactive Alerting | 3/10 | Static thresholds only |
| Visualization | 4/10 | Basic charts, no parity with app diagnostics |
| Agent Prompts | 0/10 | No prompts — agents are heuristic code |
| Human-in-the-Loop | 5/10 | Approval exists, no confidence-gated escalation |
| Multi-Engine | 2/10 | PostgreSQL only |
| Architecture | 3/10 | Isolated silo, not integrated with core platform |

---

## 2. Goals

- Bring database diagnostics to full parity with app diagnostics
- LLM-powered agents with PostgreSQL tool suite
- Chat interface for follow-up questions
- Investigation session workflow (V4Session)
- War Room UI adapted for database context
- Dossier report generation
- Safety-hardened remediation: Plan -> Verify (sandbox) -> Approve -> Execute
- All changes to production via GitOps/PRs or controlled SQL runbooks

### Acceptance Criteria

1. Agents produce findings that include `evidence_ids` and `artifact_id`
2. Heavy operations are enqueued; UI shows job progress
3. Remediation plans are immutable and require signed approvals before execution
4. Token/control budgets prevent single session from exceeding model or DB load limits
5. Synthetic incidents run and pass an end-to-end test (plan creation -> sandbox verify -> approve -> simulate execute -> verify/rollback)

---

## 3. Approach

**Session-First (Approach A):** Wire `database_diagnostics` into V4Session first, then layer LLM intelligence on top. The session model is the backbone — chat, WebSocket streaming, War Room layout, dossier generation all come from it.

**Engine scope:** PostgreSQL only. Perfect one engine before expanding. The abstract adapter base already exists for future engines.

---

## 4. Two Investigation Modes

### Mode A — Standalone (General Troubleshooting)

Used when users investigate a database independently. Triggered by: slow query alerts, replication lag alerts, disk space alerts, high CPU alerts, routine health checks.

- `parent_session_id = null`
- Agents run broad DBA diagnostics: slow queries, long transactions, locks, missing indexes, replication lag, connection exhaustion, disk I/O, buffer cache pressure

### Mode B — Contextual (Linked to App Session)

Used when investigation started from an app incident. Example: payment-api latency spike triggers DB diagnostics for orders-db-primary.

- `parent_session_id = 'APP-184'`
- Orchestrator fetches parent session findings
- Agents narrow scope: queries from triggering service, connections from that service's pods, recent schema changes affecting it

### Context Differences

**Standalone:**
```json
{
  "database": "orders-db-primary",
  "related_service": null,
  "investigation_mode": "standalone"
}
```

**Contextual:**
```json
{
  "database": "orders-db-primary",
  "related_service": "payment-api",
  "triggering_findings": ["db_timeout_errors", "latency_spike"],
  "investigation_mode": "contextual"
}
```

### UX Entry Points

1. **CapabilityLauncher card:** "Database Diagnostics" -> standalone mode
2. **App War Room button:** "Investigate Database" -> contextual mode with pre-filled parent session + auto-suggested databases from dependency map (one-click launch)

---

## 5. Session & Capability Integration

### Session Payload

```typescript
{
  capability: 'database_diagnostics',
  profile_id: string,
  time_window: '15m' | '1h' | '6h' | '24h',
  focus: ('queries' | 'connections' | 'replication' | 'storage' | 'schema')[],
  table_filter?: string[],
  database_type: 'postgres' | 'mysql' | 'redis' | 'mongo',
  sampling_mode: 'light' | 'standard' | 'deep',
  include_explain_plans: boolean,
  incident_context?: {
    service: string,
    environment: string,
    cluster: string
  },
  parent_session_id?: string,
  context_source?: 'user_selected' | 'auto_triggered'
}
```

### Session Model Extension

```python
# V4Session gets new fields:
parent_session_id: Optional[str]
related_sessions: list[str]       # bidirectional linking
investigation_mode: 'standalone' | 'contextual'
```

### Cross-Session Evidence Sharing

`GET /api/v4/sessions/{id}/findings` is already available. The DB orchestrator calls it when `parent_session_id` is set, injecting app findings into the DB agent context. Reverse linking: App War Room shows "Related Investigations" panel.

---

## 6. LLM-Powered Agent Architecture

### Model Routing Strategy

| Agent Role | Model | Rationale |
|---|---|---|
| `connection_validator` | No LLM | Pure connectivity check |
| `context_loader` | No LLM | Fetches parent session findings |
| `query_analyst` | Haiku (cheap) | Parse + extraction, tool-first |
| `health_analyst` | Haiku (cheap) | Parse + extraction, tool-first |
| `schema_analyst` | Haiku (cheap) | Parse + extraction, tool-first |
| `synthesizer` | Sonnet/Opus | Root cause analysis, correlation |
| `dossier_generator` | Opus | Final report generation |
| Chat follow-ups | Sonnet | User-facing reasoning |

### Agent Graph

```
START -> connection_validator -> context_loader -> [parallel dispatch] -> synthesizer -> dossier_generator -> END
                                                       |
                                       +---------------+---------------+
                                       |               |               |
                                 query_analyst    health_analyst   schema_analyst
                                 (Haiku+tools)   (Haiku+tools)   (Haiku+tools)
```

### Tool-First Pattern

Every tool returns a dual-output contract:

```python
class ToolOutput:
    summary: dict          # Compact object for LLM consumption (3-5 lines)
    artifact_id: str       # Reference to Evidence table row
    evidence_id: str       # Fingerprint for citation
    source_agent: str
    timestamp: str
```

Agents must call tools first, receive compact summaries, then reason over summaries only. Full EXPLAIN JSON is stored in the Evidence table — only the summary + `artifact_id` enters the prompt.

### Tool Suite

| Tool | Type | Safety | Target |
|---|---|---|---|
| `run_explain` | Read | EXPLAIN only, no ANALYZE on primary | primary/replica |
| `run_explain_analyze` | Read | Only when `sampling_mode=deep` + `include_explain_plans=true` | replica only |
| `query_pg_stat_statements` | Read | Read-only | primary |
| `query_pg_stat_activity` | Read | Read-only | primary |
| `query_pg_locks` | Read | Read-only | primary |
| `inspect_table_stats` | Read | Read-only | primary |
| `inspect_index_usage` | Read | Read-only | primary |
| `inspect_schema` | Read | Read-only | primary |
| `get_connection_pool` | Read | Read-only | primary |
| `get_replication_status` | Read | Read-only | primary |
| `get_config_setting` | Read | Read-only | primary |
| `capture_query_sample` | Read | By sql_sha + time window | replica |
| `estimate_index_benefit` | Compute | Deterministic, no DB write | local |
| `dry_run_index_create` | Sandbox | Creates on replica/clone only | replica |
| `get_slow_query_stack_traces` | Read | App log correlation | log store |
| `create_remediation_plan` | Plan | Immutable plan creation only | system |

### Safety Controls

| Control | Rule |
|---|---|
| Default EXPLAIN | `EXPLAIN (FORMAT JSON)` — no ANALYZE on primary |
| ANALYZE allowed | Only when `sampling_mode=deep` AND `include_explain_plans=true` AND `target=replica` |
| Credentials | Read-only DB user for all tool queries by default |
| Heavy ops | Enqueued via job queue with concurrency limiter (1 per profile) |
| Sampling | `deep` mode: top K queries (default 20), top M tables (default 50) |
| Token budget | Per-session LLM token limit to prevent runaway costs |
| DB load budget | Estimated added DB load tracked per session; abort if threshold exceeded |

### Evidence Storage

Instead of S3, use an internal Evidence table in the platform DB:

```sql
CREATE TABLE evidence_artifacts (
    artifact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    source_agent TEXT NOT NULL,
    artifact_type TEXT NOT NULL,  -- 'explain_plan', 'pg_stat_dump', 'query_sample', etc.
    summary_json TEXT NOT NULL,   -- compact summary for LLM consumption
    full_content TEXT NOT NULL,   -- complete raw output
    preview TEXT,                 -- first N lines for UI preview without fetching full artifact
    timestamp TEXT NOT NULL,
    vector_embedding_id TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
```

### Evidence Fingerprinting

Every evidence item carries:

```json
{
  "evidence_id": "e-9001",
  "artifact_id": "art-9001",
  "source_agent": "query_analyst",
  "timestamp": "2026-03-10T12:34:56Z",
  "summary": "pg_stat_statements: total_time=1.47E6ms calls=820 mean=1792ms",
  "preview": "first 10 lines of raw output..."
}
```

### Explainable Reasoning

Every finding must include:
- `supporting_evidence_ids[]` — links to evidence artifacts
- `rule_check` — deterministic rule string (e.g., `"index_suggested: explain.rows_estimated > 100000"`)

### Agent Output: JSON-Only

All agents return structured JSON, no free text.

---

## 7. Canonical Schemas

### Agent Finding Schema

```json
{
  "finding_id": "f-0001",
  "agent": "query_analyst",
  "category": "slow_query",
  "title": "High p95 latency for SQL sha:0xabc",
  "severity": "high",
  "confidence_raw": 0.86,
  "confidence_calibrated": 0.78,
  "timestamp": "2026-03-10T12:34:56Z",
  "detail": "Query scanning 12M rows repeatedly causing p95 1800ms (calls: 820)",
  "evidence_ids": ["e-9001", "e-9002"],
  "evidence_snippets": [
    {
      "id": "e-9001",
      "summary": "pg_stat_statements: total_time=1.47E6ms calls=820 mean=1792ms p95=1800ms",
      "artifact_id": "art-9001"
    },
    {
      "id": "e-9002",
      "summary": "EXPLAIN (FORMAT JSON) summary: Seq Scan on orders (rows=12M)",
      "artifact_id": "art-9002"
    }
  ],
  "affected_entities": {
    "database": "orders_db",
    "cluster": "postgres-prod-cluster",
    "tables": ["orders"]
  },
  "recommendation": "Add covering index on orders(user_id, created_at) OR rewrite query. See plan: p-77",
  "remediation_available": true,
  "remediation_plan_id": "p-77",
  "rule_check": "index_suggested: explain.rows_estimated > 100000",
  "meta": {
    "sql_sha": "0xabc",
    "sample_query_id": "q-5566",
    "agent_version": "query_analyst-v2",
    "prompt_version": "db-agent-prompt-v1"
  }
}
```

### Remediation Plan Schema (Immutable Once Created)

```json
{
  "plan_id": "p-77",
  "created_by": "query_analyst",
  "created_at": "2026-03-10T12:40:00Z",
  "summary": "Create index idx_orders_user_created_at to reduce seq scans for payment queries",
  "scope": {
    "type": "schema_change",
    "database": "orders_db",
    "cluster": "postgres-prod-cluster",
    "target_repos": ["git@github.com:org/service-order.git"]
  },
  "steps": [
    {
      "step_id": "s1",
      "type": "create_index",
      "description": "Create index concurrently on replica for verification",
      "command": "CREATE INDEX CONCURRENTLY idx_orders_user_created_at ON orders (user_id, created_at);",
      "run_target": "replica1",
      "estimated_time_minutes": 8
    },
    {
      "step_id": "s2",
      "type": "verify",
      "description": "Run representative workload and compare p95, p50",
      "command": "-- replay workload; check p95 pre/post",
      "run_target": "replica1",
      "checks": [
        { "metric": "p95_latency", "threshold_reduction_pct": 50 }
      ]
    },
    {
      "step_id": "s3",
      "type": "promote",
      "description": "If verification passes, create PR with index DDL and merge via GitOps",
      "command": "git create-branch ...; open PR ...",
      "run_target": "gitops"
    },
    {
      "step_id": "s4",
      "type": "rollback",
      "description": "Drop index and revert PR if verification fails",
      "command": "DROP INDEX IF EXISTS idx_orders_user_created_at;",
      "run_target": "replica1"
    }
  ],
  "prechecks": [
    { "id": "p1", "type": "replica_available", "required": true },
    { "id": "p2", "type": "disk_free", "required": true, "threshold_gb": 10 }
  ],
  "required_approvals": [
    { "role": "dba", "min_count": 1 },
    { "role": "service_owner", "min_count": 1 }
  ],
  "approval_status": "pending",
  "approvals": [],
  "audit": {
    "plan_artifact_id": "art-plan-77",
    "immutable_hash": "sha256:..."
  },
  "policy_tags": ["safe-index", "no-downtime"],
  "estimated_risk": "low",
  "status": "created"
}
```

---

## 8. Remediation: Plan -> Verify -> Approve -> Execute

```
Agent creates plan (immutable, SHA256-hashed)
    -> Prechecks (replica available? disk free?)
        -> Sandbox verification (run on replica/clone, compare metrics)
            -> Role-based approval (DBA + service owner, JWT-signed)
                -> Execute on target (GitOps PR or controlled SQL runbook)
                    -> Post-execution verification
                        -> Rollback if verification fails
```

### Key Properties

- Plans are immutable once created — audited with SHA256 hash stored in Evidence table
- JWT-signed approval tokens with role requirements
- Sandbox-first: changes tested on replica before PR to primary
- GitOps integration: schema changes go through PRs, not direct DDL
- Every step logged in audit trail with before/after state
- "Preview remediation diff" before plan creation (show SQL/DDL and generated revert)

---

## 9. WebSocket Event Model

```json
{ "event": "SESSION_STARTED", "session_id": "S-42", "timestamp": "..." }
{ "event": "AGENT_STARTED", "agent": "query_analyst", "job_id": "J-101" }
{ "event": "TOOL_JOB_ENQUEUED", "tool": "run_explain_analyze", "job_id": "J-102", "target": "replica1" }
{ "event": "TOOL_JOB_COMPLETED", "job_id": "J-102", "summary": { "duration_ms": 1200, "rows": 10 }, "artifact_id": "art-102" }
{ "event": "FINDING_CREATED", "finding": { "..." } }
{ "event": "PLAN_CREATED", "plan_id": "P-77", "remediation_url": "/plans/P-77" }
{ "event": "PLAN_APPROVAL_REQUIRED", "plan_id": "P-77", "required_roles": ["dba", "oncall"] }
{ "event": "LOW_CONFIDENCE", "session_id": "S-42", "reason": "query_analyst returned confidence < 0.7" }
```

---

## 10. Confidence & Human-in-the-Loop

- `confidence_raw`: Direct model output score
- `confidence_calibrated`: Post-calibration score (trained on ground truth feedback)
- If any finding `confidence_calibrated < 0.7` -> emit `LOW_CONFIDENCE` event -> UI shows review banner
- Feedback loop: human confirms/rejects findings -> stored as ground truth -> retrains calibration model
- Findings accepted/rejected rates tracked as ops metrics

---

## 11. War Room UI

### Three-Column Layout (adapted from app diagnostics)

| Column | Content |
|---|---|
| **Investigator** (col-3) | DB profile banner (name, engine, host:port, mode badge), investigation timeline, chat interface |
| **Evidence Findings** (col-5) | Scrollable findings stack using AgentFindingCard with agent color coding, CausalRoleBadge, evidence drill-down with artifact preview (first N lines) |
| **Navigator** (col-4) | Query performance flamechart, connection pool gauge, replication topology SVG, table bloat heatmap, remediation plan dock |

### Header Banners

**Standalone:**
```
Database Diagnostics | orders-db-primary | Mode: General Troubleshooting
```

**Contextual:**
```
Database Diagnostics | orders-db-primary | Linked: payment-api incident (APP-184)
```

### Cross-Session UI

- App War Room: "Related Investigations" panel with link to DB session
- DB War Room: "Linked Incident" banner with jump-to-app-session link
- One-click "Start DB Session from App War Room" pre-fills parent_session_id and suggests top DBs

---

## 12. Dossier & Reporting

After investigation completes, the `dossier_generator` (Opus) produces:

1. **Executive Summary** — 3-sentence overview
2. **Root Cause Analysis** — Primary cause with evidence chain
3. **Findings** — All findings ranked by severity x confidence
4. **Performance Tuning Recommendations** — Index suggestions, config changes, query rewrites
5. **Remediation Plans** — All created plans with status and preview diffs
6. **Proactive Alerts** — Trend-based warnings ("connection pool trending to saturation in ~2h")
7. **Database Health Scorecard** — Composite scores for queries, connections, storage, replication

Rendered in `DatabaseDossierView.tsx`, exportable as PDF.

---

## 13. Visualization Components

| Visualization | Component | Data Source |
|---|---|---|
| Query performance flamechart | `QueryFlamechart.tsx` | pg_stat_statements top N |
| Connection pool gauge | `ConnectionPoolGauge.tsx` | adapter.get_connection_pool |
| Replication topology | `ReplicationTopologySVG.tsx` | adapter.get_replication_status |
| Table bloat heatmap | `TableBloatHeatmap.tsx` | pg_stat_user_tables bloat_ratio |
| Index usage matrix | `IndexUsageMatrix.tsx` | pg_stat_user_indexes |
| Slow query timeline | `SlowQueryTimeline.tsx` | pg_stat_activity history |
| EXPLAIN plan tree | `ExplainPlanTree.tsx` | EXPLAIN JSON output (from Evidence table) |
| Metric sparklines | Reuse `SparklineWidget` | monitor metrics |

---

## 14. Ops Monitoring Metrics (Must-Have)

Track across all sessions:

| Metric | Description |
|---|---|
| `agent.tool_calls.{tool_name}.count` | Tool invocation count |
| `agent.tool_calls.{tool_name}.latency` | Tool latency distribution |
| `tool_job.queue_length` | Pending jobs in queue |
| `tool_job.active` | Active jobs per profile |
| `llm.tokens.used.per_session` | Token consumption per session |
| `llm.calls.cost` | Estimated cost per session |
| `findings.accepted_rate` | Human-confirmed findings ratio |
| `findings.rejected_rate` | Human-rejected findings ratio |
| `plan.success_rate` | Remediation plan success ratio |
| `plan.rollback_rate` | Remediation rollback ratio |
| `db_tool.load.introduced` | Estimated DB load caused by diagnostic queries |

---

## 15. Prioritized Rollout

1. Safety controls and job queue — read-only creds, replica-only ANALYZE, job queue with concurrency limits
2. Evidence table and tool output contracts — enforce `artifact_id` + summary pattern
3. Agent output JSON schema — adopt Finding schema, enforce via code + tests
4. Session integration — add `database_diagnostics` to CapabilityType, wire into V4Session
5. LLM agent graph — replace heuristic agents with tool-first LLM agents
6. Chat interface — reuse ChatContext from app diagnostics
7. War Room UI — adapt three-column layout for DB context
8. Remediation Plan flow — immutability, JWT-signed approvals, sandbox verification, audit storage
9. Dossier generation — Opus-powered report with all sections
10. Visualization components — flamechart, gauges, topology, heatmaps
11. LLM model routing and budget controls — Haiku for agents, Opus for synth
12. Calibration and feedback loop — ground truth collection, calibration model training
13. Ops metrics instrumentation

---

## 16. Files to Create/Modify

### Backend (New)

- `backend/src/agents/database/graph_v2.py` — New LLM-powered agent graph
- `backend/src/agents/database/tools/` — Tool implementations (one file per tool)
- `backend/src/agents/database/prompts/` — Prompt templates per agent
- `backend/src/database/evidence_store.py` — Evidence table CRUD
- `backend/src/database/job_queue.py` — Job queue with concurrency limiter
- `backend/src/api/db_session_endpoints.py` — V4Session integration for DB diagnostics

### Backend (Modify)

- `backend/src/api/routes_v4.py` — Add `database_diagnostics` capability
- `backend/src/database/models.py` — Add evidence, job, and extended finding models
- `backend/src/database/remediation_engine.py` — Add sandbox verification and immutable plans

### Frontend (New)

- `frontend/src/components/ActionCenter/forms/DatabaseDiagnosticsFields.tsx` — Session creation form
- `frontend/src/components/Investigation/DatabaseWarRoom.tsx` — Three-column DB War Room
- `frontend/src/components/Investigation/DatabaseDossierView.tsx` — Report view
- `frontend/src/components/Investigation/db-viz/QueryFlamechart.tsx`
- `frontend/src/components/Investigation/db-viz/ConnectionPoolGauge.tsx`
- `frontend/src/components/Investigation/db-viz/ReplicationTopologySVG.tsx`
- `frontend/src/components/Investigation/db-viz/TableBloatHeatmap.tsx`
- `frontend/src/components/Investigation/db-viz/IndexUsageMatrix.tsx`
- `frontend/src/components/Investigation/db-viz/SlowQueryTimeline.tsx`
- `frontend/src/components/Investigation/db-viz/ExplainPlanTree.tsx`

### Frontend (Modify)

- `frontend/src/types/index.ts` — Add `database_diagnostics` to CapabilityType
- `frontend/src/components/Home/CapabilityLauncher.tsx` — Add DB diagnostics card
- `frontend/src/App.tsx` — Route DB sessions to DatabaseWarRoom

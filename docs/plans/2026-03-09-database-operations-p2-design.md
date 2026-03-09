# Database Operations P2 — Design Document

**Date:** 2026-03-09
**Status:** Approved
**Depends on:** Database Diagnostics P0 (shipped), Database Monitoring P1 (shipped)

---

## 1. Overview

Write operations, AI-driven remediation, and configuration tuning for PostgreSQL databases. Adds a saga-based execution engine (plan → approve → execute → verify → rollback), an AI remediation planner that maps diagnostic findings to actionable fixes, and a frontend Operations tab for manual and AI-suggested operations.

**Scope:** PostgreSQL only. MongoDB/MySQL adapters deferred.

**Approach:** Both AI-generated plans (from diagnostic findings) and user-initiated operations (from a manual menu). Inline approval UX — plans shown with SQL preview + impact assessment, user clicks Approve/Reject directly. Failover is plan-only (generates runbook, does not auto-execute).

---

## 2. Adapter Write Operations

New abstract methods on `DatabaseAdapter`, implemented by `PostgresAdapter`. All write methods require an `approval_token: str` parameter — the adapter validates the JWT before executing.

| Method | PostgreSQL Implementation | Safety |
|--------|--------------------------|--------|
| `kill_query(pid)` | `SELECT pg_terminate_backend($1)` | Validates PID exists in `pg_stat_activity` first |
| `vacuum_table(table, full, analyze)` | `VACUUM [FULL] [ANALYZE] table` | Table existence check; FULL requires explicit flag |
| `reindex_table(table)` | `REINDEX TABLE CONCURRENTLY table` | Uses CONCURRENTLY to avoid locks |
| `create_index(table, columns, name, unique)` | `CREATE INDEX CONCURRENTLY name ON table (cols)` | Non-blocking; validates columns exist |
| `drop_index(index_name)` | `DROP INDEX CONCURRENTLY name` | Validates index exists; prevents dropping PK indexes |
| `alter_config(param, value, scope)` | `ALTER SYSTEM SET param = value` + `pg_reload_conf()` | Allowlist of tunable params; rejects dangerous ones |
| `get_config_recommendations()` | Reads `pg_settings` + heuristics | Read-only; compares current vs. suggested |
| `generate_failover_runbook(replica_id)` | Reads replication state | Read-only; returns step list, no execution |

### Config Allowlist

Tunable parameters (everything else rejected):

```
shared_buffers, work_mem, maintenance_work_mem, effective_cache_size,
max_connections, max_worker_processes, max_parallel_workers_per_gather,
random_page_cost, effective_io_concurrency, checkpoint_completion_target,
wal_buffers, min_wal_size, max_wal_size, log_min_duration_statement,
statement_timeout, idle_in_transaction_session_timeout
```

---

## 3. Remediation Engine (Saga Orchestrator)

New class at `backend/src/database/remediation_engine.py`:

```python
class RemediationEngine:
    def __init__(self, plan_store, adapter_registry, profile_store, secret_key):
        ...

    def plan(self, profile_id, action, params, finding_id=None) -> RemediationPlan
    def approve(self, plan_id) -> dict   # {plan_id, approval_token, expires_at}
    def reject(self, plan_id)
    async def execute(self, plan_id, token) -> RemediationResult
    def get_plan(self, plan_id) -> RemediationPlan
    def list_plans(self, profile_id, status=None) -> list
    def get_audit_log(self, profile_id, limit=50) -> list
```

### Saga Flow

```
plan → [pending] → approve → [approved] → execute:
  1. Pre-flight check (connection alive, table/index exists, no conflicting locks)
  2. Snapshot "before" state (row count, index list, config value, etc.)
  3. Execute SQL via adapter write method
  4. Verify success (re-check state matches expectations)
  5. If verify fails → auto-rollback using rollback_sql
  → [completed] or [failed] or [rolled_back]
```

### Statuses

`pending` → `approved` → `executing` → `completed` | `failed` | `rolled_back`

Also: `expired` (approval token TTL exceeded), `rejected` (user rejected plan).

### JWT Approval Token

- Generated on `approve()`, signed with app secret key
- 5-minute TTL
- Payload: `{plan_id, profile_id, action, exp}`
- Validated by adapter before any write operation

### Safety Layers

1. **Adapter-level:** Write methods require valid JWT token
2. **Engine-level:** Pre-flight checks before execution
3. **Saga-level:** Auto-rollback on verification failure
4. **Audit-level:** Every write logged with before/after state
5. **UI-level:** Inline approval with SQL preview — no hidden execution

**No batch remediation. One plan executed at a time. Serial, not parallel.**

---

## 4. Data Models

Added to `backend/src/database/models.py`:

```python
class RemediationPlan(BaseModel):
    plan_id: str
    profile_id: str
    finding_id: Optional[str] = None     # null if manually triggered
    action: str                           # kill_query, vacuum, reindex, create_index, drop_index, alter_config, failover_runbook
    params: dict = {}                     # action-specific: {pid: 123}, {table: "orders", full: true}, etc.
    sql_preview: str                      # exact SQL that will run
    impact_assessment: str                # "~2min lock on 1.2M row table"
    rollback_sql: Optional[str] = None    # null for irreversible ops (kill_query)
    requires_downtime: bool = False
    status: str = "pending"
    created_at: str
    approved_at: Optional[str] = None
    executed_at: Optional[str] = None
    completed_at: Optional[str] = None
    result_summary: Optional[str] = None
    before_state: Optional[dict] = None
    after_state: Optional[dict] = None

class AuditLogEntry(BaseModel):
    entry_id: str
    plan_id: str
    profile_id: str
    action: str
    sql_executed: str
    status: str                           # success, failed, rolled_back
    before_state: dict = {}
    after_state: dict = {}
    error: Optional[str] = None
    timestamp: str

class ConfigRecommendation(BaseModel):
    param: str
    current_value: str
    recommended_value: str
    reason: str
    requires_restart: bool = False
```

### Persistence

New SQLite tables in `data/debugduck.db`:

```sql
CREATE TABLE remediation_plans (
    plan_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    finding_id TEXT,
    action TEXT NOT NULL,
    params TEXT NOT NULL,            -- JSON
    sql_preview TEXT NOT NULL,
    impact_assessment TEXT,
    rollback_sql TEXT,
    requires_downtime INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL,
    approved_at TEXT,
    executed_at TEXT,
    completed_at TEXT,
    result_summary TEXT,
    before_state TEXT,               -- JSON
    after_state TEXT                  -- JSON
);

CREATE TABLE audit_log (
    entry_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    action TEXT NOT NULL,
    sql_executed TEXT NOT NULL,
    status TEXT NOT NULL,
    before_state TEXT,               -- JSON
    after_state TEXT,                -- JSON
    error TEXT,
    timestamp TEXT NOT NULL
);
```

Store class: `backend/src/database/remediation_store.py` (same pattern as `DiagnosticRunStore`).

---

## 5. AI Remediation Planner

New LangGraph agent at `backend/src/agents/database/remediation_planner.py`.

### Graph

```
analyze_findings → generate_plans → [STOP for human approval]
```

### Finding-to-Action Mapping

| Finding Category | Suggested Action | Details |
|-----------------|-----------------|---------|
| `slow_queries` | `create_index` | Columns from query plan analysis |
| `table_bloat` | `vacuum` | FULL if bloat > 30% |
| `index_bloat` | `reindex` | Target bloated index |
| `deadlocks` | `kill_query` | Blocking PID |
| `connection_saturation` | `alter_config` | Increase `max_connections` |
| `replication_lag` | `failover_runbook` | Generate runbook steps |
| `missing_index` | `create_index` | Specific columns |
| `unused_index` | `drop_index` | Index with zero scans |

### Integration

After a diagnostic run completes, user clicks "Suggest Fixes" → invokes planner → plans appear in Operations tab for approval.

---

## 6. API Endpoints

All under `db_router` (prefix `/api/db`):

### Remediation

```
POST   /api/db/remediation/plan
       body: { profile_id, action, params }
       → RemediationPlan

POST   /api/db/remediation/suggest
       body: { profile_id, run_id }
       → { plans: RemediationPlan[] }

GET    /api/db/remediation/plans?profile_id=X&status=Y
       → RemediationPlan[]

GET    /api/db/remediation/plans/{plan_id}
       → RemediationPlan

POST   /api/db/remediation/approve/{plan_id}
       → { plan_id, approval_token, expires_at }

POST   /api/db/remediation/reject/{plan_id}
       → { status: "rejected" }

POST   /api/db/remediation/execute/{plan_id}
       body: { approval_token }
       → RemediationResult

GET    /api/db/remediation/log?profile_id=X&limit=50
       → AuditLogEntry[]
```

### Config

```
GET    /api/db/config/{profile_id}/recommendations
       → { current, recommended, suggestions: ConfigRecommendation[] }
```

### Kill Query Shortcut

```
POST   /api/db/queries/{profile_id}/kill/{pid}
       → RemediationResult
```

Bypasses full saga — kill is low-risk and time-sensitive. Creates plan + auto-approves + executes in one call.

---

## 7. Frontend

### 7.1 DBOperations Tab (`DBOperations.tsx`)

New tab in DatabaseLayout sidebar: `{ id: 'operations', label: 'Operations', icon: 'build' }`.

**Layout:**
- Top bar: profile selector, "New Operation" dropdown menu
- Active Queries panel: live query list with PID, SQL preview, duration, Kill button
- Pending Plans panel: `RemediationCard` for each pending/approved plan
- Config Recommendations panel: current vs. suggested values with Apply button
- Execution Log: recent audit entries with status dots, expandable before/after diff

**"New Operation" dropdown menu:**
- Kill Query (opens active query list)
- Vacuum Table (form: table selector, full checkbox, analyze checkbox)
- Reindex Table (form: table selector)
- Create Index (form: table, columns, unique, name)
- Drop Index (form: index selector)
- Alter Config (form: param selector from allowlist, value)

### 7.2 RemediationCard (`RemediationCard.tsx`)

Inline approval card shown for each pending plan:

```
┌──────────────────────────────────────────────────┐
│ CREATE INDEX on orders(customer_id)              │
│ Source: AI (from finding "slow queries")    ○ pending │
│                                                  │
│ SQL Preview:                                     │
│ ┌──────────────────────────────────────────────┐ │
│ │ CREATE INDEX CONCURRENTLY idx_orders_cust    │ │
│ │ ON orders (customer_id);                     │ │
│ └──────────────────────────────────────────────┘ │
│                                                  │
│ Impact: ~3min, non-blocking                      │
│ Rollback: DROP INDEX CONCURRENTLY idx_orders_... │
│                                                  │
│                        [Reject]  [Approve & Run] │
└──────────────────────────────────────────────────┘
```

### 7.3 OperationFormModal (`OperationFormModal.tsx`)

Modal for manually triggering operations. Dynamic form fields based on selected action type. Submits to `/api/db/remediation/plan`, then shows the resulting `RemediationCard` for approval.

---

## 8. File Structure

```
backend/src/database/
  remediation_engine.py          # Saga orchestrator
  remediation_store.py           # SQLite persistence for plans + audit log
  models.py                      # Add RemediationPlan, AuditLogEntry, ConfigRecommendation

backend/src/database/adapters/
  base.py                        # Add 8 write methods to ABC
  postgres.py                    # Implement write methods
  mock_adapter.py                # Mock write methods

backend/src/agents/database/
  remediation_planner.py         # LangGraph agent: findings → plans

backend/src/api/
  db_endpoints.py                # Add remediation + config + kill endpoints

backend/tests/
  test_remediation_engine.py
  test_remediation_store.py
  test_remediation_endpoints.py
  test_remediation_planner.py
  test_adapter_write_ops.py

frontend/src/components/Database/
  DatabaseLayout.tsx             # Add Operations tab
  DBOperations.tsx               # Main operations view
  RemediationCard.tsx            # Inline plan approval card
  OperationFormModal.tsx         # Manual operation trigger modal

frontend/src/services/
  api.ts                         # Add remediation API functions
```

# Database Diagnostics, Monitoring & Operations — Design Document

**Date:** 2026-03-09
**Status:** Approved
**Author:** Architecture Team

---

## 1. Overview

A fully standalone database management module for DebugDuck supporting PostgreSQL, MongoDB, MySQL, and Oracle DB. Three capabilities phased across sprints: Diagnostics (P0), Monitoring (P1), and Operations (P2).

**Not integrated with app/cluster diagnostics.** This is a separate product surface with its own page, nav entry, data models, and WebSocket channel. Shares only the design system (dark theme, cyan accent, Tailwind).

---

## 2. Capabilities

### 2.1 Diagnostics (P0) — Reactive
"Something is wrong with my DB — find out what."
- Slow query detection + EXPLAIN plan analysis
- Replication lag root cause
- Connection pool exhaustion
- Lock contention / deadlocks
- Storage/memory pressure
- Schema bloat / missing indexes

### 2.2 Monitoring (P1) — Proactive
"Continuously watch my DB and alert me before things break."
- Connection pool utilization trending
- Replication lag thresholds
- Query performance degradation over time
- Storage capacity forecasting
- Buffer/cache hit ratio tracking
- Automated health checks on schedule
- Configurable alert rules with history

### 2.3 Operations (P2) — Write Actions
"Fix or tune things on my DB."
- Kill long-running queries
- Add/drop indexes
- Tune configuration parameters
- Vacuum / reindex / compact
- Schema migrations (limited scope)
- Failover / promote replica
- Full saga pattern: plan → approve → execute → verify → rollback

---

## 3. Architecture

### 3.1 Five-Plane Model

```
┌─────────────── Experience Plane (Frontend) ──────────────────┐
│  DB Dashboard: Capability sidebar + content area (Overview/Connections/Diag/Mon/Ops/Schema) │
├─────────────── Control Plane (API) ──────────────────────────┤
│  db_endpoints.py: FastAPI router at /api/db/*                  │
│  WebSocket channel for live diagnostic progress                │
├─────────────── Orchestration Plane (Agents) ─────────────────┤
│  LangGraph StateGraph: fan-out to domain agents → synthesize   │
├─────────────── Tool Plane (Adapters) ────────────────────────┤
│  DatabaseAdapterRegistry → PostgresAdapter, MongoDBAdapter...  │
│  Snapshot-based reads, approval-gated writes                   │
├─────────────── Data/Trust Plane (Storage) ────────────────────┤
│  SQLite: profiles, diagnostic runs, audit log                  │
│  InfluxDB: monitoring time-series (P1)                         │
└───────────────────────────────────────────────────────────────┘
```

### 3.2 Adapter Pattern

Mirrors existing `FirewallAdapter` + `AdapterRegistry` pattern.

```python
class DatabaseAdapter(ABC):
    """Base adapter for all database engines."""

    @abstractmethod
    async def connect(self) -> None: ...
    @abstractmethod
    async def disconnect(self) -> None: ...
    @abstractmethod
    async def health_check(self) -> AdapterHealth: ...

    # Snapshot accessors (cached, TTL-based, never hit live DB)
    @abstractmethod
    async def get_schema_snapshot(self) -> SchemaSnapshot: ...
    @abstractmethod
    async def get_active_queries(self) -> list[ActiveQuery]: ...
    @abstractmethod
    async def get_replication_status(self) -> ReplicationSnapshot: ...
    @abstractmethod
    async def get_performance_stats(self) -> PerfSnapshot: ...
    @abstractmethod
    async def get_connection_pool(self) -> ConnectionPoolSnapshot: ...

    # Live query (read-only, timeout-capped, row-limited)
    @abstractmethod
    async def execute_diagnostic_query(self, sql: str) -> QueryResult: ...

    # Write path (requires approval token, P2 only)
    @abstractmethod
    async def execute_remediation(self, plan: RemediationPlan) -> RemediationResult: ...
```

**DatabaseAdapterRegistry:**
- Multi-instance per engine (N Postgres, M MongoDB, etc.)
- Lookup by `instance_id` (primary) or `profile_id` (integration binding)
- Thread-safe with `asyncio.Lock`
- TTL-based snapshot refresh (default 300s)

**Pluggability:** Adding a new engine = one class with ~10 methods. Registry, caching, health checks inherited.

### 3.3 Agent Structure

All agents inherit from existing `ReActAgent` base class, inheriting:
- Budget tracking (max_iterations, max_tokens, max_tool_calls)
- Breadcrumb recording and negative findings
- Evidence pins with confidence scoring
- Retry logic with exponential backoff
- Wrap-up nudge when budget exhausted

| Agent | Responsibility | Tools | Phase |
|-------|---------------|-------|-------|
| `DBQueryAgent` | Slow queries, plan analysis, index recommendations | `explain_query`, `get_slow_log`, `suggest_index` | P0 |
| `DBHealthAgent` | Connections, replication, storage, memory | `get_perf_stats`, `get_replication_status`, `get_connection_pool` | P0 |
| `DBSchemaAgent` | Schema drift, bloat, missing indexes, FK integrity | `get_schema_snapshot`, `compare_schemas`, `detect_bloat` | P1 |
| `DBRemediationAgent` | Execute approved fixes | `execute_remediation` (requires approval token) | P2 |

### 3.4 Orchestration Graph (LangGraph)

```
START
  → db_connection_validator     (can we reach the DB? fail fast)
  → snapshot_collector          (populate all caches in parallel)
  → symptom_classifier          (what category: perf? replication? schema?)
  → [dispatch_router]           (select relevant agents by symptom)
  → [2-3 domain agents parallel] (only dispatched ones run)
  → synthesize                  (merge findings, deduplicate, rank)
  → [conditional] remediation_planner (if actionable fix found, P2)
  → END
```

No critic/redispatch loop in P0. Add in P2 if synthesis quality data warrants it.

### 3.5 Remediation Safety (P2)

Five layers of defense-in-depth:

| Layer | Mechanism |
|-------|-----------|
| Adapter-level | READ-ONLY connection by default. Write requires explicit opt-in. |
| Tool-level | Remediation tools require `approval_token` (JWT, short-lived) |
| Orchestration | `remediation_planner` emits plan, STOPS. Requires human approval via WebSocket. |
| Execution | Pre-flight check (is DB still in expected state?), execute, verify, auto-rollback on failure. |
| Audit | Every write logged with before/after state, approver, timestamp. |

No batch remediation. One fix at a time. Serial, not parallel.

---

## 4. Frontend

### 4.1 Principle

Fully standalone. **Not integrated with app/cluster War Room.**

- App diagnostic = **Investigation** (one incident, ephemeral) → War Room UI
- DB diagnostic = **Management** (persistent profiles, ongoing relationship) → Dashboard with capability sidebar

Different mental models require different UI patterns. The DB dashboard uses **capability-first navigation** (sidebar = what you want to do, content area = which database), not profile-first tabs.

### 4.2 Navigation Model

**Capability-first sidebar** — like AWS Console, Datadog, or Grafana:

```
┌──────────────────┬──────────────────────────────────────────────┐
│  Databases       │                                              │
│                  │  Content area changes based on               │
│  ┌────────────┐  │  sidebar selection                           │
│  │ Overview   │◄─│                                              │
│  ├────────────┤  │  Each section has its own layout,            │
│  │ Connections│  │  with DB selector dropdown where needed      │
│  ├────────────┤  │                                              │
│  │ Diagnostics│  │                                              │
│  ├────────────┤  │                                              │
│  │ Monitoring │  │  (P1)                                        │
│  ├────────────┤  │                                              │
│  │ Operations │  │  (P2)                                        │
│  ├────────────┤  │                                              │
│  │ Schema     │  │  (P1)                                        │
│  └────────────┘  │                                              │
│                  │                                              │
│  ── Settings ──  │                                              │
│  Alert Rules (P1)│                                              │
│  Audit Log   (P2)│                                              │
└──────────────────┴──────────────────────────────────────────────┘
```

**Why capability-first, not profile-first:**
- Fleet overview across all DBs without clicking each profile
- Sidebar scales (new features = new sidebar items, not crowded tabs)
- Cross-DB views possible (monitoring alerts across all DBs)
- Clean deep-linkable URLs: `/db/diagnostics/prod-pg`
- Mental model: "What do I want to do?" then "Which DB?"

### 4.3 Sidebar Sections

**Overview (P0):** Fleet health cards for all connected DBs. Status indicator (green/yellow/red), engine badge, key metric per card. Recent alerts (P1) and recent diagnostic runs.

**Connections (P0):** Profile CRUD table. Create/edit/delete/test connection profiles. Engine type, host, port, database, credentials.

**Diagnostics (P0):** DB selector dropdown at top. Run history table. Launch new diagnostic. Expanded findings view with query plan viewer and recommendations.

**Monitoring (P1):** DB selector + time range. Time-series charts (latency p50/95/99, connections, repl lag). Alert rules CRUD. Alert fire/resolve history.

**Operations (P2):** DB selector. Pending remediation approvals. Quick actions (kill query, vacuum, reindex, tune). Execution audit log with before/after state.

**Schema (P1):** DB selector. Schema browser (tables/views/functions tree). Table detail with columns, indexes, size, bloat. Schema diff between snapshots.

P1/P2 sidebar items show "Coming Soon" placeholder until their phase ships.

### 4.4 Components

| Component | Purpose | Phase |
|-----------|---------|-------|
| `DBLayout.tsx` | Page shell: sidebar + content area | P0 |
| `DBSidebar.tsx` | Capability navigation sidebar | P0 |
| `DBOverview.tsx` | Fleet health cards grid | P0 |
| `DBConnections.tsx` | Profile CRUD table | P0 |
| `DBProfileForm.tsx` | Create/edit profile modal | P0 |
| `DBDiagnostics.tsx` | Run history + findings view | P0 |
| `DBDiagnosticRun.tsx` | Single run detail (findings list) | P0 |
| `DBHealthGauge.tsx` | Circular gauge (reusable) | P0 |
| `QueryPlanViewer.tsx` | EXPLAIN tree renderer | P0 |
| `SlowQueryTable.tsx` | Sortable slow query list | P0 |
| `DBMonitoring.tsx` | Time-series charts + alerts | P1 |
| `DBAlertRuleEditor.tsx` | Alert rule CRUD form | P1 |
| `DBSchema.tsx` | Schema browser + table detail | P1 |
| `SchemaCompareView.tsx` | Side-by-side schema diff | P1 |
| `DBOperations.tsx` | Remediation console | P2 |
| `RemediationApprovalCard.tsx` | Plan + approve/reject | P2 |

---

## 5. API Endpoints

```
POST   /api/db/profiles              Create connection profile
GET    /api/db/profiles              List all profiles
GET    /api/db/profiles/{id}         Get profile details
PUT    /api/db/profiles/{id}         Update profile
DELETE /api/db/profiles/{id}         Delete profile

POST   /api/db/profiles/{id}/test    Test connection
GET    /api/db/profiles/{id}/health  Health snapshot

POST   /api/db/diagnostics/start     Launch diagnostic run
GET    /api/db/diagnostics/{run_id}  Get run status + findings
GET    /api/db/diagnostics/history   List past runs (by profile)

WS     /api/db/ws/{run_id}           Live diagnostic progress

# P1
GET    /api/db/profiles/{id}/metrics?range=1h   Time-series data
POST   /api/db/alerts                Create alert rule
GET    /api/db/alerts                List alert rules
DELETE /api/db/alerts/{id}           Delete alert rule
GET    /api/db/alerts/history        Alert fire/resolve history

# P2
POST   /api/db/remediation/plan      Generate remediation plan
POST   /api/db/remediation/approve   Approve plan (returns JWT token)
POST   /api/db/remediation/execute   Execute approved plan
GET    /api/db/remediation/log       Execution audit log
```

---

## 6. Data Models (Key Pydantic Models)

```python
class DBProfile(BaseModel):
    id: str                     # UUID
    name: str                   # "prod-pg"
    engine: Literal["postgresql", "mongodb", "mysql", "oracle"]
    host: str
    port: int
    database: str
    credentials: EncryptedCredentials
    created_at: datetime
    tags: dict[str, str] = {}

class DiagnosticRun(BaseModel):
    run_id: str
    profile_id: str
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    completed_at: Optional[datetime]
    findings: list[DBFinding]
    summary: str

class DBFinding(BaseModel):
    finding_id: str
    category: Literal["query_performance", "replication", "connections",
                       "storage", "schema", "locks", "memory"]
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: float           # 0.0 - 1.0
    title: str
    detail: str
    evidence: list[str]
    recommendation: Optional[str]
    remediation_available: bool  # P2: can we auto-fix this?

class RemediationPlan(BaseModel):    # P2
    plan_id: str
    finding_id: str
    action: str                 # "add_index", "kill_query", "vacuum", etc.
    sql_preview: str            # What will be executed
    impact_assessment: str      # "~2min lock on 1.2M row table"
    rollback_sql: Optional[str]
    requires_downtime: bool
```

---

## 7. File Structure

```
backend/src/
├── agents/database/
│   ├── __init__.py
│   ├── graph.py              # LangGraph StateGraph
│   ├── query_agent.py        # DBQueryAgent(ReActAgent)
│   ├── health_agent.py       # DBHealthAgent(ReActAgent)
│   ├── schema_agent.py       # DBSchemaAgent(ReActAgent) — P1
│   └── remediation_agent.py  # DBRemediationAgent(ReActAgent) — P2
├── database/
│   ├── __init__.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py           # DatabaseAdapter(ABC)
│   │   ├── registry.py       # DatabaseAdapterRegistry
│   │   ├── postgres.py       # PostgresAdapter (P0)
│   │   ├── mongodb.py        # MongoDBAdapter (P1)
│   │   ├── mysql.py          # MySQLAdapter (P1)
│   │   └── oracle.py         # OracleAdapter (P2)
│   ├── models.py             # Pydantic: profiles, runs, findings, plans
│   ├── profile_store.py      # Profile CRUD (SQLite, encrypted creds)
│   ├── diagnostic_store.py   # Run history persistence
│   ├── monitoring_engine.py  # Polling loop + alert eval (P1)
│   └── remediation_engine.py # Saga executor + rollback (P2)
├── api/
│   └── db_endpoints.py       # FastAPI router /api/db/*

frontend/src/components/
├── Database/
│   ├── DBLayout.tsx              # Page shell: sidebar + content area
│   ├── DBSidebar.tsx             # Capability navigation sidebar
│   ├── DBOverview.tsx            # Fleet health cards grid
│   ├── DBConnections.tsx         # Profile CRUD table
│   ├── DBProfileForm.tsx         # Create/edit profile modal
│   ├── DBDiagnostics.tsx         # Run history + findings
│   ├── DBDiagnosticRun.tsx       # Single run detail view
│   ├── DBHealthGauge.tsx         # Circular gauge (reusable)
│   ├── QueryPlanViewer.tsx       # EXPLAIN tree renderer
│   ├── SlowQueryTable.tsx        # Sortable slow query list
│   ├── DBMonitoring.tsx          # Time-series charts + alerts (P1)
│   ├── DBAlertRuleEditor.tsx     # Alert rule CRUD form (P1)
│   ├── DBSchema.tsx              # Schema browser + detail (P1)
│   ├── SchemaCompareView.tsx     # Side-by-side schema diff (P1)
│   ├── DBOperations.tsx          # Remediation console (P2)
│   └── RemediationApprovalCard.tsx  # Plan + approve/reject (P2)
```

---

## 8. Phasing

| Phase | Sprint | Scope | DB Engines |
|-------|--------|-------|-----------|
| **P0** | 1-2 | Adapter base + PostgreSQL + Registry + QueryAgent + HealthAgent + Dashboard (Health + Diagnostics tabs) | PostgreSQL |
| **P1** | 3-4 | MongoDB + MySQL adapters + SchemaAgent + Monitoring tab + Alert engine + Time-series storage | + MongoDB, MySQL |
| **P2** | 5-6 | Oracle adapter + RemediationAgent + Saga executor + Operations tab + Audit log | + Oracle |

**P0 is PostgreSQL-only.** Ship one engine end-to-end before parallelizing. This validates the adapter interface, the graph, and the UI.

---

## 9. Key Design Decisions

1. **Fully standalone** — no War Room integration, no mixing with app diagnostics
2. **Snapshot-first** — diagnostics read from cached snapshots, never hit live DB during analysis
3. **ReActAgent inheritance** — all agents get budget tracking, evidence pins, retry logic for free
4. **Registry pattern** — mirrors FirewallAdapter registry for multi-instance management
5. **4 agents, not 6** — Query, Health, Schema, Remediation. YAGNI on Security and Connection-specific agents.
6. **No critic loop in P0** — add only if synthesis quality data warrants it
7. **One fix at a time** — no batch remediation, serial execution with human approval
8. **Encrypted credentials** — profile store uses Fernet symmetric encryption for DB passwords

# MongoDB Engine Support — Design Document

## Goal

Add MongoDB as a second database engine to the existing database diagnostics capability, reusing the LangGraph V2 graph and 3-analyst pattern (query, health, schema).

## Architecture

**Approach: Engine-Agnostic Graph** — The existing `graph_v2.py` LangGraph calls adapter methods that are engine-independent. We create a `MongoAdapter(DatabaseAdapter)` using Motor (async pymongo) that maps MongoDB operations to existing snapshot types. No graph changes needed.

### MongoDB → Snapshot Mapping

| Existing Snapshot | PostgreSQL Source | MongoDB Equivalent |
|---|---|---|
| `PerfSnapshot` | `pg_stat_database` | `db.serverStatus()` |
| `ActiveQuery[]` | `pg_stat_activity` | `db.currentOp()` |
| `ConnectionPoolSnapshot` | Connection counts | `serverStatus.connections` |
| `SchemaSnapshot` | `pg_tables` + `pg_indexes` | `getCollectionInfos()` + `collStats` |
| `ReplicationSnapshot` | `pg_stat_replication` | `replSetGetStatus` |
| `TableDetail` | Column types + indexes | `collStats` + `listIndexes` |
| `QueryResult` (explain) | `EXPLAIN ANALYZE` | `cursor.explain("executionStats")` |

## Backend Components

### 1. MongoAdapter (`backend/src/database/adapters/mongo.py`)

- Extends `DatabaseAdapter` base class
- Constructor: `host, port, database, username, password, connection_uri=None`
- If `connection_uri` provided, use directly; else build URI from fields
- Motor `AsyncIOMotorClient` with `serverSelectionTimeoutMS=10000`
- Implements all 7 abstract `_fetch_*` methods + `execute_diagnostic_query`
- `kill_query()` via `db.command("killOp", op=opid)`; other write ops stubbed P2

### 2. MongoDB Read Tools (`backend/src/agents/database/tools/mongo_read_tools.py`)

7 tools mirroring `pg_read_tools.py`:

| Tool | MongoDB Command |
|---|---|
| `run_explain` | `collection.find(query).explain("executionStats")` |
| `query_current_ops` | `db.current_op()` |
| `query_server_status` | `db.command("serverStatus")` |
| `query_collection_stats` | `db.command("collStats", collection)` |
| `inspect_collection_indexes` | `collection.list_indexes()` |
| `get_connection_info` | `serverStatus.connections` |
| `get_replication_status` | `db.command("replSetGetStatus")` |

All tools return `{summary, artifact_id, evidence_id}` pattern matching PG tools.

### 3. Adapter Resolution Updates

- `db_endpoints.py`: Add `elif profile["engine"] == "mongodb"` branch
- `routes_v4.py` `run_db_diagnosis()`: Same branch for MongoAdapter instantiation

### 4. Prompt Template Adjustments

- Add MongoDB terminology context (collections vs tables, documents vs rows, BSON types) to analyst system prompts
- Conditional sections based on `engine` in state

### 5. Dependency

- Add `motor>=3.3` to requirements

## Frontend Components

### 1. Type Changes (`types/index.ts`)

- `database_type: 'postgres' | 'mongodb'`
- Add optional `connection_uri?: string` to `DatabaseDiagnosticsForm`

### 2. Form Updates (`DatabaseDiagnosticsFields.tsx`)

- Engine auto-detected from selected profile (`profile.engine` field)
- When MongoDB selected:
  - Show connection URI field + "Advanced" toggle for individual host/port/db fields
  - Hide "Include EXPLAIN ANALYZE" checkbox (MongoDB explain works differently — always available)
  - Focus areas: rename "schema" label to "Collections" in UI
- When PostgreSQL: unchanged behavior

### 3. Visualization Components

Existing components work as-is — they consume generic data shapes:
- `ConnectionPoolGauge` — active/idle/waiting/max numbers
- `SlowQueryTimeline` — pid/duration_ms/query objects
- `ExplainPlanTree` — tree nodes with cost/rows (MongoDB explain maps to same structure)

## Testing

- `test_mongo_adapter.py` — Unit tests with mocked Motor client
- `test_mongo_read_tools.py` — Tool output format validation
- `test_db_graph_v2.py` — Add test with mock MongoAdapter (graph should work identically)

## Files Changed

| File | Action |
|---|---|
| `backend/src/database/adapters/mongo.py` | **Create** — MongoAdapter class |
| `backend/src/agents/database/tools/mongo_read_tools.py` | **Create** — 7 read tools |
| `backend/tests/test_mongo_adapter.py` | **Create** — adapter unit tests |
| `backend/tests/test_mongo_read_tools.py` | **Create** — tool tests |
| `backend/src/database/adapters/base.py` | **Modify** — Add `connection_uri` to constructor |
| `backend/src/api/db_endpoints.py` | **Modify** — Add MongoDB adapter branch |
| `backend/src/api/routes_v4.py` | **Modify** — Add MongoDB adapter branch |
| `backend/src/agents/database/prompts/templates.py` | **Modify** — MongoDB-aware prompt sections |
| `backend/requirements.txt` | **Modify** — Add `motor>=3.3` |
| `frontend/src/types/index.ts` | **Modify** — Extend database_type union + add connection_uri |
| `frontend/src/components/ActionCenter/forms/DatabaseDiagnosticsFields.tsx` | **Modify** — MongoDB-specific form fields |
| `backend/tests/test_db_graph_v2.py` | **Modify** — Add MongoDB adapter test |

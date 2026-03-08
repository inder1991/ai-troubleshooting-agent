# Database Monitoring P1 — Design Document

**Date:** 2026-03-09
**Status:** Approved
**Depends on:** Database Diagnostics P0 (shipped)

---

## 1. Overview

Continuous monitoring for PostgreSQL databases. Polls all connected profiles on a configurable interval, writes time-series metrics to InfluxDB, evaluates alert rules via the existing AlertEngine, and renders charts + schema browser in the frontend.

**Scope:** PostgreSQL only. MongoDB/MySQL adapters deferred.

**Not included:** Operations/write actions (P2), remediation (P2).

---

## 2. DBMonitor Service

New class at `backend/src/database/db_monitor.py`. Mirrors `NetworkMonitor` pattern — async polling loop, multi-profile collection, alert evaluation, WebSocket broadcast.

```python
class DBMonitor:
    def __init__(self, profile_store, adapter_registry, metrics_store,
                 alert_engine, broadcast_callback, interval=30):
        ...

    async def start()        # creates asyncio task
    async def stop()
    async def _run_loop()    # sleep(interval) → _collect_cycle()
    async def _collect_cycle()
    async def _collect_profile_metrics(profile, adapter)
    def get_snapshot() → dict  # current state for REST
```

### Collection Cycle

```
_collect_cycle():
  for profile in profile_store.list_all():
      adapter = registry.get_or_create(profile)
      try:
          await adapter.connect()  # no-op if already connected
          await _collect_profile_metrics(profile, adapter)
          await alert_engine.evaluate(f"db:{profile['id']}")
      except Exception:
          mark profile as unreachable
  broadcast({"type": "db_monitor_update", "data": snapshot})
```

### Adapter Registry Integration

`DatabaseAdapterRegistry` gains a `get_or_create(profile)` method that lazily creates and caches adapters by profile ID, reusing existing connections across cycles.

---

## 3. InfluxDB Measurements

Reuses existing `MetricsStore`. New write methods added:

| Measurement | Tags | Fields |
|---|---|---|
| `db_performance` | profile_id, engine | cache_hit_ratio, transactions_per_sec, deadlocks, uptime_seconds |
| `db_connections` | profile_id, engine | active, idle, waiting, max_connections, utilization_pct |
| `db_replication` | profile_id, engine | lag_bytes, lag_seconds, replica_count, is_replica |
| `db_query_latency` | profile_id, engine | slow_count, max_duration_ms, avg_duration_ms, total_active |

New query method: `query_db_metrics(profile_id, metric, duration, resolution)` returns time-series data using Flux QL aggregateWindow.

---

## 4. Alert Rules

Reuses existing `AlertEngine` + `NotificationDispatcher`. New default rules with `entity_type='database'`:

| Rule | Metric | Condition | Threshold | Severity |
|---|---|---|---|---|
| Connection Pool Saturation | db_conn_utilization | gt | 80 | warning |
| Connection Pool Critical | db_conn_utilization | gt | 95 | critical |
| Low Cache Hit Ratio | db_cache_hit_ratio | lt | 0.9 | warning |
| Replication Lag | db_repl_lag_bytes | gt | 10000000 | warning |
| Replication Lag Critical | db_repl_lag_bytes | gt | 100000000 | critical |
| Deadlocks Detected | db_deadlocks | gt | 0 | warning |
| Slow Query Spike | db_slow_query_count | gt | 5 | warning |

Default rules loaded on first startup. Users can create/edit/delete custom rules via API.

---

## 5. Schema Browser

New adapter method on `DatabaseAdapter` ABC:

```python
async def get_table_detail(self, table_name: str) → TableDetail
```

`PostgresAdapter` implements via `pg_stat_user_tables`, `pg_indexes`, `pg_class`, `information_schema.columns`.

**TableDetail model:**
```python
class TableDetail(BaseModel):
    name: str
    schema_name: str = "public"
    columns: list[ColumnInfo]       # name, type, nullable, default, is_pk
    indexes: list[IndexInfo]        # name, columns, unique, size_bytes
    row_estimate: int
    total_size_bytes: int
    bloat_ratio: float              # estimated from pgstattuple or dead tuples
```

The existing `get_schema_snapshot()` returns the table/index/size list. `get_table_detail()` adds column-level and per-table drill-down.

---

## 6. API Endpoints

All under `db_router` (prefix `/api/db`):

### Monitoring
```
GET  /api/db/monitor/status
     → { running, interval, profiles: [{id, name, status, last_collected_at}] }

GET  /api/db/monitor/metrics/{profile_id}/{metric}?duration=1h&resolution=1m
     → { profile_id, metric, points: [{time, value}] }

POST /api/db/monitor/start   → start DBMonitor loop
POST /api/db/monitor/stop    → stop DBMonitor loop
```

### Alerts
```
GET    /api/db/alerts/rules          → list DB-scoped alert rules
POST   /api/db/alerts/rules          → create custom rule
PUT    /api/db/alerts/rules/{id}     → update rule
DELETE /api/db/alerts/rules/{id}     → delete rule
GET    /api/db/alerts/active         → currently firing DB alerts
GET    /api/db/alerts/history?profile_id=X&severity=Y&limit=50
```

### Schema
```
GET  /api/db/schema/{profile_id}
     → { tables, views, functions, total_size_bytes }

GET  /api/db/schema/{profile_id}/table/{table_name}
     → TableDetail (columns, indexes, row_estimate, size, bloat)
```

---

## 7. Frontend

Two new tabs added to `DatabaseLayout` sidebar:

### 7.1 Monitoring Tab (`DBMonitoring.tsx`)

**Layout:**
- Top bar: profile selector, time range (1h/6h/24h/7d), refresh button, monitor start/stop toggle
- Chart grid (2x2): Connections, Cache Hit Ratio, TPS, Replication Lag
- Charts rendered with lightweight inline SVG (polyline paths from point data) — same approach as Observatory
- Below charts: Active Alerts panel (severity badge, message, fired_at, acknowledge button)
- Below alerts: Alert Rules table (name, metric, condition, threshold, severity, enabled toggle, edit/delete)
- Create/Edit Rule modal: name, metric dropdown, condition, threshold, severity, cooldown

### 7.2 Schema Tab (`DBSchema.tsx`)

**Layout:**
- Top bar: profile selector, search filter
- Split panel:
  - Left (30%): tree view with expandable groups (Tables, Views, Functions). Each table shows row count + size badge.
  - Right (70%): selected table detail — columns table (name, type, nullable, default, PK icon), indexes table (name, columns, unique badge, size), size/bloat/row stats header

---

## 8. File Structure

```
backend/src/database/
  db_monitor.py              # DBMonitor polling service
  db_alert_rules.py          # default alert rule definitions
  models.py                  # add TableDetail, ColumnInfo, IndexInfo

backend/src/database/adapters/
  base.py                    # add get_table_detail() to ABC
  postgres.py                # implement get_table_detail()
  mock_adapter.py            # mock get_table_detail()

backend/src/network/
  metrics_store.py           # add write_db_metric(), query_db_metrics()
  alert_engine.py            # no changes (entity_type='database' works already)

backend/src/api/
  db_endpoints.py            # add monitor, alert, schema endpoints
  main.py                    # start DBMonitor on startup

backend/tests/
  test_db_monitor.py
  test_db_schema.py
  test_db_monitor_endpoints.py

frontend/src/components/Database/
  DatabaseLayout.tsx          # add Monitoring + Schema tabs
  DBMonitoring.tsx            # time-series charts + alerts
  DBSchema.tsx                # schema browser
```

---

## 9. Startup Wiring

In `main.py` startup:
```python
# After NetworkMonitor startup
from src.database.db_monitor import DBMonitor
db_monitor = DBMonitor(
    profile_store=_get_db_profile_store(),
    adapter_registry=db_adapter_registry,
    metrics_store=metrics_store,         # same InfluxDB instance
    alert_engine=alert_engine,           # same AlertEngine
    broadcast_callback=manager.broadcast,
)
asyncio.create_task(db_monitor.start())
```

DBMonitor starts automatically if InfluxDB is configured. If not, monitoring endpoints return 503.

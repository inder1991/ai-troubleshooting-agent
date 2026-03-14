"""PostgreSQL adapter using asyncpg."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore

from .base import AdapterHealth, DatabaseAdapter
from ..models import (
    ActiveQuery,
    ColumnInfo,
    ConnectionPoolSnapshot,
    IndexInfo,
    PerfSnapshot,
    QueryResult,
    ReplicaInfo,
    ReplicationSnapshot,
    SchemaSnapshot,
    TableDetail,
)

logger = logging.getLogger(__name__)

QUERY_TIMEOUT_SEC = 10
ROW_LIMIT = 1000


class PostgresAdapter(DatabaseAdapter):
    """PostgreSQL adapter using asyncpg for async connectivity."""

    MAX_CONNECT_RETRIES = 3

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        ttl: int = 300,
        connect_timeout: int = 10,
        query_timeout: int = 30,
    ):
        super().__init__(
            engine="postgresql", host=host, port=port, database=database,
            ttl=ttl, connect_timeout=connect_timeout, query_timeout=query_timeout,
        )
        self._username = username
        self._password = password
        self._conn: Optional[asyncpg.Connection] = None

    async def connect(self) -> None:
        """Connect with retry logic (3 attempts, exponential backoff)."""
        last_err: Optional[Exception] = None
        for attempt in range(1, self.MAX_CONNECT_RETRIES + 1):
            try:
                self._conn = await asyncio.wait_for(
                    asyncpg.connect(
                        host=self.host,
                        port=self.port,
                        database=self.database,
                        user=self._username,
                        password=self._password,
                        timeout=self.connect_timeout,
                    ),
                    timeout=self.connect_timeout,
                )
                self._connected = True
                logger.info("Connected to %s:%s/%s on attempt %d",
                            self.host, self.port, self.database, attempt)
                return
            except Exception as e:
                last_err = e
                if attempt < self.MAX_CONNECT_RETRIES:
                    backoff = 2 ** (attempt - 1)  # 1s, 2s
                    logger.warning(
                        "Connection attempt %d/%d failed (%s), retrying in %ds",
                        attempt, self.MAX_CONNECT_RETRIES, e, backoff,
                    )
                    await asyncio.sleep(backoff)
        raise ConnectionError(
            f"Failed to connect after {self.MAX_CONNECT_RETRIES} attempts: {last_err}"
        )

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
        self._connected = False
        self._invalidate_cache()

    async def health_check(self) -> AdapterHealth:
        if not self._connected or not self._conn:
            return AdapterHealth(status="unreachable", error="Not connected")
        try:
            start = time.time()
            row = await self._conn.fetchrow("SELECT version()")
            latency = (time.time() - start) * 1000
            version = row["version"] if row else ""
            return AdapterHealth(
                status="healthy", latency_ms=round(latency, 2), version=version
            )
        except Exception as e:
            return AdapterHealth(status="degraded", error=str(e))

    async def check_permissions(self) -> dict:
        """Check read permissions on critical pg_stat views."""
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

    async def get_slow_queries_from_stats(self) -> list[dict]:
        """Return top 10 historically slow queries from pg_stat_statements."""
        try:
            rows = await self._conn.fetch("""
                SELECT queryid, query, calls, mean_exec_time,
                       total_exec_time, stddev_exec_time, rows
                FROM pg_stat_statements
                ORDER BY mean_exec_time DESC
                LIMIT 10
            """)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("pg_stat_statements not available: %s", e)
            return []

    async def _fetch_performance_stats(self) -> PerfSnapshot:
        row = await self._conn.fetchrow("""
            SELECT
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') AS active,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle') AS idle,
                (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max,
                COALESCE(
                    (SELECT round(sum(heap_blks_hit)::numeric / NULLIF(sum(heap_blks_hit) + sum(heap_blks_read), 0), 4)
                     FROM pg_statio_user_tables), 0
                ) AS ratio,
                (SELECT xact_commit + xact_rollback FROM pg_stat_database WHERE datname = current_database()) AS tps,
                (SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()) AS deadlocks,
                EXTRACT(EPOCH FROM now() - pg_postmaster_start_time())::int AS uptime
        """)
        return PerfSnapshot(
            connections_active=row["active"],
            connections_idle=row["idle"],
            connections_max=row["max"],
            cache_hit_ratio=float(row["ratio"]),
            transactions_per_sec=float(row["tps"] or 0),
            deadlocks=row["deadlocks"] or 0,
            uptime_seconds=row["uptime"] or 0,
        )

    async def _fetch_active_queries(self) -> list[ActiveQuery]:
        rows = await self._conn.fetch("""
            SELECT pid, query,
                   EXTRACT(EPOCH FROM now() - query_start) * 1000 AS duration_ms,
                   state, usename, datname, wait_event IS NOT NULL AS waiting
            FROM pg_stat_activity
            WHERE state != 'idle' AND pid != pg_backend_pid()
            ORDER BY duration_ms DESC
            LIMIT 50
        """)
        return [
            ActiveQuery(
                pid=r["pid"],
                query=r["query"],
                duration_ms=r["duration_ms"] or 0,
                state=r["state"] or "",
                user=r["usename"] or "",
                database=r["datname"] or "",
                waiting=r["waiting"],
            )
            for r in rows
        ]

    async def _fetch_replication_status(self) -> ReplicationSnapshot:
        is_replica_row = await self._conn.fetchrow(
            "SELECT pg_is_in_recovery() AS is_replica"
        )
        is_replica = is_replica_row["is_replica"] if is_replica_row else False

        replicas = []
        lag_bytes = 0
        if not is_replica:
            rows = await self._conn.fetch("""
                SELECT client_addr, state,
                       pg_wal_lsn_diff(sent_lsn, replay_lsn) AS lag_bytes
                FROM pg_stat_replication
            """)
            replicas = [
                ReplicaInfo(
                    name=str(r["client_addr"] or ""),
                    state=r["state"] or "",
                    lag_bytes=int(r["lag_bytes"] or 0),
                )
                for r in rows
            ]
        else:
            lag_row = await self._conn.fetchrow("""
                SELECT pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()) AS lag
            """)
            lag_bytes = int(lag_row["lag"] or 0) if lag_row else 0

        return ReplicationSnapshot(
            is_replica=is_replica,
            replicas=replicas,
            replication_lag_bytes=lag_bytes,
        )

    async def _fetch_schema_snapshot(self) -> SchemaSnapshot:
        tables = await self._conn.fetch("""
            SELECT relname AS name, n_live_tup AS rows,
                   pg_total_relation_size(c.oid) AS size_bytes
            FROM pg_class c JOIN pg_stat_user_tables s ON c.relname = s.relname
            WHERE c.relkind = 'r'
              AND s.schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            ORDER BY size_bytes DESC LIMIT 100
        """)
        indexes = await self._conn.fetch("""
            SELECT indexrelname AS name, relname AS table,
                   idx_scan, idx_tup_read, idx_tup_fetch,
                   pg_relation_size(indexrelid) AS size_bytes
            FROM pg_stat_user_indexes
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            ORDER BY size_bytes DESC LIMIT 200
        """)
        total_row = await self._conn.fetchrow(
            "SELECT pg_database_size(current_database()) AS total"
        )
        return SchemaSnapshot(
            tables=[dict(r) for r in tables],
            indexes=[dict(r) for r in indexes],
            total_size_bytes=total_row["total"] if total_row else 0,
        )

    async def get_table_detail(self, table_name: str) -> TableDetail:
        if not self._conn:
            raise RuntimeError("Not connected")

        col_rows = await self._conn.fetch("""
            SELECT c.column_name, c.data_type, c.is_nullable, c.column_default,
                   CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END AS is_pk
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                  ON tc.constraint_name = ku.constraint_name
                WHERE tc.table_name = $1 AND tc.constraint_type = 'PRIMARY KEY'
            ) pk ON pk.column_name = c.column_name
            WHERE c.table_name = $1 AND c.table_schema = 'public'
            ORDER BY c.ordinal_position
        """, table_name)

        columns = [
            ColumnInfo(
                name=r["column_name"], data_type=r["data_type"],
                nullable=r["is_nullable"] == "YES",
                default=r["column_default"], is_pk=r["is_pk"],
            ) for r in col_rows
        ]

        idx_rows = await self._conn.fetch("""
            SELECT indexname, indexdef,
                   pg_relation_size(quote_ident(indexname)::regclass) AS size_bytes
            FROM pg_indexes
            WHERE tablename = $1 AND schemaname = 'public'
        """, table_name)

        indexes = [
            IndexInfo(
                name=r["indexname"], columns=[],
                unique="UNIQUE" in (r["indexdef"] or ""),
                size_bytes=r["size_bytes"] or 0,
            ) for r in idx_rows
        ]

        stat_row = await self._conn.fetchrow("""
            SELECT n_live_tup AS row_estimate,
                   pg_total_relation_size(quote_ident($1)::regclass) AS total_size,
                   CASE WHEN n_live_tup > 0
                     THEN n_dead_tup::float / n_live_tup
                     ELSE 0 END AS bloat_ratio
            FROM pg_stat_user_tables WHERE relname = $1
        """, table_name)

        return TableDetail(
            name=table_name, schema_name="public", columns=columns, indexes=indexes,
            row_estimate=stat_row["row_estimate"] if stat_row else 0,
            total_size_bytes=stat_row["total_size"] if stat_row else 0,
            bloat_ratio=round(stat_row["bloat_ratio"], 4) if stat_row else 0.0,
        )

    async def _fetch_connection_pool(self) -> ConnectionPoolSnapshot:
        row = await self._conn.fetchrow("""
            SELECT
                count(*) FILTER (WHERE state = 'active') AS active,
                count(*) FILTER (WHERE state = 'idle') AS idle,
                count(*) FILTER (WHERE wait_event IS NOT NULL AND state != 'idle') AS waiting,
                (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_conn
            FROM pg_stat_activity
        """)
        return ConnectionPoolSnapshot(
            active=row["active"],
            idle=row["idle"],
            waiting=row["waiting"],
            max_connections=row["max_conn"],
        )

    # ── Diagnostic accessors ──

    async def get_wait_events(self) -> list[dict]:
        """Return current wait events grouped by type."""
        try:
            rows = await asyncio.wait_for(
                self._conn.fetch("""
                    SELECT wait_event_type, wait_event, count(*) AS cnt,
                           array_agg(pid) AS pids
                    FROM pg_stat_activity
                    WHERE wait_event IS NOT NULL AND pid != pg_backend_pid()
                    GROUP BY 1, 2
                    ORDER BY cnt DESC
                    LIMIT 10
                """),
                timeout=self.query_timeout,
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_wait_events failed: %s", e)
            return []

    async def get_lock_chains(self) -> list[dict]:
        """Return blocking lock chains (who blocks whom)."""
        try:
            rows = await asyncio.wait_for(
                self._conn.fetch("""
                    SELECT
                        blocked.pid AS blocked_pid,
                        blocked.usename AS blocked_user,
                        blocked.query AS blocked_query,
                        blocking.pid AS blocking_pid,
                        blocking.usename AS blocking_user,
                        blocking.query AS blocking_query
                    FROM pg_locks bl
                    JOIN pg_stat_activity blocked ON bl.pid = blocked.pid
                    JOIN pg_locks kl ON bl.locktype = kl.locktype
                        AND bl.database IS NOT DISTINCT FROM kl.database
                        AND bl.relation IS NOT DISTINCT FROM kl.relation
                        AND bl.page IS NOT DISTINCT FROM kl.page
                        AND bl.tuple IS NOT DISTINCT FROM kl.tuple
                        AND bl.virtualxid IS NOT DISTINCT FROM kl.virtualxid
                        AND bl.transactionid IS NOT DISTINCT FROM kl.transactionid
                        AND bl.classid IS NOT DISTINCT FROM kl.classid
                        AND bl.objid IS NOT DISTINCT FROM kl.objid
                        AND bl.objsubid IS NOT DISTINCT FROM kl.objsubid
                        AND bl.pid != kl.pid
                    JOIN pg_stat_activity blocking ON kl.pid = blocking.pid
                    WHERE NOT bl.granted AND kl.granted
                        AND blocked.pid != pg_backend_pid()
                        AND blocking.pid != pg_backend_pid()
                    LIMIT 5
                """),
                timeout=self.query_timeout,
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_lock_chains failed: %s", e)
            return []

    async def get_long_transactions(self) -> list[dict]:
        """Return transactions idle in transaction > 5 minutes."""
        try:
            rows = await asyncio.wait_for(
                self._conn.fetch("""
                    SELECT pid, usename, state, query,
                           EXTRACT(EPOCH FROM now() - xact_start)::int AS age_seconds
                    FROM pg_stat_activity
                    WHERE state = 'idle in transaction'
                        AND EXTRACT(EPOCH FROM now() - xact_start) > 300
                        AND pid != pg_backend_pid()
                    ORDER BY age_seconds DESC
                    LIMIT 5
                """),
                timeout=self.query_timeout,
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_long_transactions failed: %s", e)
            return []

    async def get_autovacuum_status(self) -> dict:
        """Return running vacuums and stale tables needing vacuum."""
        result: dict = {"running": [], "stale": []}
        try:
            running = await asyncio.wait_for(
                self._conn.fetch("""
                    SELECT pid, datname, relid::regclass::text AS table_name,
                           phase, heap_blks_total, heap_blks_scanned
                    FROM pg_stat_progress_vacuum
                """),
                timeout=self.query_timeout,
            )
            result["running"] = [dict(r) for r in running]
        except Exception as e:
            logger.warning("get_autovacuum_status (running) failed: %s", e)

        try:
            stale = await asyncio.wait_for(
                self._conn.fetch("""
                    SELECT relname, n_dead_tup, n_live_tup,
                           last_autovacuum, last_autoanalyze
                    FROM pg_stat_user_tables
                    WHERE n_dead_tup > 1000
                      AND schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                    ORDER BY n_dead_tup DESC
                    LIMIT 10
                """),
                timeout=self.query_timeout,
            )
            result["stale"] = [dict(r) for r in stale]
        except Exception as e:
            logger.warning("get_autovacuum_status (stale) failed: %s", e)

        return result

    async def get_table_access_patterns(self) -> list[dict]:
        """Return sequential vs index scan ratios per table."""
        try:
            rows = await asyncio.wait_for(
                self._conn.fetch("""
                    SELECT relname, seq_scan, idx_scan,
                           CASE WHEN seq_scan + idx_scan > 0
                               THEN round(seq_scan::numeric / (seq_scan + idx_scan), 2)
                               ELSE 0
                           END AS seq_scan_ratio
                    FROM pg_stat_user_tables
                    WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                    ORDER BY seq_scan DESC
                    LIMIT 10
                """),
                timeout=self.query_timeout,
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_table_access_patterns failed: %s", e)
            return []

    async def explain_query(self, sql: str) -> dict | None:
        """Run EXPLAIN (FORMAT JSON) with a 10s timeout.

        Safety: uses EXPLAIN only — never EXPLAIN ANALYZE — so the query
        is *not* executed on production.
        """
        if not self._conn:
            return None
        try:
            import json as _json

            row = await self._conn.fetchval(
                f"EXPLAIN (FORMAT JSON) {sql}",
                timeout=QUERY_TIMEOUT_SEC,
            )
            # asyncpg returns a JSON string; parse the first plan node
            plan_list = _json.loads(row) if isinstance(row, str) else row
            if isinstance(plan_list, list) and plan_list:
                return plan_list[0].get("Plan")
            return None
        except Exception as e:
            logger.warning("EXPLAIN failed: %s", e)
            return None

    async def execute_diagnostic_query(self, sql: str) -> QueryResult:
        """Execute a READ-ONLY diagnostic query with timeout and row limit."""
        try:
            start = time.time()
            rows = await asyncio.wait_for(
                self._conn.fetch(
                    f"SELECT * FROM ({sql}) AS q LIMIT {ROW_LIMIT}",
                    timeout=self.query_timeout,
                ),
                timeout=self.query_timeout,
            )
            elapsed = (time.time() - start) * 1000
            return QueryResult(
                query=sql,
                execution_time_ms=round(elapsed, 2),
                rows_returned=len(rows),
            )
        except asyncio.TimeoutError:
            return QueryResult(query=sql, error=f"Query timed out after {self.query_timeout}s")
        except Exception as e:
            return QueryResult(query=sql, error=str(e))

    # ── Write operations (P2) ──

    async def kill_query(self, pid: int) -> dict:
        """Terminate a backend process by PID."""
        # Validate PID exists
        row = await self._conn.fetchrow(
            "SELECT pid, query, state FROM pg_stat_activity WHERE pid = $1", pid
        )
        if not row:
            raise ValueError(f"PID {pid} not found in pg_stat_activity")
        result = await self._conn.fetchval(
            "SELECT pg_terminate_backend($1)", pid
        )
        return {
            "success": bool(result),
            "pid": pid,
            "query": row["query"][:200] if row["query"] else "",
            "message": f"Terminated PID {pid}" if result else f"Failed to terminate PID {pid}",
        }

    async def vacuum_table(self, table: str, full: bool = False, analyze: bool = True) -> dict:
        """VACUUM [FULL] [ANALYZE] a table."""
        # Validate table exists
        exists = await self._conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = $1)", table
        )
        if not exists:
            raise ValueError(f"Table '{table}' does not exist")
        parts = ["VACUUM"]
        if full:
            parts.append("FULL")
        if analyze:
            parts.append("ANALYZE")
        parts.append(table)
        sql = " ".join(parts)
        await self._conn.execute(sql)
        return {"success": True, "table": table, "full": full, "analyze": analyze, "sql": sql}

    async def reindex_table(self, table: str) -> dict:
        """REINDEX TABLE CONCURRENTLY."""
        exists = await self._conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = $1)", table
        )
        if not exists:
            raise ValueError(f"Table '{table}' does not exist")
        sql = f"REINDEX TABLE CONCURRENTLY {table}"
        await self._conn.execute(sql)
        return {"success": True, "table": table, "sql": sql}

    async def create_index(self, table: str, columns: list[str],
                           name: str | None = None, unique: bool = False) -> dict:
        """CREATE INDEX CONCURRENTLY."""
        # Validate table and columns exist
        exists = await self._conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = $1)", table
        )
        if not exists:
            raise ValueError(f"Table '{table}' does not exist")
        for col in columns:
            col_exists = await self._conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name = $1 AND column_name = $2)",
                table, col,
            )
            if not col_exists:
                raise ValueError(f"Column '{col}' does not exist on table '{table}'")
        idx_name = name or f"idx_{table}_{'_'.join(columns)}"
        unique_kw = "UNIQUE " if unique else ""
        col_list = ", ".join(columns)
        sql = f"CREATE {unique_kw}INDEX CONCURRENTLY {idx_name} ON {table} ({col_list})"
        await self._conn.execute(sql)
        return {"success": True, "index_name": idx_name, "table": table, "columns": columns, "sql": sql}

    async def drop_index(self, index_name: str) -> dict:
        """DROP INDEX CONCURRENTLY. Prevents dropping PK indexes."""
        # Check index exists and is not a PK constraint
        idx = await self._conn.fetchrow(
            """SELECT indexname, tablename FROM pg_indexes
               WHERE indexname = $1""", index_name
        )
        if not idx:
            raise ValueError(f"Index '{index_name}' does not exist")
        # Check if it backs a primary key
        is_pk = await self._conn.fetchval(
            """SELECT EXISTS(
                SELECT 1 FROM pg_constraint
                WHERE conname = $1 AND contype = 'p'
            )""", index_name
        )
        if is_pk:
            raise ValueError(f"Cannot drop primary key index '{index_name}'")
        sql = f"DROP INDEX CONCURRENTLY {index_name}"
        await self._conn.execute(sql)
        return {"success": True, "index_name": index_name, "sql": sql}

    async def _alter_config_impl(self, param: str, value: str) -> dict:
        """ALTER SYSTEM SET + pg_reload_conf()."""
        await self._conn.execute(f"ALTER SYSTEM SET {param} = '{value}'")
        await self._conn.execute("SELECT pg_reload_conf()")
        return {"success": True, "param": param, "value": value, "reload": True}

    async def get_config_recommendations(self) -> list[dict]:
        """Compare current pg_settings against heuristics."""
        rows = await self._conn.fetch(
            """SELECT name, setting, unit, context, short_desc
               FROM pg_settings
               WHERE name IN ('shared_buffers', 'work_mem', 'maintenance_work_mem',
                              'effective_cache_size', 'max_connections',
                              'random_page_cost', 'effective_io_concurrency',
                              'checkpoint_completion_target', 'wal_buffers',
                              'statement_timeout', 'idle_in_transaction_session_timeout')"""
        )
        # Simple heuristic recommendations
        recs = []
        for row in rows:
            name, setting, unit = row["name"], row["setting"], row["unit"] or ""
            rec = self._recommend_config(name, setting, unit)
            if rec:
                recs.append({
                    "param": name,
                    "current_value": f"{setting}{unit}",
                    "recommended_value": rec["value"],
                    "reason": rec["reason"],
                    "requires_restart": row["context"] == "postmaster",
                })
        return recs

    @staticmethod
    def _recommend_config(name: str, setting: str, unit: str) -> dict | None:
        """Simple heuristic config recommendations."""
        try:
            val = int(setting)
        except (ValueError, TypeError):
            return None
        recommendations = {
            "shared_buffers": (lambda v: v < 32768, "256MB", "Should be ~25% of RAM"),
            "work_mem": (lambda v: v < 16384, "64MB", "Better sort/hash performance"),
            "maintenance_work_mem": (lambda v: v < 65536, "256MB", "Faster VACUUM and index builds"),
            "random_page_cost": (lambda v: v > 2, "1.1", "SSD-appropriate value"),
            "effective_io_concurrency": (lambda v: v < 100, "200", "SSD-appropriate value"),
            "checkpoint_completion_target": (lambda v: v < 0.9, "0.9", "Spread checkpoint I/O"),
            "statement_timeout": (lambda v: v == 0, "30000", "30s timeout prevents runaway queries"),
        }
        if name in recommendations:
            check, rec_val, reason = recommendations[name]
            if check(val):
                return {"value": rec_val, "reason": reason}
        return None

    async def generate_failover_runbook(self) -> dict:
        """Generate a failover runbook based on current replication state."""
        repl = await self.get_replication_status()
        is_replica = repl.is_replica
        replicas = [r.model_dump() for r in repl.replicas]
        steps = []
        if is_replica:
            steps = [
                {"order": 1, "description": "This server IS a replica. To promote:", "command": "SELECT pg_promote();"},
                {"order": 2, "description": "Verify promotion", "command": "SELECT pg_is_in_recovery(); -- Should return false"},
                {"order": 3, "description": "Update application connection strings", "command": "-- Point apps to new primary"},
            ]
        elif replicas:
            steps = [
                {"order": 1, "description": f"Verify replica health ({len(replicas)} replicas)", "command": "SELECT * FROM pg_stat_replication;"},
                {"order": 2, "description": "Check replication lag is minimal", "command": "SELECT client_addr, replay_lag FROM pg_stat_replication;"},
                {"order": 3, "description": "Stop writes on primary", "command": "-- Drain connections or set default_transaction_read_only = on"},
                {"order": 4, "description": "Promote chosen replica", "command": "-- On replica: SELECT pg_promote();"},
                {"order": 5, "description": "Update DNS/connection strings", "command": "-- Point apps to new primary"},
                {"order": 6, "description": "Verify new primary", "command": "SELECT pg_is_in_recovery(); -- Should return false"},
            ]
        else:
            steps = [
                {"order": 1, "description": "No replicas configured", "command": "-- Set up streaming replication first"},
            ]
        return {
            "is_replica": is_replica,
            "replica_count": len(replicas),
            "replicas": replicas,
            "steps": steps,
            "warnings": ["Failover causes brief downtime", "Ensure replica is caught up before promoting"],
            "estimated_downtime": "30-60 seconds",
        }

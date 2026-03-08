"""PostgreSQL adapter using asyncpg."""
from __future__ import annotations

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

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        ttl: int = 300,
    ):
        super().__init__(
            engine="postgresql", host=host, port=port, database=database, ttl=ttl
        )
        self._username = username
        self._password = password
        self._conn: Optional[asyncpg.Connection] = None

    async def connect(self) -> None:
        self._conn = await asyncpg.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self._username,
            password=self._password,
            timeout=10,
        )
        self._connected = True

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
            ORDER BY size_bytes DESC LIMIT 100
        """)
        indexes = await self._conn.fetch("""
            SELECT indexrelname AS name, relname AS table,
                   idx_scan, idx_tup_read, idx_tup_fetch,
                   pg_relation_size(indexrelid) AS size_bytes
            FROM pg_stat_user_indexes
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

    async def execute_diagnostic_query(self, sql: str) -> QueryResult:
        """Execute a READ-ONLY diagnostic query with timeout and row limit."""
        try:
            start = time.time()
            rows = await self._conn.fetch(
                f"SELECT * FROM ({sql}) AS q LIMIT {ROW_LIMIT}",
                timeout=QUERY_TIMEOUT_SEC,
            )
            elapsed = (time.time() - start) * 1000
            return QueryResult(
                query=sql,
                execution_time_ms=round(elapsed, 2),
                rows_returned=len(rows),
            )
        except Exception as e:
            return QueryResult(query=sql, error=str(e))

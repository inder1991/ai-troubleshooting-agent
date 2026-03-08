"""Mock database adapter for testing."""
from __future__ import annotations

from .base import AdapterHealth, DatabaseAdapter
from ..models import (
    ActiveQuery,
    ColumnInfo,
    ConnectionPoolSnapshot,
    IndexInfo,
    PerfSnapshot,
    QueryResult,
    ReplicationSnapshot,
    SchemaSnapshot,
    TableDetail,
)


class MockDatabaseAdapter(DatabaseAdapter):
    """In-memory mock adapter returning synthetic data."""

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False
        self._invalidate_cache()

    async def health_check(self) -> AdapterHealth:
        if not self._connected:
            return AdapterHealth(status="unreachable", error="Not connected")
        return AdapterHealth(status="healthy", latency_ms=1.2, version="MockDB 1.0")

    async def _fetch_performance_stats(self) -> PerfSnapshot:
        return PerfSnapshot(
            connections_active=12,
            connections_idle=5,
            connections_max=100,
            cache_hit_ratio=0.94,
            transactions_per_sec=150.0,
            deadlocks=0,
            uptime_seconds=86400,
        )

    async def _fetch_active_queries(self) -> list[ActiveQuery]:
        return [
            ActiveQuery(
                pid=1001,
                query="SELECT * FROM orders WHERE created_at > now() - interval '1h'",
                duration_ms=3200,
                state="active",
                user="app",
                database=self.database,
            ),
            ActiveQuery(
                pid=1002,
                query="UPDATE users SET last_login = now()",
                duration_ms=150,
                state="active",
                user="app",
                database=self.database,
            ),
        ]

    async def _fetch_replication_status(self) -> ReplicationSnapshot:
        return ReplicationSnapshot(
            is_replica=False, replicas=[], replication_lag_bytes=0
        )

    async def _fetch_schema_snapshot(self) -> SchemaSnapshot:
        return SchemaSnapshot(
            tables=[
                {"name": "orders", "rows": 1200000, "size_bytes": 256000000}
            ],
            indexes=[
                {"name": "pk_orders", "table": "orders", "columns": ["id"]}
            ],
            total_size_bytes=256000000,
        )

    async def _fetch_connection_pool(self) -> ConnectionPoolSnapshot:
        return ConnectionPoolSnapshot(
            active=12, idle=5, waiting=0, max_connections=100
        )

    async def get_table_detail(self, table_name: str) -> TableDetail:
        return TableDetail(
            name=table_name, schema_name="public",
            columns=[
                ColumnInfo(name="id", data_type="integer", nullable=False, is_pk=True),
                ColumnInfo(name="name", data_type="varchar(255)", nullable=True),
                ColumnInfo(name="created_at", data_type="timestamp", nullable=False),
            ],
            indexes=[
                IndexInfo(name=f"pk_{table_name}", columns=["id"], unique=True, size_bytes=8192),
                IndexInfo(name=f"idx_{table_name}_created", columns=["created_at"], unique=False, size_bytes=16384),
            ],
            row_estimate=120000, total_size_bytes=256000000, bloat_ratio=0.05,
        )

    async def execute_diagnostic_query(self, sql: str) -> QueryResult:
        return QueryResult(query=sql, execution_time_ms=1.5, rows_returned=1)

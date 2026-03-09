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

    # ── Write operations (P2) ──

    async def kill_query(self, pid: int) -> dict:
        return {"success": True, "pid": pid, "message": f"Terminated PID {pid}"}

    async def vacuum_table(self, table: str, full: bool = False, analyze: bool = True) -> dict:
        return {"success": True, "table": table, "full": full, "analyze": analyze}

    async def reindex_table(self, table: str) -> dict:
        return {"success": True, "table": table, "message": f"Reindexed {table}"}

    async def create_index(self, table: str, columns: list[str],
                           name: str | None = None, unique: bool = False) -> dict:
        idx_name = name or f"idx_{table}_{'_'.join(columns)}"
        return {"success": True, "index_name": idx_name, "table": table, "columns": columns, "unique": unique}

    async def drop_index(self, index_name: str) -> dict:
        return {"success": True, "index_name": index_name, "message": f"Dropped {index_name}"}

    async def _alter_config_impl(self, param: str, value: str) -> dict:
        return {"success": True, "param": param, "value": value, "reload": True}

    async def get_config_recommendations(self) -> list[dict]:
        return [
            {"param": "shared_buffers", "current_value": "128MB", "recommended_value": "1GB", "reason": "25% of 4GB RAM", "requires_restart": True},
            {"param": "work_mem", "current_value": "4MB", "recommended_value": "64MB", "reason": "Better sort performance", "requires_restart": False},
            {"param": "effective_cache_size", "current_value": "4GB", "recommended_value": "3GB", "reason": "75% of RAM", "requires_restart": False},
        ]

    async def generate_failover_runbook(self) -> dict:
        return {
            "steps": [
                {"order": 1, "description": "Verify replica health", "command": "SELECT pg_is_in_recovery();"},
                {"order": 2, "description": "Check replication lag", "command": "SELECT * FROM pg_stat_replication;"},
                {"order": 3, "description": "Promote replica", "command": "SELECT pg_promote();"},
                {"order": 4, "description": "Update connection strings", "command": "-- Update application config"},
                {"order": 5, "description": "Verify new primary", "command": "SELECT pg_is_in_recovery(); -- Should return false"},
            ],
            "warnings": ["This will cause brief downtime", "Ensure replica is caught up before promoting"],
            "estimated_downtime": "30-60 seconds",
        }

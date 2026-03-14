"""Mock database adapter for testing."""
from __future__ import annotations

import random

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

    async def check_permissions(self) -> dict:
        return {
            'pg_stat_activity': True,
            'pg_stat_user_tables': True,
            'pg_stat_user_indexes': True,
            'pg_stat_replication': True,
        }

    async def get_slow_queries_from_stats(self) -> list[dict]:
        return [
            {
                'queryid': 100001,
                'query': 'SELECT o.*, u.email FROM orders o JOIN users u ON o.user_id = u.id WHERE o.created_at > $1',
                'calls': 48210,
                'mean_exec_time': 245.7,
                'total_exec_time': 11840397.0,
                'stddev_exec_time': 180.3,
                'rows': 962100,
            },
            {
                'queryid': 100002,
                'query': 'UPDATE inventory SET stock = stock - $1 WHERE product_id = $2',
                'calls': 15320,
                'mean_exec_time': 128.4,
                'total_exec_time': 1966988.0,
                'stddev_exec_time': 95.1,
                'rows': 15320,
            },
            {
                'queryid': 100003,
                'query': 'SELECT COUNT(*) FROM audit_log WHERE timestamp > $1 GROUP BY event_type',
                'calls': 890,
                'mean_exec_time': 1842.6,
                'total_exec_time': 1639914.0,
                'stddev_exec_time': 620.5,
                'rows': 4450,
            },
        ]

    async def _fetch_performance_stats(self) -> PerfSnapshot:
        return PerfSnapshot(
            connections_active=87,
            connections_idle=8,
            connections_max=100,
            cache_hit_ratio=round(random.uniform(0.78, 0.92), 2),
            transactions_per_sec=round(random.uniform(800, 1500), 1),
            deadlocks=random.randint(0, 5),
            uptime_seconds=1209600,  # 14 days
        )

    async def _fetch_active_queries(self) -> list[ActiveQuery]:
        return [
            ActiveQuery(pid=4201, query="SELECT o.*, u.email, p.amount FROM orders o JOIN users u ON o.user_id = u.id JOIN payments p ON o.id = p.order_id WHERE o.created_at > now() - interval '24h' ORDER BY o.total DESC", duration_ms=random.randint(6000, 35000), state="active", user="app_backend", database=self.database),
            ActiveQuery(pid=4202, query="UPDATE inventory SET stock = stock - 1 WHERE product_id IN (SELECT product_id FROM order_items WHERE order_id = 98234)", duration_ms=random.randint(6000, 35000), state="active", user="app_backend", database=self.database),
            ActiveQuery(pid=4203, query="SELECT COUNT(*) FROM events WHERE timestamp > now() - interval '7d' GROUP BY event_type", duration_ms=random.randint(6000, 35000), state="active", user="analytics", database=self.database),
            ActiveQuery(pid=4204, query="INSERT INTO audit_log SELECT * FROM staging_audit", duration_ms=2100, state="idle in transaction", user="etl_worker", database=self.database),
        ]

    async def _fetch_replication_status(self) -> ReplicationSnapshot:
        return ReplicationSnapshot(
            is_replica=False,
            replicas=[
                ReplicaInfo(name="replica-east-1", state="streaming", lag_bytes=1024, lag_seconds=0.5),
                ReplicaInfo(name="replica-west-1", state="streaming", lag_bytes=524288, lag_seconds=12.3),
                ReplicaInfo(name="replica-eu-1", state="catchup", lag_bytes=2097152, lag_seconds=45.0),
            ],
            replication_lag_bytes=524288,
            replication_lag_seconds=12.3,
        )

    async def _fetch_schema_snapshot(self) -> SchemaSnapshot:
        return SchemaSnapshot(
            tables=[
                {"name": "orders", "rows": 1200000, "size_bytes": 256000000},
                {"name": "users", "rows": 450000, "size_bytes": 128000000},
                {"name": "payments", "rows": 890000, "size_bytes": 192000000},
                {"name": "inventory", "rows": 35000, "size_bytes": 24000000},
                {"name": "audit_log", "rows": 5400000, "size_bytes": 1024000000},
            ],
            indexes=[
                {"name": "pk_orders", "table": "orders", "columns": ["id"]},
                {"name": "idx_orders_created", "table": "orders", "columns": ["created_at"]},
                {"name": "pk_users", "table": "users", "columns": ["id"]},
                {"name": "idx_users_email", "table": "users", "columns": ["email"]},
            ],
            total_size_bytes=1624000000,
        )

    async def _fetch_connection_pool(self) -> ConnectionPoolSnapshot:
        return ConnectionPoolSnapshot(active=random.randint(75, 95), idle=8, waiting=random.randint(0, 8), max_connections=100)

    async def get_table_detail(self, table_name: str) -> TableDetail:
        table_data = {
            "orders": {"bloat": 0.42, "rows": 1200000, "size": 256000000, "indexes": [
                IndexInfo(name="pk_orders", columns=["id"], unique=True, size_bytes=32768, scan_count=1450000),
                IndexInfo(name="idx_orders_created", columns=["created_at"], unique=False, size_bytes=65536, scan_count=328000),
                IndexInfo(name="idx_orders_status_legacy", columns=["status"], unique=False, size_bytes=49152, scan_count=0),
            ]},
            "users": {"bloat": 0.08, "rows": 450000, "size": 128000000, "indexes": [
                IndexInfo(name="pk_users", columns=["id"], unique=True, size_bytes=16384, scan_count=2100000),
                IndexInfo(name="idx_users_email", columns=["email"], unique=True, size_bytes=24576, scan_count=870000),
            ]},
            "payments": {"bloat": 0.23, "rows": 890000, "size": 192000000, "indexes": [
                IndexInfo(name="pk_payments", columns=["id"], unique=True, size_bytes=28672, scan_count=920000),
                IndexInfo(name="idx_payments_order_id", columns=["order_id"], unique=False, size_bytes=36864, scan_count=415000),
            ]},
            "inventory": {"bloat": 0.03, "rows": 35000, "size": 24000000, "indexes": [
                IndexInfo(name="pk_inventory", columns=["id"], unique=True, size_bytes=8192, scan_count=67000),
            ]},
            "audit_log": {"bloat": 0.67, "rows": 5400000, "size": 1024000000, "indexes": [
                IndexInfo(name="pk_audit_log", columns=["id"], unique=True, size_bytes=131072, scan_count=540000),
                IndexInfo(name="idx_audit_log_ts", columns=["timestamp"], unique=False, size_bytes=262144, scan_count=12400),
                IndexInfo(name="idx_audit_old_format", columns=["legacy_id"], unique=False, size_bytes=196608, scan_count=0),
            ]},
        }
        data = table_data.get(table_name, {"bloat": 0.05, "rows": 0, "size": 0, "indexes": []})
        base_bloat = data["bloat"]
        varied_bloat = max(0.0, min(1.0, round(base_bloat + random.uniform(-0.05, 0.1), 2)))
        return TableDetail(
            name=table_name, schema_name="public",
            columns=[
                ColumnInfo(name="id", data_type="integer", nullable=False, is_pk=True),
                ColumnInfo(name="name", data_type="varchar(255)", nullable=True),
                ColumnInfo(name="created_at", data_type="timestamp", nullable=False),
            ],
            indexes=data["indexes"],
            row_estimate=data["rows"], total_size_bytes=data["size"], bloat_ratio=varied_bloat,
        )

    # ── Diagnostic accessors ──

    async def get_wait_events(self) -> list[dict]:
        return [
            {"wait_event_type": "Lock", "wait_event": "relation", "cnt": 5, "pids": [4201, 4202, 4210, 4215, 4220]},
            {"wait_event_type": "IO", "wait_event": "DataFileRead", "cnt": 3, "pids": [4203, 4207, 4211]},
            {"wait_event_type": "LWLock", "wait_event": "BufferMapping", "cnt": 2, "pids": [4205, 4206]},
        ]

    async def get_lock_chains(self) -> list[dict]:
        return [
            {
                "blocked_pid": 4205,
                "blocked_user": "app_backend",
                "blocked_query": "UPDATE orders SET status = 'shipped' WHERE id = 98234",
                "blocking_pid": 4201,
                "blocking_user": "app_backend",
                "blocking_query": "SELECT o.*, u.email FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = 98234 FOR UPDATE",
            },
        ]

    async def get_long_transactions(self) -> list[dict]:
        return [
            {
                "pid": 4204,
                "usename": "etl_worker",
                "state": "idle in transaction",
                "query": "INSERT INTO audit_log SELECT * FROM staging_audit",
                "age_seconds": 1847,
            },
        ]

    async def get_autovacuum_status(self) -> dict:
        return {
            "running": [],
            "stale": [
                {
                    "relname": "audit_log",
                    "n_dead_tup": 892341,
                    "n_live_tup": 5400000,
                    "last_autovacuum": "2026-03-13T02:15:00",
                    "last_autoanalyze": "2026-03-13T02:16:00",
                },
                {
                    "relname": "orders",
                    "n_dead_tup": 245120,
                    "n_live_tup": 1200000,
                    "last_autovacuum": "2026-03-12T18:45:00",
                    "last_autoanalyze": "2026-03-12T18:46:00",
                },
            ],
        }

    async def get_table_access_patterns(self) -> list[dict]:
        return [
            {"relname": "orders", "seq_scan": 120, "idx_scan": 2850000, "seq_scan_ratio": 0.04},
            {"relname": "audit_log", "seq_scan": 8900, "idx_scan": 1200, "seq_scan_ratio": 0.88},
            {"relname": "events", "seq_scan": 4500, "idx_scan": 0, "seq_scan_ratio": 1.0},
        ]

    async def explain_query(self, sql: str) -> dict | None:
        return {
            "Node Type": "Sort",
            "Startup Cost": 1250.5,
            "Total Cost": 1350.8,
            "Plan Rows": 5000,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Startup Cost": 0.0,
                    "Total Cost": 1100.0,
                    "Plan Rows": 120000,
                    "Filter": "(created_at > (now() - '24:00:00'::interval))",
                }
            ],
        }

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

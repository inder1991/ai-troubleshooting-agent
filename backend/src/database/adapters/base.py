"""Abstract base class for all database engine adapters."""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel

from ..models import (
    ActiveQuery,
    ConnectionPoolSnapshot,
    PerfSnapshot,
    QueryResult,
    ReplicationSnapshot,
    SchemaSnapshot,
    TableDetail,
)


# Config allowlist — only these params can be altered
CONFIG_ALLOWLIST = {
    "shared_buffers", "work_mem", "maintenance_work_mem", "effective_cache_size",
    "max_connections", "max_worker_processes", "max_parallel_workers_per_gather",
    "random_page_cost", "effective_io_concurrency", "checkpoint_completion_target",
    "wal_buffers", "min_wal_size", "max_wal_size", "log_min_duration_statement",
    "statement_timeout", "idle_in_transaction_session_timeout",
}


class AdapterHealth(BaseModel):
    status: str  # "healthy", "degraded", "unreachable"
    latency_ms: float = 0.0
    version: str = ""
    error: Optional[str] = None


class DatabaseAdapter(ABC):
    """Abstract base for all database engine adapters.

    Key design principles (mirrors FirewallAdapter):
    - Snapshot accessors are cached with TTL; diagnostics read from cache.
    - execute_diagnostic_query is the only read that hits live DB.
    - execute_remediation (P2) is the only write path, requires approval.
    """

    DEFAULT_TTL = 300  # 5 minutes

    def __init__(
        self,
        engine: str,
        host: str,
        port: int,
        database: str,
        ttl: int = DEFAULT_TTL,
        connect_timeout: int = 10,
        query_timeout: int = 30,
    ):
        self.engine = engine
        self.host = host
        self.port = port
        self.database = database
        self._ttl = ttl
        self.connect_timeout = connect_timeout
        self.query_timeout = query_timeout
        self._connected = False

        # Snapshot caches
        self._perf_cache: Optional[PerfSnapshot] = None
        self._queries_cache: Optional[list[ActiveQuery]] = None
        self._repl_cache: Optional[ReplicationSnapshot] = None
        self._schema_cache: Optional[SchemaSnapshot] = None
        self._pool_cache: Optional[ConnectionPoolSnapshot] = None
        self._snapshot_time: float = 0

    def _cache_fresh(self) -> bool:
        return (time.time() - self._snapshot_time) < self._ttl

    def _invalidate_cache(self) -> None:
        self._perf_cache = None
        self._queries_cache = None
        self._repl_cache = None
        self._schema_cache = None
        self._pool_cache = None
        self._snapshot_time = 0

    # ── Lifecycle ──

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def health_check(self) -> AdapterHealth: ...

    @abstractmethod
    async def check_permissions(self) -> dict:
        """Check read permissions on diagnostic views. Returns {view_name: bool}."""
        ...

    @abstractmethod
    async def get_slow_queries_from_stats(self) -> list[dict]:
        """Return historically slow queries from pg_stat_statements or equivalent."""
        ...

    # ── Snapshot fetchers (vendor-specific, called on cache miss) ──

    @abstractmethod
    async def _fetch_performance_stats(self) -> PerfSnapshot: ...

    @abstractmethod
    async def _fetch_active_queries(self) -> list[ActiveQuery]: ...

    @abstractmethod
    async def _fetch_replication_status(self) -> ReplicationSnapshot: ...

    @abstractmethod
    async def _fetch_schema_snapshot(self) -> SchemaSnapshot: ...

    @abstractmethod
    async def _fetch_connection_pool(self) -> ConnectionPoolSnapshot: ...

    @abstractmethod
    async def get_table_detail(self, table_name: str) -> TableDetail: ...

    # ── Cached accessors ──

    async def get_performance_stats(self) -> PerfSnapshot:
        if not self._cache_fresh() or self._perf_cache is None:
            self._perf_cache = await self._fetch_performance_stats()
            self._snapshot_time = time.time()
        return self._perf_cache

    async def get_active_queries(self) -> list[ActiveQuery]:
        if not self._cache_fresh() or self._queries_cache is None:
            self._queries_cache = await self._fetch_active_queries()
            if not self._perf_cache:
                self._snapshot_time = time.time()
        return self._queries_cache

    async def get_replication_status(self) -> ReplicationSnapshot:
        if not self._cache_fresh() or self._repl_cache is None:
            self._repl_cache = await self._fetch_replication_status()
            if not self._perf_cache:
                self._snapshot_time = time.time()
        return self._repl_cache

    async def get_schema_snapshot(self) -> SchemaSnapshot:
        if not self._cache_fresh() or self._schema_cache is None:
            self._schema_cache = await self._fetch_schema_snapshot()
        return self._schema_cache

    async def get_connection_pool(self) -> ConnectionPoolSnapshot:
        if not self._cache_fresh() or self._pool_cache is None:
            self._pool_cache = await self._fetch_connection_pool()
        return self._pool_cache

    # ── Diagnostic accessors (non-abstract — safe defaults) ──

    async def get_wait_events(self) -> list[dict]:
        """Return current wait events from pg_stat_activity."""
        return []

    async def get_lock_chains(self) -> list[dict]:
        """Return blocking lock chains (who blocks whom)."""
        return []

    async def get_long_transactions(self) -> list[dict]:
        """Return transactions idle in transaction > 5 minutes."""
        return []

    async def get_autovacuum_status(self) -> dict:
        """Return running vacuums and stale tables needing vacuum."""
        return {"running": [], "stale": []}

    async def get_table_access_patterns(self) -> list[dict]:
        """Return sequential vs index scan ratios per table."""
        return []

    # ── EXPLAIN (read-only, no ANALYZE) ──

    async def explain_query(self, sql: str) -> dict | None:
        """Return the query plan for *sql* without executing it.

        Subclasses should override with engine-specific implementation.
        Default returns None (not supported).
        """
        return None

    # ── Live queries ──

    @abstractmethod
    async def execute_diagnostic_query(self, sql: str) -> QueryResult: ...

    async def refresh_snapshot(self) -> None:
        """Force-refresh all cached snapshots."""
        self._invalidate_cache()
        await asyncio.gather(
            self.get_performance_stats(),
            self.get_active_queries(),
            self.get_replication_status(),
            self.get_schema_snapshot(),
            self.get_connection_pool(),
        )

    # ── Write operations (P2) ──

    @abstractmethod
    async def kill_query(self, pid: int) -> dict:
        """Terminate a backend process by PID."""
        ...

    @abstractmethod
    async def vacuum_table(self, table: str, full: bool = False, analyze: bool = True) -> dict:
        """VACUUM [FULL] [ANALYZE] a table."""
        ...

    @abstractmethod
    async def reindex_table(self, table: str) -> dict:
        """REINDEX TABLE CONCURRENTLY."""
        ...

    @abstractmethod
    async def create_index(self, table: str, columns: list[str],
                           name: str | None = None, unique: bool = False) -> dict:
        """CREATE INDEX CONCURRENTLY."""
        ...

    @abstractmethod
    async def drop_index(self, index_name: str) -> dict:
        """DROP INDEX CONCURRENTLY."""
        ...

    async def alter_config(self, param: str, value: str) -> dict:
        """ALTER SYSTEM SET param = value. Validates against allowlist."""
        if param not in CONFIG_ALLOWLIST:
            raise ValueError(f"Parameter '{param}' not in allowlist")
        return await self._alter_config_impl(param, value)

    @abstractmethod
    async def _alter_config_impl(self, param: str, value: str) -> dict:
        """Vendor-specific config alter implementation."""
        ...

    @abstractmethod
    async def get_config_recommendations(self) -> list[dict]:
        """Return config tuning recommendations."""
        ...

    @abstractmethod
    async def generate_failover_runbook(self) -> dict:
        """Generate a failover runbook (read-only, no execution)."""
        ...

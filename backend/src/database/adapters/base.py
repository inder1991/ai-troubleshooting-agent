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
    ):
        self.engine = engine
        self.host = host
        self.port = port
        self.database = database
        self._ttl = ttl
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

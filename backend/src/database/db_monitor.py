"""DBMonitor — continuous polling service for database metrics."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class DBMonitor:
    """Polls all enabled DB profiles on a configurable interval."""

    def __init__(
        self,
        profile_store,
        adapter_registry,
        metrics_store,
        alert_engine,
        broadcast_callback: Optional[Callable[..., Coroutine]] = None,
        interval: int = 30,
    ):
        self.profile_store = profile_store
        self.adapter_registry = adapter_registry
        self.metrics_store = metrics_store
        self.alert_engine = alert_engine
        self._broadcast = broadcast_callback
        self.interval = interval

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._profile_statuses: dict[str, dict] = {}
        self._last_cycle_at: Optional[float] = None
        self._cycle_duration: float = 0.0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("DBMonitor started (interval=%ds)", self.interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DBMonitor stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._collect_cycle()
            except Exception as e:
                logger.error("DBMonitor cycle error: %s", e)
            await asyncio.sleep(self.interval)

    async def _collect_cycle(self) -> None:
        start = time.time()
        profiles = self.profile_store.list_all()

        for profile in profiles:
            pid = profile["id"]
            try:
                adapter = self.adapter_registry.get_by_profile(pid)
                if not adapter:
                    self._profile_statuses[pid] = {
                        "id": pid, "name": profile["name"],
                        "status": "not_connected", "last_collected_at": None,
                    }
                    continue

                if not adapter._connected:
                    await adapter.connect()

                await self._collect_profile_metrics(profile, adapter)

                self._profile_statuses[pid] = {
                    "id": pid, "name": profile["name"],
                    "status": "healthy", "last_collected_at": time.time(),
                }

                if self.alert_engine:
                    try:
                        await self.alert_engine.evaluate(f"db:{pid}")
                    except Exception as e:
                        logger.warning("Alert evaluation failed for %s: %s", pid, e)

            except Exception as e:
                logger.warning("DBMonitor collection failed for %s: %s", pid, e)
                self._profile_statuses[pid] = {
                    "id": pid, "name": profile.get("name", pid),
                    "status": "error", "error": str(e),
                    "last_collected_at": None,
                }

        self._last_cycle_at = time.time()
        self._cycle_duration = time.time() - start

        if self._broadcast:
            await self._broadcast({
                "type": "db_monitor_update",
                "data": self.get_snapshot(),
            })

    async def _collect_profile_metrics(self, profile: dict, adapter) -> None:
        pid = profile["id"]
        engine = profile.get("engine", "unknown")

        await adapter.refresh_snapshot()

        stats = await adapter.get_performance_stats()
        pool = await adapter.get_connection_pool()
        repl = await adapter.get_replication_status()
        queries = await adapter.get_active_queries()

        if not self.metrics_store:
            return

        utilization_pct = 0.0
        if pool.max_connections > 0:
            utilization_pct = (pool.active + pool.waiting) / pool.max_connections * 100

        slow_queries = [q for q in queries if q.duration_ms > 5000]
        max_duration = max((q.duration_ms for q in queries), default=0)
        avg_duration = (
            sum(q.duration_ms for q in queries) / len(queries) if queries else 0
        )

        metrics = {
            "cache_hit_ratio": stats.cache_hit_ratio,
            "transactions_per_sec": stats.transactions_per_sec,
            "deadlocks": float(stats.deadlocks),
            "uptime_seconds": float(stats.uptime_seconds),
            "conn_active": float(pool.active),
            "conn_idle": float(pool.idle),
            "conn_waiting": float(pool.waiting),
            "conn_max": float(pool.max_connections),
            "conn_utilization_pct": utilization_pct,
            "repl_lag_bytes": float(repl.replication_lag_bytes),
            "repl_lag_seconds": repl.replication_lag_seconds,
            "slow_query_count": float(len(slow_queries)),
            "max_query_duration_ms": max_duration,
            "avg_query_duration_ms": avg_duration,
            "total_active_queries": float(len(queries)),
        }

        await self.metrics_store.write_db_metrics_batch(pid, engine, metrics)

    def get_snapshot(self) -> dict:
        return {
            "running": self._running,
            "interval": self.interval,
            "last_cycle_at": self._last_cycle_at,
            "cycle_duration": self._cycle_duration,
            "profiles": list(self._profile_statuses.values()),
        }

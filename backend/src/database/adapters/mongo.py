"""MongoDB adapter using Motor (async pymongo)."""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    AsyncIOMotorClient = None  # type: ignore

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


class MongoAdapter(DatabaseAdapter):
    """MongoDB adapter using Motor for async connectivity."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        username: str = "",
        password: str = "",
        connection_uri: str = "",
        ttl: int = 300,
    ):
        super().__init__(
            engine="mongodb", host=host, port=port, database=database, ttl=ttl
        )
        self._username = username
        self._password = password
        self._connection_uri = connection_uri
        self._client: Optional[AsyncIOMotorClient] = None

    # ── Lifecycle ──

    async def connect(self) -> None:
        if AsyncIOMotorClient is None:
            raise RuntimeError("motor is not installed – pip install motor")

        if self._connection_uri:
            self._client = AsyncIOMotorClient(
                self._connection_uri,
                serverSelectionTimeoutMS=10000,
            )
        else:
            kwargs: dict = {
                "host": self.host,
                "port": self.port,
                "serverSelectionTimeoutMS": 10000,
            }
            if self._username:
                kwargs["username"] = self._username
            if self._password:
                kwargs["password"] = self._password
            self._client = AsyncIOMotorClient(**kwargs)

        # Force a round-trip to validate the connection
        await self._client.admin.command("ping")
        self._connected = True
        logger.info("Connected to MongoDB at %s:%s/%s", self.host, self.port, self.database)

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
        self._connected = False
        self._invalidate_cache()
        logger.info("Disconnected from MongoDB")

    async def health_check(self) -> AdapterHealth:
        if not self._connected or not self._client:
            return AdapterHealth(status="unreachable", error="Not connected")
        try:
            db = self._client[self.database]
            start = time.time()
            status = await db.command("serverStatus")
            latency = (time.time() - start) * 1000
            version = status.get("version", "")
            return AdapterHealth(
                status="healthy", latency_ms=round(latency, 2), version=version
            )
        except Exception as e:
            return AdapterHealth(status="degraded", error=str(e))

    # ── Snapshot fetchers ──

    async def _fetch_performance_stats(self) -> PerfSnapshot:
        db = self._client[self.database]
        status = await db.command("serverStatus")

        connections = status.get("connections", {})
        current = connections.get("current", 0)
        available = connections.get("available", 0)
        active = connections.get("active", current)

        # WiredTiger cache hit ratio
        wt = status.get("wiredTiger", {})
        cache = wt.get("cache", {})
        bytes_read = cache.get("bytes read into cache", 0)
        bytes_in_cache = cache.get("bytes currently in the cache", 0)
        if bytes_read + bytes_in_cache > 0:
            cache_hit_ratio = round(bytes_in_cache / (bytes_read + bytes_in_cache), 4)
        else:
            cache_hit_ratio = 0.0

        # Sum of opcounters for transactions_per_sec
        opcounters = status.get("opcounters", {})
        tps = sum(
            opcounters.get(op, 0)
            for op in ("insert", "query", "update", "delete", "getmore", "command")
        )

        uptime = status.get("uptime", 0)

        return PerfSnapshot(
            connections_active=active,
            connections_idle=current - active,
            connections_max=current + available,
            cache_hit_ratio=cache_hit_ratio,
            transactions_per_sec=float(tps),
            deadlocks=0,
            uptime_seconds=int(uptime),
        )

    async def _fetch_active_queries(self) -> list[ActiveQuery]:
        db = self._client[self.database]
        result = await db.command("currentOp")
        inprog = result.get("inprog", [])

        queries = []
        for op in inprog:
            opid = op.get("opid", 0)
            microsecs = op.get("microsecs_running", 0) or 0
            duration_ms = microsecs / 1000.0
            command = op.get("command", {})
            command_str = json.dumps(command, default=str)[:500] if command else ""
            state = op.get("op", "unknown")
            waiting = op.get("waitingForLock", False)
            ns = op.get("ns", "")

            queries.append(
                ActiveQuery(
                    pid=opid,
                    query=command_str,
                    duration_ms=round(duration_ms, 2),
                    state=state,
                    user=op.get("effectiveUsers", [{}])[0].get("user", "") if op.get("effectiveUsers") else "",
                    database=ns.split(".")[0] if ns else "",
                    waiting=waiting,
                )
            )

        # Sort by duration descending, limit to 50
        queries.sort(key=lambda q: q.duration_ms, reverse=True)
        return queries[:50]

    async def _fetch_connection_pool(self) -> ConnectionPoolSnapshot:
        db = self._client[self.database]
        status = await db.command("serverStatus")
        connections = status.get("connections", {})

        current = connections.get("current", 0)
        available = connections.get("available", 0)
        active = connections.get("active", 0)

        return ConnectionPoolSnapshot(
            active=active,
            idle=current - active,
            waiting=0,
            max_connections=current + available,
        )

    async def _fetch_replication_status(self) -> ReplicationSnapshot:
        db = self._client[self.database]
        try:
            rs_status = await db.command("replSetGetStatus")
        except Exception:
            # Standalone server — no replica set
            return ReplicationSnapshot(
                is_replica=False, replicas=[], replication_lag_bytes=0
            )

        my_state = rs_status.get("myState", 0)
        is_replica = my_state == 2  # SECONDARY

        members = rs_status.get("members", [])
        self_name = rs_status.get("set", "")

        # Find the PRIMARY's optime for lag calculation
        primary_optime = None
        my_optime = None
        replicas = []
        for member in members:
            state_str = member.get("stateStr", "")
            if state_str == "PRIMARY":
                primary_optime = member.get("optimeDate")
            if member.get("self", False):
                my_optime = member.get("optimeDate")
                continue  # Skip self from replica list
            replicas.append(
                ReplicaInfo(
                    name=member.get("name", ""),
                    state=state_str,
                    lag_bytes=0,
                    lag_seconds=float(member.get("lag", 0)),
                )
            )

        lag_seconds = 0.0
        if is_replica and primary_optime and my_optime:
            try:
                lag_seconds = (primary_optime - my_optime).total_seconds()
            except (TypeError, AttributeError):
                lag_seconds = 0.0

        return ReplicationSnapshot(
            is_replica=is_replica,
            replicas=replicas,
            replication_lag_bytes=0,
            replication_lag_seconds=lag_seconds,
        )

    async def _fetch_schema_snapshot(self) -> SchemaSnapshot:
        db = self._client[self.database]
        collection_names = await db.list_collection_names()

        tables = []
        all_indexes = []

        for coll_name in collection_names:
            try:
                stats = await db.command("collStats", coll_name)
                tables.append({
                    "name": coll_name,
                    "rows": stats.get("count", 0),
                    "size_bytes": stats.get("size", 0),
                    "storage_size": stats.get("storageSize", 0),
                    "avg_obj_size": stats.get("avgObjSize", 0),
                })

                # Collect indexes
                index_sizes = stats.get("indexSizes", {})
                for idx_name, idx_size in index_sizes.items():
                    all_indexes.append({
                        "name": idx_name,
                        "table": coll_name,
                        "size_bytes": idx_size,
                    })
            except Exception as e:
                logger.warning("Failed to get collStats for %s: %s", coll_name, e)

        # Total database size
        try:
            db_stats = await db.command("dbStats")
            total_size = db_stats.get("dataSize", 0) + db_stats.get("indexSize", 0)
        except Exception:
            total_size = 0

        return SchemaSnapshot(
            tables=tables,
            indexes=all_indexes,
            total_size_bytes=total_size,
        )

    async def get_table_detail(self, table_name: str) -> TableDetail:
        """Get detail for a MongoDB collection (table_name = collection name)."""
        if not self._client:
            raise RuntimeError("Not connected")

        db = self._client[self.database]

        try:
            stats = await db.command("collStats", table_name)
        except Exception as e:
            raise ValueError(f"Collection '{table_name}' not found or error: {e}")

        row_count = stats.get("count", 0)
        total_size = stats.get("size", 0) + stats.get("totalIndexSize", 0)

        # Get indexes
        indexes = []
        index_sizes = stats.get("indexSizes", {})
        async for idx in db[table_name].list_indexes():
            idx_name = idx.get("name", "")
            unique = idx.get("unique", False)
            keys = list(idx.get("key", {}).keys())
            size = index_sizes.get(idx_name, 0)
            indexes.append(
                IndexInfo(
                    name=idx_name,
                    columns=keys,
                    unique=unique,
                    size_bytes=size,
                )
            )

        # MongoDB is schemaless — just report _id
        columns = [
            ColumnInfo(name="_id", data_type="ObjectId", nullable=False, is_pk=True)
        ]

        return TableDetail(
            name=table_name,
            schema_name=self.database,
            columns=columns,
            indexes=indexes,
            row_estimate=row_count,
            total_size_bytes=total_size,
            bloat_ratio=0.0,
        )

    # ── Live queries ──

    async def execute_diagnostic_query(self, sql: str) -> QueryResult:
        """Execute a diagnostic query against MongoDB.

        Input can be JSON: {"collection": "name", "filter": {...}}
        or just a collection name to count documents.
        """
        db = self._client[self.database]
        try:
            # Try parsing as JSON
            try:
                parsed = json.loads(sql)
                collection = parsed.get("collection", "")
                filter_doc = parsed.get("filter", {})
            except (json.JSONDecodeError, TypeError):
                # Treat as collection name
                collection = sql.strip()
                filter_doc = {}

            if not collection:
                return QueryResult(query=sql, error="No collection specified")

            start = time.time()
            explain_result = await db.command(
                "explain",
                {"find": collection, "filter": filter_doc},
                verbosity="executionStats",
            )
            elapsed = (time.time() - start) * 1000

            # Extract execution stats
            exec_stats = (
                explain_result
                .get("queryPlanner", {})
                .get("winningPlan", {})
            )
            n_returned = (
                explain_result
                .get("executionStats", {})
                .get("nReturned", 0)
            )

            return QueryResult(
                query=sql,
                execution_time_ms=round(elapsed, 2),
                rows_returned=n_returned,
            )
        except Exception as e:
            return QueryResult(query=sql, error=str(e))

    # ── Write operations (P2) ──

    async def kill_query(self, pid: int) -> dict:
        """Kill a MongoDB operation by opid."""
        db = self._client[self.database]
        try:
            await db.command("killOp", op=pid)
            return {
                "success": True,
                "pid": pid,
                "message": f"Killed operation {pid}",
            }
        except Exception as e:
            return {
                "success": False,
                "pid": pid,
                "message": f"Failed to kill operation {pid}: {e}",
            }

    async def vacuum_table(self, table: str, full: bool = False, analyze: bool = True) -> dict:
        """VACUUM is not applicable to MongoDB. Use compact instead."""
        return {
            "success": False,
            "table": table,
            "message": "VACUUM is not applicable to MongoDB. Use db.collection.compact() via the shell.",
        }

    async def reindex_table(self, table: str) -> dict:
        """Reindex a MongoDB collection."""
        db = self._client[self.database]
        try:
            await db[table].reindex()
            return {
                "success": True,
                "table": table,
                "message": f"Reindexed collection {table}",
            }
        except Exception as e:
            return {
                "success": False,
                "table": table,
                "message": f"Failed to reindex {table}: {e}",
            }

    async def create_index(
        self,
        table: str,
        columns: list[str],
        name: str | None = None,
        unique: bool = False,
    ) -> dict:
        """Create an index on a MongoDB collection."""
        db = self._client[self.database]
        try:
            keys = [(col, 1) for col in columns]
            kwargs: dict = {}
            if name:
                kwargs["name"] = name
            if unique:
                kwargs["unique"] = True
            idx_name = await db[table].create_index(keys, **kwargs)
            return {
                "success": True,
                "index_name": idx_name,
                "table": table,
                "columns": columns,
            }
        except Exception as e:
            return {
                "success": False,
                "table": table,
                "message": f"Failed to create index: {e}",
            }

    async def drop_index(self, index_name: str) -> dict:
        """Drop a MongoDB index. Requires collection context."""
        return {
            "success": False,
            "index_name": index_name,
            "message": (
                "MongoDB requires a collection name to drop an index. "
                "Use db[collection].drop_index(index_name) via the shell."
            ),
        }

    async def _alter_config_impl(self, param: str, value: str) -> dict:
        """ALTER CONFIG is not directly supported for MongoDB via this adapter."""
        return {
            "success": False,
            "param": param,
            "value": value,
            "message": (
                "MongoDB configuration changes require setParameter command or "
                "editing mongod.conf. Not supported via this adapter."
            ),
        }

    async def get_config_recommendations(self) -> list[dict]:
        """MongoDB config recommendations — not implemented."""
        return []

    async def generate_failover_runbook(self) -> dict:
        """Generate a MongoDB replica set failover runbook."""
        repl = await self.get_replication_status()
        is_replica = repl.is_replica
        replicas = [r.model_dump() for r in repl.replicas]
        steps = []

        if is_replica:
            steps = [
                {
                    "order": 1,
                    "description": "This server is a SECONDARY. To trigger failover:",
                    "command": "rs.stepDown()",
                },
                {
                    "order": 2,
                    "description": "Verify election completed",
                    "command": "rs.status()",
                },
                {
                    "order": 3,
                    "description": "Update application connection strings",
                    "command": "-- Point apps to new primary or use replica set URI",
                },
            ]
        elif replicas:
            steps = [
                {
                    "order": 1,
                    "description": f"Verify replica set health ({len(replicas)} members)",
                    "command": "rs.status()",
                },
                {
                    "order": 2,
                    "description": "Check replication lag",
                    "command": "rs.printReplicationInfo()",
                },
                {
                    "order": 3,
                    "description": "Step down the current primary",
                    "command": "rs.stepDown()",
                },
                {
                    "order": 4,
                    "description": "Verify new primary elected",
                    "command": "rs.status()",
                },
                {
                    "order": 5,
                    "description": "Update connection strings if not using replica set URI",
                    "command": "-- Update application config",
                },
            ]
        else:
            steps = [
                {
                    "order": 1,
                    "description": "No replica set configured",
                    "command": "-- Initialize with rs.initiate()",
                },
            ]

        return {
            "is_replica": is_replica,
            "replica_count": len(replicas),
            "replicas": replicas,
            "steps": steps,
            "warnings": [
                "rs.stepDown() triggers an election — brief write unavailability",
                "Ensure all secondaries are caught up before stepping down",
            ],
            "estimated_downtime": "10-30 seconds (election time)",
        }

    async def check_permissions(self) -> dict:
        """Check diagnostic read permissions on MongoDB.

        Returns a dict of {view_name: bool} indicating whether the connected
        user can read key diagnostic collections/commands.
        """
        results: dict[str, bool] = {}
        db_name = self._database
        try:
            db = self._client[db_name]
            # Verify serverStatus is readable (requires clusterMonitor or root)
            await db.command("serverStatus")
            results["serverStatus"] = True
        except Exception:
            results["serverStatus"] = False
        try:
            db = self._client[db_name]
            # Verify currentOp is readable
            await db.command("currentOp")
            results["currentOp"] = True
        except Exception:
            results["currentOp"] = False
        try:
            db = self._client[db_name]
            # Verify replSetGetStatus
            await self._client.admin.command("replSetGetStatus")
            results["replSetGetStatus"] = True
        except Exception:
            results["replSetGetStatus"] = False
        return results

    async def get_slow_queries_from_stats(self) -> list[dict]:
        """Return historically slow operations from the MongoDB system.profile collection.

        Requires profiling to be enabled (db.setProfilingLevel(1, {slowms: 100})).
        Returns an empty list if profiling is not enabled or no slow ops are found.
        """
        slow: list[dict] = []
        try:
            db = self._client[self._database]
            cursor = db["system.profile"].find(
                {"millis": {"$gt": 100}},
                {"op": 1, "ns": 1, "millis": 1, "ts": 1, "command": 1},
            ).sort("millis", -1).limit(20)
            async for doc in cursor:
                slow.append({
                    "operation": doc.get("op", "unknown"),
                    "namespace": doc.get("ns", ""),
                    "duration_ms": doc.get("millis", 0),
                    "timestamp": str(doc.get("ts", "")),
                    "query": str(doc.get("command", {}))[:200],
                })
        except Exception:
            pass
        return slow

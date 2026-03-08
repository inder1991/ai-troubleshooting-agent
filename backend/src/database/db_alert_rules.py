"""Default alert rules for database monitoring."""
from __future__ import annotations

from src.network.alert_engine import AlertRule

DEFAULT_DB_ALERT_RULES: list[AlertRule] = [
    AlertRule(
        id="db-conn-pool-warning", name="DB Connection Pool Saturation",
        severity="warning", entity_type="database", entity_filter="*",
        metric="conn_utilization_pct", condition="gt", threshold=80.0,
        duration_seconds=60, cooldown_seconds=300,
        description="Connection pool usage above 80%",
    ),
    AlertRule(
        id="db-conn-pool-critical", name="DB Connection Pool Critical",
        severity="critical", entity_type="database", entity_filter="*",
        metric="conn_utilization_pct", condition="gt", threshold=95.0,
        duration_seconds=30, cooldown_seconds=300,
        description="Connection pool usage above 95%",
    ),
    AlertRule(
        id="db-cache-hit-low", name="DB Low Cache Hit Ratio",
        severity="warning", entity_type="database", entity_filter="*",
        metric="cache_hit_ratio", condition="lt", threshold=0.9,
        duration_seconds=120, cooldown_seconds=600,
        description="Cache hit ratio below 90%",
    ),
    AlertRule(
        id="db-repl-lag-warning", name="DB Replication Lag Warning",
        severity="warning", entity_type="database", entity_filter="*",
        metric="repl_lag_bytes", condition="gt", threshold=10_000_000.0,
        duration_seconds=60, cooldown_seconds=300,
        description="Replication lag above 10 MB",
    ),
    AlertRule(
        id="db-repl-lag-critical", name="DB Replication Lag Critical",
        severity="critical", entity_type="database", entity_filter="*",
        metric="repl_lag_bytes", condition="gt", threshold=100_000_000.0,
        duration_seconds=30, cooldown_seconds=300,
        description="Replication lag above 100 MB",
    ),
    AlertRule(
        id="db-deadlocks", name="DB Deadlocks Detected",
        severity="warning", entity_type="database", entity_filter="*",
        metric="deadlocks", condition="gt", threshold=0.0,
        duration_seconds=30, cooldown_seconds=600,
        description="Deadlocks detected since last snapshot",
    ),
    AlertRule(
        id="db-slow-queries", name="DB Slow Query Spike",
        severity="warning", entity_type="database", entity_filter="*",
        metric="slow_query_count", condition="gt", threshold=5.0,
        duration_seconds=60, cooldown_seconds=300,
        description="More than 5 slow queries (>5s) active",
    ),
]

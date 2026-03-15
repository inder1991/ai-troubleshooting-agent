"""Alert threshold engine — evaluates rules against SQLite-collected metrics.

This is the lightweight alert engine that works with SQLiteMetricsStore
(as opposed to the InfluxDB-based AlertEngine in alert_engine.py).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_ALERT_RULES = [
    {"id": "cpu_high", "metric": "cpu_pct", "operator": ">", "threshold": 80, "severity": "warning", "message": "CPU utilization above 80%"},
    {"id": "cpu_critical", "metric": "cpu_pct", "operator": ">", "threshold": 95, "severity": "critical", "message": "CPU utilization critical (>95%)"},
    {"id": "memory_high", "metric": "memory_pct", "operator": ">", "threshold": 85, "severity": "warning", "message": "Memory utilization above 85%"},
    {"id": "memory_critical", "metric": "memory_pct", "operator": ">", "threshold": 95, "severity": "critical", "message": "Memory utilization critical (>95%)"},
    {"id": "session_high", "metric": "session_utilization_pct", "operator": ">", "threshold": 80, "severity": "warning", "message": "Firewall session table above 80%"},
    {"id": "packet_buffer", "metric": "packet_buffer_pct", "operator": ">", "threshold": 70, "severity": "warning", "message": "Packet buffer utilization above 70%"},
    {"id": "pool_member_down", "metric": "pool_*_members_up", "operator": "<", "threshold": 1, "severity": "critical", "message": "Load balancer pool has no healthy members"},
    {"id": "cert_expiry_warn", "metric": "cert_*_days_left", "operator": "<", "threshold": 14, "severity": "warning", "message": "SSL certificate expiring within 14 days"},
    {"id": "cert_expiry_crit", "metric": "cert_*_days_left", "operator": "<", "threshold": 7, "severity": "critical", "message": "SSL certificate expiring within 7 days"},
    {"id": "ha_desync", "metric": "ha_sync_status", "operator": "==", "threshold": 0, "severity": "critical", "message": "HA pair out of sync"},
    {"id": "bgp_down", "metric": "bgp_peer_*_state", "operator": "==", "threshold": 0, "severity": "critical", "message": "BGP peer session down"},
    {"id": "tunnel_down", "metric": "tunnel_*_up", "operator": "==", "threshold": 0, "severity": "critical", "message": "GRE/VPN tunnel down"},
    {"id": "ping_loss", "metric": "packet_loss_pct", "operator": ">", "threshold": 5, "severity": "warning", "message": "Packet loss above 5%"},
    {"id": "clusterxl_desync", "metric": "clusterxl_sync_pct", "operator": "<", "threshold": 95, "severity": "warning", "message": "Checkpoint ClusterXL sync below 95%"},
]


class SQLiteAlertEngine:
    """Evaluates threshold rules against collected metrics and generates alerts."""

    def __init__(self, metrics_store, rules: list[dict] | None = None):
        self.store = metrics_store
        self.rules = rules or list(DEFAULT_ALERT_RULES)
        self._running = False
        self._devices: list[dict] = []
        # Track already-fired alerts to avoid duplicates
        self._fired: dict[str, float] = {}  # "device_id:rule_id" -> last_fired_ts
        self._cooldown_seconds = 300  # Don't re-fire same alert within 5 min

    def set_devices(self, devices: list[dict]) -> None:
        self._devices = devices

    def _evaluate_condition(self, value: float | None, operator: str, threshold: float) -> bool:
        if value is None:
            return False
        if operator == ">": return value > threshold
        if operator == "<": return value < threshold
        if operator == ">=": return value >= threshold
        if operator == "<=": return value <= threshold
        if operator == "==": return value == threshold
        if operator == "!=": return value != threshold
        return False

    def _is_wildcard_rule(self, metric: str) -> bool:
        return "*" in metric

    def _get_matching_metrics(self, device_id: str, metric_pattern: str) -> list[tuple[str, float]]:
        """For wildcard rules like 'bgp_peer_*_state', find all matching metrics."""
        if not self._is_wildcard_rule(metric_pattern):
            val = self.store.get_latest_device_metric(device_id, metric_pattern)
            return [(metric_pattern, val)] if val is not None else []

        conn = self.store._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT metric_name FROM device_metrics WHERE device_id=? AND metric_name LIKE ? ORDER BY timestamp DESC",
            (device_id, metric_pattern.replace("*", "%"))
        ).fetchall()

        results = []
        for (metric_name,) in rows:
            val = self.store.get_latest_device_metric(device_id, metric_name)
            if val is not None:
                results.append((metric_name, val))
        return results

    async def evaluate(self) -> int:
        """Evaluate all rules against all devices. Returns number of new alerts."""
        new_alerts = 0
        now = time.time()

        for device in self._devices:
            device_id = device.get("id", "")
            for rule in self.rules:
                metrics = self._get_matching_metrics(device_id, rule["metric"])
                for metric_name, value in metrics:
                    if self._evaluate_condition(value, rule["operator"], rule["threshold"]):
                        fire_key = f"{device_id}:{rule['id']}:{metric_name}"
                        last_fired = self._fired.get(fire_key, 0)
                        if now - last_fired < self._cooldown_seconds:
                            continue

                        message = f"{rule['message']} — {metric_name}={value:.1f} (threshold: {rule['operator']}{rule['threshold']})"
                        self.store.write_alert(
                            device_id=device_id,
                            rule_id=rule["id"],
                            severity=rule["severity"],
                            metric_name=metric_name,
                            value=value,
                            threshold=rule["threshold"],
                            message=message,
                        )
                        self._fired[fire_key] = now
                        new_alerts += 1
                        logger.info("Alert fired: %s on %s (%s)", rule["id"], device_id, message)

        return new_alerts

    async def start(self, interval: int = 30) -> None:
        """Evaluate rules periodically."""
        self._running = True
        logger.info("SQLite alert engine started (interval: %ds, rules: %d)", interval, len(self.rules))
        while self._running:
            new = await self.evaluate()
            if new > 0:
                logger.info("Alert evaluation: %d new alerts", new)
            await asyncio.sleep(interval)

    def stop(self) -> None:
        self._running = False

    def add_rule(self, rule: dict) -> None:
        self.rules.append(rule)

    def remove_rule(self, rule_id: str) -> None:
        self.rules = [r for r in self.rules if r["id"] != rule_id]

    def get_rules(self) -> list[dict]:
        return list(self.rules)

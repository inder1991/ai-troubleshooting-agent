"""Threshold-based alert engine evaluating metrics from InfluxDB."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AlertState(str, Enum):
    PENDING = "pending"
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass
class AlertRule:
    id: str
    name: str
    severity: str  # critical, warning, info
    entity_type: str  # device, link, interface
    entity_filter: str  # "*" or specific device_id
    metric: str
    condition: str  # gt, lt, eq, absent
    threshold: float
    duration_seconds: int = 300
    cooldown_seconds: int = 600
    enabled: bool = True
    description: str = ""


DEFAULT_RULES = [
    AlertRule(
        id="default-unreachable", name="Device Unreachable",
        severity="critical", entity_type="device", entity_filter="*",
        metric="packet_loss", condition="gt", threshold=0.99,
        duration_seconds=90, cooldown_seconds=300,
    ),
    AlertRule(
        id="default-cpu", name="High CPU",
        severity="warning", entity_type="device", entity_filter="*",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=300, cooldown_seconds=600,
    ),
    AlertRule(
        id="default-mem", name="High Memory",
        severity="warning", entity_type="device", entity_filter="*",
        metric="mem_pct", condition="gt", threshold=95.0,
        duration_seconds=300, cooldown_seconds=600,
    ),
    AlertRule(
        id="default-errors", name="Interface Errors",
        severity="warning", entity_type="device", entity_filter="*",
        metric="error_rate", condition="gt", threshold=0.01,
        duration_seconds=300, cooldown_seconds=600,
    ),
    AlertRule(
        id="default-saturation", name="Link Saturation",
        severity="warning", entity_type="device", entity_filter="*",
        metric="utilization", condition="gt", threshold=0.85,
        duration_seconds=600, cooldown_seconds=900,
    ),
    AlertRule(
        id="default-latency", name="Latency Spike",
        severity="warning", entity_type="device", entity_filter="*",
        metric="latency_ms", condition="gt", threshold=200.0,
        duration_seconds=120, cooldown_seconds=300,
    ),
]


class AlertEngine:
    """Evaluates alert rules against InfluxDB metrics."""

    def __init__(self, metrics_store: Any, load_defaults: bool = False) -> None:
        self.metrics = metrics_store
        self.rules: list[AlertRule] = []
        self._states: dict[str, AlertState] = {}  # (rule_id, entity_id) -> state
        self._last_fired: dict[str, float] = {}  # (rule_id, entity_id) -> timestamp
        self._active_alerts: dict[str, dict] = {}
        self._dispatcher = None

        if load_defaults:
            for r in DEFAULT_RULES:
                self.add_rule(r)

    def set_dispatcher(self, dispatcher) -> None:
        """Attach a NotificationDispatcher to receive fired alerts."""
        self._dispatcher = dispatcher

    def add_rule(self, rule: AlertRule) -> None:
        self.rules.append(rule)

    def remove_rule(self, rule_id: str) -> None:
        self.rules = [r for r in self.rules if r.id != rule_id]

    def get_rules(self) -> list[dict]:
        return [
            {
                "id": r.id, "name": r.name, "severity": r.severity,
                "entity_type": r.entity_type, "entity_filter": r.entity_filter,
                "metric": r.metric, "condition": r.condition,
                "threshold": r.threshold, "duration_seconds": r.duration_seconds,
                "cooldown_seconds": r.cooldown_seconds, "enabled": r.enabled,
                "description": r.description,
            }
            for r in self.rules
        ]

    def get_active_alerts(self) -> list[dict]:
        return list(self._active_alerts.values())

    def acknowledge(self, alert_key: str) -> bool:
        if alert_key in self._active_alerts:
            self._active_alerts[alert_key]["acknowledged"] = True
            return True
        return False

    def _matches_filter(self, entity_id: str, entity_filter: str) -> bool:
        if entity_filter == "*":
            return True
        return entity_id == entity_filter

    def _check_condition(self, value: float, condition: str, threshold: float) -> bool:
        if condition == "gt":
            return value > threshold
        elif condition == "lt":
            return value < threshold
        elif condition == "eq":
            return abs(value - threshold) < 0.001
        return False

    async def evaluate(self, entity_id: str) -> list[dict]:
        """Evaluate all rules for a given entity. Returns list of newly fired alerts."""
        fired: list[dict] = []
        now = time.time()

        for rule in self.rules:
            if not rule.enabled:
                continue
            if not self._matches_filter(entity_id, rule.entity_filter):
                continue

            key = f"{rule.id}:{entity_id}"

            # Check cooldown
            last = self._last_fired.get(key, 0)
            if now - last < rule.cooldown_seconds and key in self._active_alerts:
                continue

            # Query latest metric value
            data = await self.metrics.query_device_metrics(
                entity_id, rule.metric,
                range_str=f"{max(rule.duration_seconds, 30)}s",
                resolution="30s",
            )

            if not data:
                if rule.condition == "absent":
                    alert = self._fire_alert(rule, entity_id, 0, now)
                    fired.append(alert)
                continue

            latest_value = data[-1].get("value", 0)

            if self._check_condition(latest_value, rule.condition, rule.threshold):
                alert = self._fire_alert(rule, entity_id, latest_value, now)
                fired.append(alert)
            else:
                # Resolve if was firing
                if key in self._active_alerts:
                    del self._active_alerts[key]

        return fired

    def _fire_alert(
        self, rule: AlertRule, entity_id: str, value: float, now: float
    ) -> dict:
        key = f"{rule.id}:{entity_id}"
        self._last_fired[key] = now
        alert = {
            "key": key,
            "rule_id": rule.id,
            "rule_name": rule.name,
            "entity_id": entity_id,
            "severity": rule.severity,
            "metric": rule.metric,
            "value": value,
            "threshold": rule.threshold,
            "condition": rule.condition,
            "fired_at": now,
            "acknowledged": False,
            "message": f"{rule.name}: {rule.metric}={value:.1f} (threshold: {rule.condition} {rule.threshold})",
        }
        self._active_alerts[key] = alert
        return alert

    async def evaluate_all(self, entity_ids: list[str]) -> list[dict]:
        """Evaluate all rules for all entities."""
        all_fired = []
        for eid in entity_ids:
            fired = await self.evaluate(eid)
            all_fired.extend(fired)
            for alert in fired:
                await self.metrics.write_alert_event(
                    device_id=eid, rule_id=alert["rule_id"],
                    severity=alert["severity"], value=alert["value"],
                    threshold=alert["threshold"], message=alert["message"],
                )
        # Dispatch notifications for newly fired alerts
        if self._dispatcher and all_fired:
            try:
                await self._dispatcher.dispatch_batch(all_fired)
            except Exception:
                logger.exception("Notification dispatch failed")
        return all_fired

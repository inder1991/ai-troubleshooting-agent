"""Temporal analyzer: compute issue age, recency, restart velocity, worsening detection."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Any

from src.agents.cluster.state import NormalizedSignal
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_timestamp(ts: str) -> datetime | None:
    """Parse ISO timestamp string."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError) as e:
        logger.warning("Failed to parse timestamp '%s': %s", ts, e)
        return None


def _seconds_since(ts: str) -> int:
    """Seconds elapsed since a timestamp. Returns -1 for unparseable timestamps."""
    dt = _parse_timestamp(ts)
    if not dt:
        return -1
    return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))


def compute_temporal_attributes(
    signals: list[dict],
    domain_reports: list[dict],
) -> dict:
    """Compute temporal metadata for each signal and resource.

    Returns dict with:
      - signal_temporals: {signal_id: {event_age_seconds, resource_age_seconds, ...}}
      - resource_temporals: {resource_key: {first_seen, last_seen, restart_velocity, ...}}
    """
    now = datetime.now(timezone.utc)
    signal_temporals: dict[str, dict] = {}
    resource_temporals: dict[str, dict] = {}

    # Build event timeline from domain reports
    event_timestamps: dict[str, list[datetime]] = {}  # resource_key -> sorted timestamps

    for report in domain_reports:
        if report.get("status") in ("SKIPPED", "FAILED"):
            continue
        for anomaly in report.get("anomalies", []):
            ref = anomaly.get("evidence_ref", "")
            if not ref:
                continue
            # Use current time as proxy (real implementation would parse K8s event timestamps)
            if ref not in event_timestamps:
                event_timestamps[ref] = []
            event_timestamps[ref].append(now)

    # Process each signal
    for sig_dict in signals:
        sig = NormalizedSignal(**sig_dict) if isinstance(sig_dict, dict) else sig_dict
        sig_id = sig.signal_id
        res_key = sig.resource_key

        ts = _parse_timestamp(sig.timestamp)
        event_age = _seconds_since(sig.timestamp) if sig.timestamp else -1
        if event_age < 0:
            event_age = 3600  # Default 1 hour — safe middle ground
            logger.debug("Using default age for %s", res_key)

        signal_temporals[sig_id] = {
            "event_age_seconds": event_age,
            "resource_age_seconds": event_age,  # Approximation without K8s creationTimestamp
        }

        # Build resource temporal data
        if res_key not in resource_temporals:
            resource_temporals[res_key] = {
                "first_seen": sig.timestamp,
                "last_seen": sig.timestamp,
                "event_count_recent": 0,    # Events in last 5 min
                "event_count_baseline": 0,  # Events in last 60 min
                "restart_velocity": 0.0,
                "resource_age_seconds": event_age,
                "flap_count": 0,
            }

        rt = resource_temporals[res_key]

        # Update first/last seen
        if sig.timestamp:
            if not rt["first_seen"] or sig.timestamp < rt["first_seen"]:
                rt["first_seen"] = sig.timestamp
            if not rt["last_seen"] or sig.timestamp > rt["last_seen"]:
                rt["last_seen"] = sig.timestamp

        # Event window analysis
        events = event_timestamps.get(res_key, [])
        five_min_ago = now - timedelta(minutes=5)
        sixty_min_ago = now - timedelta(minutes=60)
        rt["event_count_recent"] = max(1, sum(1 for e in events if e >= five_min_ago))
        rt["event_count_baseline"] = max(1, sum(1 for e in events if e >= sixty_min_ago))

        # Restart velocity (from raw_value if HIGH_RESTART_COUNT signal)
        if sig.signal_type == "HIGH_RESTART_COUNT" and isinstance(sig.raw_value, (int, float)):
            # Estimate velocity: restarts / resource_age_minutes
            age_minutes = max(1, event_age / 60)
            rt["restart_velocity"] = round(float(sig.raw_value) / age_minutes, 2)

    logger.info("Computed temporal attributes for %d signals, %d resources",
                len(signal_temporals), len(resource_temporals))

    return {
        "signal_temporals": signal_temporals,
        "resource_temporals": resource_temporals,
    }


def detect_worsening(resource_temporal: dict, thresholds: dict | None = None) -> bool:
    """Detect if a resource's condition is worsening."""
    multiplier = (thresholds or {}).get("worsening_rate_multiplier", 3.0)

    recent = resource_temporal.get("event_count_recent", 0)
    baseline = resource_temporal.get("event_count_baseline", 0)

    # Event rate spike: recent rate > Nx the baseline rate
    baseline_rate = max(1, baseline) / 60  # per minute
    recent_rate = max(0, recent) / 5       # per minute
    if recent_rate > multiplier * baseline_rate:
        return True

    # Restart velocity acceleration
    velocity = resource_temporal.get("restart_velocity", 0.0)
    event_age = resource_temporal.get("resource_age_seconds", 0)
    if velocity > 0.5 and event_age < 300:
        return True

    return False


def detect_flapping(resource_temporal: dict, thresholds: dict | None = None) -> int:
    """Detect flapping — returns estimated flap count.

    Without stored history, we estimate from event pattern density.
    High event count with low severity suggests flapping.
    """
    threshold = (thresholds or {}).get("flap_count_threshold", 3)
    recent = resource_temporal.get("event_count_recent", 0)
    baseline = resource_temporal.get("event_count_baseline", 0)

    # If many events but velocity is low, likely flapping
    if baseline > 10 and resource_temporal.get("restart_velocity", 0) < 0.1:
        return min(baseline // 3, 10)  # Estimate flap count

    return 0


@traced_node(timeout_seconds=3)
async def temporal_analyzer(state: dict, config: dict) -> dict:
    """Compute issue age, recency, restart velocity. Deterministic, zero LLM cost."""
    signals = state.get("normalized_signals", [])
    reports = state.get("domain_reports", [])

    temporal_data = compute_temporal_attributes(signals, reports)

    return {"temporal_analysis": temporal_data}

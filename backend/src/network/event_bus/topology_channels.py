"""Topology-specific event channels, schema, and factory functions.

Defines a standard envelope (TopologyEvent) for all topology mutations so
that subscribers receive a uniform payload regardless of the entity kind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict
from uuid import uuid4

# ── Channel Constants ─────────────────────────────────────────────────

DEVICE_CHANGED = "topology.device.changed"
INTERFACE_CHANGED = "topology.interface.changed"
LINK_DISCOVERED = "topology.link.discovered"
ROUTE_CHANGED = "topology.route.changed"
POLICY_CHANGED = "topology.policy.changed"
STALE_DETECTED = "topology.stale.detected"

TOPOLOGY_CHANNELS = [
    DEVICE_CHANGED,
    INTERFACE_CHANGED,
    LINK_DISCOVERED,
    ROUTE_CHANGED,
    POLICY_CHANGED,
    STALE_DETECTED,
]

# ── Event Type Constants ──────────────────────────────────────────────


class EventType:
    """Plain string constants for topology event types."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STALE = "stale"


# ── Schema Version ────────────────────────────────────────────────────

SCHEMA_VERSION = 1

# ── Topology Event Dataclass ──────────────────────────────────────────


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    return str(uuid4())


@dataclass
class TopologyEvent:
    """Canonical envelope for all topology mutation events."""

    event_type: str
    entity_type: str  # device / interface / link / route / policy
    entity_id: str
    source: str
    data: Dict = field(default_factory=dict)
    changes: Dict = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    event_id: str = field(default_factory=_new_uuid)
    timestamp: str = field(default_factory=_utcnow_iso)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "source": self.source,
            "data": self.data,
            "changes": self.changes,
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TopologyEvent:
        return cls(
            event_type=d["event_type"],
            entity_type=d["entity_type"],
            entity_id=d["entity_id"],
            source=d["source"],
            data=d.get("data", {}),
            changes=d.get("changes", {}),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            event_id=d.get("event_id", _new_uuid()),
            timestamp=d.get("timestamp", _utcnow_iso()),
        )


# ── Factory Functions ─────────────────────────────────────────────────


def make_device_event(
    device_id: str,
    event_type: str,
    source: str,
    data: dict | None = None,
    changes: dict | None = None,
) -> TopologyEvent:
    return TopologyEvent(
        event_type=event_type,
        entity_type="device",
        entity_id=device_id,
        source=source,
        data=data or {},
        changes=changes or {},
    )


def make_interface_event(
    interface_id: str,
    event_type: str,
    source: str,
    data: dict | None = None,
    changes: dict | None = None,
) -> TopologyEvent:
    return TopologyEvent(
        event_type=event_type,
        entity_type="interface",
        entity_id=interface_id,
        source=source,
        data=data or {},
        changes=changes or {},
    )


def make_link_event(
    link_id: str,
    event_type: str,
    source: str,
    data: dict | None = None,
    changes: dict | None = None,
) -> TopologyEvent:
    return TopologyEvent(
        event_type=event_type,
        entity_type="link",
        entity_id=link_id,
        source=source,
        data=data or {},
        changes=changes or {},
    )


def make_route_event(
    route_id: str,
    event_type: str,
    source: str,
    data: dict | None = None,
    changes: dict | None = None,
) -> TopologyEvent:
    return TopologyEvent(
        event_type=event_type,
        entity_type="route",
        entity_id=route_id,
        source=source,
        data=data or {},
        changes=changes or {},
    )


def make_stale_event(
    entity_type: str,
    entity_id: str,
    last_seen: str = "",
) -> TopologyEvent:
    return TopologyEvent(
        event_type=EventType.STALE,
        entity_type=entity_type,
        entity_id=entity_id,
        source="staleness_checker",
        data={"last_seen": last_seen} if last_seen else {},
    )

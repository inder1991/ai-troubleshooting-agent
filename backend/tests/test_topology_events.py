"""Tests for topology event channels, schema, and factory functions."""

import pytest

from src.network.event_bus.topology_channels import (
    DEVICE_CHANGED,
    INTERFACE_CHANGED,
    LINK_DISCOVERED,
    ROUTE_CHANGED,
    POLICY_CHANGED,
    STALE_DETECTED,
    TOPOLOGY_CHANNELS,
    EventType,
    SCHEMA_VERSION,
    TopologyEvent,
    make_device_event,
    make_interface_event,
    make_link_event,
    make_route_event,
    make_stale_event,
)


def test_all_channels_defined():
    expected = [
        DEVICE_CHANGED,
        INTERFACE_CHANGED,
        LINK_DISCOVERED,
        ROUTE_CHANGED,
        POLICY_CHANGED,
        STALE_DETECTED,
    ]
    assert len(TOPOLOGY_CHANNELS) == 6
    for ch in expected:
        assert ch in TOPOLOGY_CHANNELS


def test_event_types():
    assert EventType.CREATED == "created"
    assert EventType.UPDATED == "updated"
    assert EventType.DELETED == "deleted"
    assert EventType.STALE == "stale"


def test_create_event():
    evt = TopologyEvent(
        event_type=EventType.CREATED,
        entity_type="device",
        entity_id="sw-core-01",
        source="snmp_collector",
        data={"hostname": "sw-core-01"},
        changes={"added": True},
    )
    assert evt.event_type == "created"
    assert evt.entity_type == "device"
    assert evt.entity_id == "sw-core-01"
    assert evt.source == "snmp_collector"
    assert evt.data == {"hostname": "sw-core-01"}
    assert evt.changes == {"added": True}
    assert evt.schema_version == SCHEMA_VERSION


def test_to_dict():
    evt = TopologyEvent(
        event_type=EventType.UPDATED,
        entity_type="interface",
        entity_id="eth0",
        source="poller",
    )
    d = evt.to_dict()
    assert isinstance(d, dict)
    assert d["event_type"] == "updated"
    assert d["entity_type"] == "interface"
    assert d["entity_id"] == "eth0"
    assert d["source"] == "poller"
    assert d["schema_version"] == SCHEMA_VERSION
    assert "event_id" in d
    assert "timestamp" in d


def test_from_dict():
    evt = TopologyEvent(
        event_type=EventType.DELETED,
        entity_type="link",
        entity_id="link-42",
        source="lldp",
        data={"speed": 1000},
    )
    d = evt.to_dict()
    restored = TopologyEvent.from_dict(d)
    assert restored.event_type == evt.event_type
    assert restored.entity_type == evt.entity_type
    assert restored.entity_id == evt.entity_id
    assert restored.source == evt.source
    assert restored.data == evt.data
    assert restored.event_id == evt.event_id
    assert restored.timestamp == evt.timestamp


def test_make_device_event():
    evt = make_device_event("sw-01", EventType.CREATED, "discovery", data={"os": "ios"})
    assert evt.entity_type == "device"
    assert evt.entity_id == "sw-01"
    assert evt.event_type == "created"
    assert evt.data == {"os": "ios"}


def test_make_link_event():
    evt = make_link_event("link-99", EventType.UPDATED, "lldp", changes={"bandwidth": 10000})
    assert evt.entity_type == "link"
    assert evt.entity_id == "link-99"
    assert evt.event_type == "updated"
    assert evt.changes == {"bandwidth": 10000}


def test_event_has_uuid():
    evt = TopologyEvent(
        event_type=EventType.CREATED,
        entity_type="device",
        entity_id="r1",
        source="test",
    )
    assert evt.event_id is not None
    assert len(evt.event_id) > 0


def test_event_has_timestamp():
    evt = TopologyEvent(
        event_type=EventType.CREATED,
        entity_type="device",
        entity_id="r1",
        source="test",
    )
    assert evt.timestamp is not None
    assert len(evt.timestamp) > 0

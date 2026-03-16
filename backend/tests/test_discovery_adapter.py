"""Tests for DiscoveryAdapter interface and DiscoveryObservation model."""

import pytest
from src.network.discovery.observation import ObservationType, DiscoveryObservation
from src.network.discovery.adapter import DiscoveryAdapter


EXPECTED_TYPES = [
    "DEVICE", "INTERFACE", "NEIGHBOR", "ROUTE", "BGP_PEER",
    "OSPF_NEIGHBOR", "ARP_ENTRY", "MAC_ENTRY", "LAG_MEMBER",
    "VPC", "SUBNET", "SECURITY_GROUP", "CLOUD_INTERFACE",
    "ROUTE_TABLE", "LOAD_BALANCER",
]


def test_all_types_defined():
    """All 15 ObservationType values exist."""
    for name in EXPECTED_TYPES:
        assert hasattr(ObservationType, name), f"Missing ObservationType.{name}"
    assert len(ObservationType) == 15


def test_create_observation():
    """Create an observation with all fields and verify them."""
    obs = DiscoveryObservation(
        observation_type=ObservationType.DEVICE,
        source="snmp",
        device_id="router-1",
        data={"hostname": "core-rtr"},
        confidence=0.9,
        observed_at="2026-03-16T00:00:00Z",
    )
    assert obs.observation_type == ObservationType.DEVICE
    assert obs.source == "snmp"
    assert obs.device_id == "router-1"
    assert obs.data == {"hostname": "core-rtr"}
    assert obs.confidence == 0.9
    assert obs.observed_at == "2026-03-16T00:00:00Z"


def test_to_dict():
    """to_dict serializes observation_type as its string value."""
    obs = DiscoveryObservation(
        observation_type=ObservationType.BGP_PEER,
        source="bgp",
        device_id="edge-1",
        data={"peer_as": 65001},
        confidence=0.8,
        observed_at="2026-03-16T12:00:00Z",
    )
    d = obs.to_dict()
    assert isinstance(d, dict)
    assert d["observation_type"] == "bgp_peer"
    assert d["source"] == "bgp"
    assert d["device_id"] == "edge-1"
    assert d["data"] == {"peer_as": 65001}
    assert d["confidence"] == 0.8
    assert d["observed_at"] == "2026-03-16T12:00:00Z"


def test_observation_has_timestamp():
    """observed_at defaults to a non-None value."""
    obs = DiscoveryObservation(
        observation_type=ObservationType.INTERFACE,
        source="lldp",
        device_id="sw-1",
    )
    assert obs.observed_at is not None


def test_observation_defaults():
    """Default confidence is 0.5 and data is empty dict."""
    obs = DiscoveryObservation(
        observation_type=ObservationType.ROUTE,
        source="ospf",
        device_id="rtr-2",
    )
    assert obs.confidence == 0.5
    assert obs.data == {}


def test_cannot_instantiate_abstract():
    """DiscoveryAdapter cannot be instantiated directly."""
    with pytest.raises(TypeError):
        DiscoveryAdapter()


def test_defines_discover_method():
    """DiscoveryAdapter defines a discover method."""
    assert hasattr(DiscoveryAdapter, "discover")


def test_defines_supports_method():
    """DiscoveryAdapter defines a supports method."""
    assert hasattr(DiscoveryAdapter, "supports")

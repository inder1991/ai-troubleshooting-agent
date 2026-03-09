"""Tests for flow write cardinality control."""
from src.network.metrics_store import ip_to_subnet_tag


def test_ip_to_subnet_tag_default_24():
    assert ip_to_subnet_tag("10.0.0.123") == "10.0.0.0/24"
    assert ip_to_subnet_tag("192.168.1.55") == "192.168.1.0/24"


def test_ip_to_subnet_tag_custom_prefix():
    assert ip_to_subnet_tag("10.0.1.123", prefix=16) == "10.0.0.0/16"


def test_ip_to_subnet_tag_invalid():
    assert ip_to_subnet_tag("invalid") == "unknown"


def test_ip_to_subnet_tag_edge_cases():
    assert ip_to_subnet_tag("0.0.0.0") == "0.0.0.0/24"
    assert ip_to_subnet_tag("255.255.255.255") == "255.255.255.0/24"

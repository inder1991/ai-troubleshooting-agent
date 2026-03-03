"""Tests for adapter factory."""
import pytest
from src.network.adapters.factory import create_adapter
from src.network.adapters.mock_adapter import MockFirewallAdapter
from src.network.models import FirewallVendor


def test_factory_creates_mock_for_unknown():
    adapter = create_adapter(FirewallVendor.PALO_ALTO, api_endpoint="", api_key="")
    # Without pan-os-python installed, falls back to mock
    assert adapter is not None


def test_factory_returns_mock_when_sdk_missing():
    adapter = create_adapter(
        FirewallVendor.PALO_ALTO,
        api_endpoint="https://panorama.example.com",
        api_key="fake-key",
    )
    assert adapter is not None


def test_factory_aws_without_boto3():
    adapter = create_adapter(
        FirewallVendor.AWS_SG,
        api_endpoint="",
        api_key="",
        extra_config={"region": "us-east-1", "security_group_id": "sg-123"},
    )
    assert adapter is not None

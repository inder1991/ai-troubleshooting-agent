"""Tests for adapter factory."""
from src.network.adapters.factory import create_adapter
from src.network.adapters.base import FirewallAdapter
from src.network.adapters.mock_adapter import MockFirewallAdapter
from src.network.models import FirewallVendor


def test_factory_creates_mock_for_unknown():
    adapter = create_adapter(FirewallVendor.PALO_ALTO, api_endpoint="", api_key="")
    # No endpoint provided, falls back to mock
    assert isinstance(adapter, MockFirewallAdapter)


def test_factory_returns_mock_when_sdk_missing():
    adapter = create_adapter(
        FirewallVendor.PALO_ALTO,
        api_endpoint="https://panorama.example.com",
        api_key="fake-key",
    )
    # pan-os-python not installed -> falls back to mock
    assert isinstance(adapter, MockFirewallAdapter)
    assert adapter.vendor == FirewallVendor.PALO_ALTO


def test_factory_aws_returns_adapter():
    adapter = create_adapter(
        FirewallVendor.AWS_SG,
        api_endpoint="",
        api_key="",
        extra_config={"region": "us-east-1", "security_group_id": "sg-123"},
    )
    # Returns a FirewallAdapter (real if boto3 installed, mock otherwise)
    assert isinstance(adapter, FirewallAdapter)
    assert adapter.vendor == FirewallVendor.AWS_SG


def test_factory_cisco_returns_adapter():
    from src.network.adapters.cisco_adapter import CiscoAdapter
    adapter = create_adapter(
        FirewallVendor.CISCO,
        api_endpoint="192.168.1.1",
        api_key="",
        extra_config={"username": "admin", "password": "cisco"},
    )
    assert isinstance(adapter, CiscoAdapter)
    assert adapter.vendor == FirewallVendor.CISCO


def test_factory_f5_returns_adapter():
    from src.network.adapters.f5_adapter import F5Adapter
    adapter = create_adapter(
        FirewallVendor.F5,
        api_endpoint="192.168.1.245",
        api_key="",
        extra_config={"username": "admin", "password": "admin"},
    )
    assert isinstance(adapter, F5Adapter)
    assert adapter.vendor == FirewallVendor.F5


def test_factory_checkpoint_returns_adapter():
    from src.network.adapters.checkpoint_adapter import CheckpointAdapter
    adapter = create_adapter(
        FirewallVendor.CHECKPOINT,
        api_endpoint="192.168.1.100",
        api_key="",
        extra_config={"username": "admin", "password": "cpw0rd"},
    )
    assert isinstance(adapter, CheckpointAdapter)
    assert adapter.vendor == FirewallVendor.CHECKPOINT

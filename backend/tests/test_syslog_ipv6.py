"""Tests for IPv6 syslog support (#28)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.network.collectors.syslog_listener import SyslogListener


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def instance_store():
    store = MagicMock()
    store.get_device_by_ip = MagicMock(return_value=None)
    return store


class TestIPv6Constructor:
    """Test that IPv6 parameter is accepted by the constructor."""

    def test_default_ipv6_disabled(self, event_bus, instance_store):
        listener = SyslogListener(event_bus, instance_store)
        assert listener._listen_ipv6 is False

    def test_ipv6_enabled(self, event_bus, instance_store):
        listener = SyslogListener(event_bus, instance_store, listen_ipv6=True)
        assert listener._listen_ipv6 is True

    def test_ipv6_disabled_explicit(self, event_bus, instance_store):
        listener = SyslogListener(event_bus, instance_store, listen_ipv6=False)
        assert listener._listen_ipv6 is False

    def test_transport_v6_initially_none(self, event_bus, instance_store):
        listener = SyslogListener(event_bus, instance_store, listen_ipv6=True)
        assert listener._transport_v6 is None


class TestIPv6DatagramHandling:
    """Test that the protocol handler processes messages from IPv6 addresses."""

    def test_handle_datagram_from_ipv4(self, event_bus, instance_store):
        """IPv4 source addresses should work normally."""
        listener = SyslogListener(event_bus, instance_store)
        msg = b"<134>Mar  9 12:34:56 myhost myapp[1234]: test message"
        listener._handle_datagram(msg, ("192.168.1.1", 514))
        assert listener._recv_count == 1
        assert listener._error_count == 0

    def test_handle_datagram_from_ipv6(self, event_bus, instance_store):
        """IPv6 source addresses should be processed without error."""
        listener = SyslogListener(event_bus, instance_store)
        msg = b"<134>Mar  9 12:34:56 myhost myapp[1234]: test message from ipv6"
        listener._handle_datagram(msg, ("::1", 514))
        assert listener._recv_count == 1
        assert listener._error_count == 0

    def test_handle_datagram_from_full_ipv6(self, event_bus, instance_store):
        """Full IPv6 addresses should work."""
        listener = SyslogListener(event_bus, instance_store)
        msg = b"<134>Mar  9 12:34:56 myhost myapp[1234]: ipv6 full address test"
        listener._handle_datagram(msg, ("2001:db8::1", 514))
        assert listener._recv_count == 1
        assert listener._error_count == 0

    def test_handle_datagram_from_ipv6_mapped_ipv4(self, event_bus, instance_store):
        """IPv4-mapped IPv6 addresses (::ffff:x.x.x.x) should work."""
        listener = SyslogListener(event_bus, instance_store)
        msg = b"<134>Mar  9 12:34:56 myhost myapp[1234]: mapped address"
        listener._handle_datagram(msg, ("::ffff:10.0.0.1", 514))
        assert listener._recv_count == 1
        assert listener._error_count == 0

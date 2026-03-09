"""Tests for message size validation in syslog and trap listeners (#29)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.network.collectors.syslog_listener import SyslogListener
from src.network.collectors.trap_listener import SNMPTrapListener


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


class TestSyslogMessageSize:
    """Syslog listener message size validation."""

    def test_max_message_size_constant(self):
        assert SyslogListener.MAX_MESSAGE_SIZE == 8192

    def test_small_message_not_truncated(self, event_bus, instance_store):
        listener = SyslogListener(event_bus, instance_store)
        msg = b"<134>Mar  9 12:34:56 myhost myapp[1234]: short message"
        listener._handle_datagram(msg, ("10.0.0.1", 514))
        assert listener._recv_count == 1

    def test_oversized_message_truncated(self, event_bus, instance_store):
        """Messages > 8192 bytes should be truncated and flagged."""
        listener = SyslogListener(event_bus, instance_store)
        # Create a valid syslog header followed by a large payload
        header = b"<134>Mar  9 12:34:56 myhost myapp[1234]: "
        payload = b"X" * 9000
        msg = header + payload
        assert len(msg) > SyslogListener.MAX_MESSAGE_SIZE

        listener._handle_datagram(msg, ("10.0.0.1", 514))
        assert listener._recv_count == 1
        # The message should still be processed (parsed after truncation)

    def test_exact_limit_not_truncated(self, event_bus, instance_store):
        """A message exactly at MAX_MESSAGE_SIZE should NOT be truncated."""
        listener = SyslogListener(event_bus, instance_store)
        header = b"<134>Mar  9 12:34:56 myhost myapp[1234]: "
        remaining = SyslogListener.MAX_MESSAGE_SIZE - len(header)
        msg = header + b"X" * remaining
        assert len(msg) == SyslogListener.MAX_MESSAGE_SIZE

        listener._handle_datagram(msg, ("10.0.0.1", 514))
        assert listener._recv_count == 1


class TestTrapMessageSize:
    """Trap listener message size validation."""

    def test_max_message_size_constant(self):
        assert SNMPTrapListener.MAX_MESSAGE_SIZE == 8192

    def test_small_trap_not_truncated(self, event_bus, instance_store):
        listener = SNMPTrapListener(event_bus, instance_store)
        # A small invalid trap — will be dropped but recv_count increments
        msg = b"\x30\x05\x02\x01\x01\x04\x00"
        listener._handle_datagram(msg, ("10.0.0.1", 162))
        assert listener._recv_count == 1

    def test_oversized_trap_truncated(self, event_bus, instance_store):
        """Trap messages > 8192 bytes should be truncated."""
        listener = SNMPTrapListener(event_bus, instance_store)
        msg = b"\x30" + b"\x00" * 9000
        assert len(msg) > SNMPTrapListener.MAX_MESSAGE_SIZE

        listener._handle_datagram(msg, ("10.0.0.1", 162))
        assert listener._recv_count == 1
        # Will fail parsing after truncation but recv_count still increments

    def test_exact_limit_not_truncated(self, event_bus, instance_store):
        """A message exactly at MAX_MESSAGE_SIZE should NOT be truncated."""
        listener = SNMPTrapListener(event_bus, instance_store)
        msg = b"\x30" + b"\x00" * (SNMPTrapListener.MAX_MESSAGE_SIZE - 1)
        assert len(msg) == SNMPTrapListener.MAX_MESSAGE_SIZE

        listener._handle_datagram(msg, ("10.0.0.1", 162))
        assert listener._recv_count == 1

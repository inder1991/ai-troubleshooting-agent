"""Tests for UDP receive buffer size configuration (#30)."""

import socket
import pytest
from unittest.mock import MagicMock

from src.network.collectors.syslog_listener import SyslogListener
from src.network.collectors.trap_listener import SNMPTrapListener


EXPECTED_BUFFER_SIZE = 4 * 1024 * 1024  # 4 MB


class TestSyslogBufferSize:
    """Syslog listener socket buffer configuration."""

    def test_recv_buffer_size_constant(self):
        assert SyslogListener.RECV_BUFFER_SIZE == EXPECTED_BUFFER_SIZE

    def test_set_socket_buffer_calls_setsockopt(self):
        """Verify setsockopt is called with correct args."""
        mock_sock = MagicMock()
        mock_transport = MagicMock()
        mock_transport.get_extra_info.return_value = mock_sock

        SyslogListener._set_socket_buffer(mock_transport)

        mock_transport.get_extra_info.assert_called_once_with('socket')
        mock_sock.setsockopt.assert_called_once_with(
            socket.SOL_SOCKET, socket.SO_RCVBUF, EXPECTED_BUFFER_SIZE
        )

    def test_set_socket_buffer_no_socket_graceful(self):
        """If transport has no socket, _set_socket_buffer should not crash."""
        mock_transport = MagicMock()
        mock_transport.get_extra_info.return_value = None

        # Should not raise
        SyslogListener._set_socket_buffer(mock_transport)

        mock_transport.get_extra_info.assert_called_once_with('socket')


class TestTrapBufferSize:
    """Trap listener socket buffer configuration."""

    def test_recv_buffer_size_constant(self):
        assert SNMPTrapListener.RECV_BUFFER_SIZE == EXPECTED_BUFFER_SIZE

    def test_set_socket_buffer_calls_setsockopt(self):
        """Verify setsockopt is called with correct args."""
        mock_sock = MagicMock()
        mock_transport = MagicMock()
        mock_transport.get_extra_info.return_value = mock_sock

        SNMPTrapListener._set_socket_buffer(mock_transport)

        mock_transport.get_extra_info.assert_called_once_with('socket')
        mock_sock.setsockopt.assert_called_once_with(
            socket.SOL_SOCKET, socket.SO_RCVBUF, EXPECTED_BUFFER_SIZE
        )

    def test_set_socket_buffer_no_socket_graceful(self):
        """If transport has no socket, _set_socket_buffer should not crash."""
        mock_transport = MagicMock()
        mock_transport.get_extra_info.return_value = None

        # Should not raise
        SNMPTrapListener._set_socket_buffer(mock_transport)

        mock_transport.get_extra_info.assert_called_once_with('socket')

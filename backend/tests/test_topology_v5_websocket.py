"""Tests for v5 topology WebSocket endpoint."""
import pytest
from src.api.topology_v5 import get_ws_publisher


class TestWebSocketEndpoint:
    def test_ws_publisher_singleton(self):
        pub1 = get_ws_publisher()
        pub2 = get_ws_publisher()
        assert pub1 is pub2

    def test_ws_publisher_has_register(self):
        pub = get_ws_publisher()
        assert hasattr(pub, 'register')
        assert hasattr(pub, 'unregister')

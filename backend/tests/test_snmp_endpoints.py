"""Tests for SNMP configuration endpoints and collector logic."""
import time
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

from src.network.snmp_collector import SNMPCollector, SNMPDeviceConfig


class TestSNMPCollectorRates:
    def test_first_poll_returns_none(self):
        collector = SNMPCollector(MagicMock())
        result = collector._compute_rates("d1", 1, {"ifInOctets": 1000, "ifOutOctets": 2000, "ifSpeed": 1_000_000_000})
        assert result is None

    def test_second_poll_returns_rates(self):
        collector = SNMPCollector(MagicMock())
        collector._prev_counters[("d1", 1)] = (
            {"ifInOctets": 1000, "ifOutOctets": 2000, "ifSpeed": 1_000_000_000},
            time.time() - 10,
        )
        result = collector._compute_rates("d1", 1, {"ifInOctets": 2000, "ifOutOctets": 3000, "ifSpeed": 1_000_000_000})
        assert result is not None
        assert result["bps_in"] > 0
        assert result["bps_out"] > 0
        assert 0 <= result["utilization"] <= 1

    def test_counter_wraparound_32bit(self):
        collector = SNMPCollector(MagicMock())
        collector._prev_counters[("d1", 1)] = (
            {"ifInOctets": 2**32 - 100, "ifOutOctets": 0, "ifSpeed": 1_000_000_000},
            time.time() - 10,
        )
        result = collector._compute_rates("d1", 1, {"ifInOctets": 100, "ifOutOctets": 0, "ifSpeed": 1_000_000_000})
        assert result is not None
        assert result["bps_in"] > 0

    def test_error_rate_calculation(self):
        collector = SNMPCollector(MagicMock())
        collector._prev_counters[("d1", 1)] = (
            {"ifInOctets": 0, "ifOutOctets": 0, "ifInErrors": 0, "ifOutErrors": 0, "ifSpeed": 1_000_000_000},
            time.time() - 10,
        )
        result = collector._compute_rates("d1", 1, {
            "ifInOctets": 1000, "ifOutOctets": 1000,
            "ifInErrors": 5, "ifOutErrors": 5, "ifSpeed": 1_000_000_000,
        })
        assert result is not None
        assert result["error_rate"] > 0

    def test_hc_counters_preferred(self):
        collector = SNMPCollector(MagicMock())
        collector._prev_counters[("d1", 1)] = (
            {"ifHCInOctets": 0, "ifHCOutOctets": 0, "ifInOctets": 0, "ifOutOctets": 0, "ifSpeed": 1_000_000_000},
            time.time() - 10,
        )
        result = collector._compute_rates("d1", 1, {
            "ifHCInOctets": 5000, "ifHCOutOctets": 3000,
            "ifInOctets": 100, "ifOutOctets": 100, "ifSpeed": 1_000_000_000,
        })
        assert result is not None
        assert result["bps_in"] > 0


class TestSNMPConfigEndpoints:
    def test_get_snmp_config(self):
        from src.api.main import app
        from src.api import snmp_endpoints
        import networkx as nx
        g = nx.DiGraph()
        g.add_node("d1", snmp_enabled=True, snmp_version="v2c", snmp_community="public", snmp_port=161)
        mock_kg = MagicMock()
        mock_kg.graph = g
        original = snmp_endpoints._knowledge_graph
        snmp_endpoints._knowledge_graph = mock_kg
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/snmp/d1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["snmp_enabled"] is True
            assert data["snmp_version"] == "v2c"
        finally:
            snmp_endpoints._knowledge_graph = original

    def test_update_snmp_config(self):
        from src.api.main import app
        from src.api import snmp_endpoints
        import networkx as nx
        g = nx.DiGraph()
        g.add_node("d1", device_type="router")
        mock_kg = MagicMock()
        mock_kg.graph = g
        original = snmp_endpoints._knowledge_graph
        snmp_endpoints._knowledge_graph = mock_kg
        try:
            client = TestClient(app)
            resp = client.put("/api/v4/network/snmp/d1", json={
                "snmp_enabled": True, "snmp_version": "v2c",
                "snmp_community": "private", "snmp_port": 161,
            })
            assert resp.status_code == 200
            assert g.nodes["d1"]["snmp_enabled"] is True
            assert g.nodes["d1"]["snmp_community"] == "private"
        finally:
            snmp_endpoints._knowledge_graph = original

    def test_get_snmp_config_not_found(self):
        from src.api.main import app
        from src.api import snmp_endpoints
        import networkx as nx
        g = nx.DiGraph()
        mock_kg = MagicMock()
        mock_kg.graph = g
        original = snmp_endpoints._knowledge_graph
        snmp_endpoints._knowledge_graph = mock_kg
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/snmp/nonexistent")
            assert resp.status_code == 404
        finally:
            snmp_endpoints._knowledge_graph = original

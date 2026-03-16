"""Tests for LLDP/CDP discovery adapter."""

import asyncio

import pytest

from src.network.discovery.lldp_adapter import LLDPDiscoveryAdapter
from src.network.discovery.observation import DiscoveryObservation, ObservationType


def _run_async_gen(coro_fn):
    """Collect all items from an async generator using a new event loop."""
    loop = asyncio.new_event_loop()
    try:

        async def _collect():
            return [item async for item in coro_fn]

        return loop.run_until_complete(_collect())
    finally:
        loop.close()


class TestLLDPDiscoveryAdapter:
    def test_supports_device_target(self):
        adapter = LLDPDiscoveryAdapter()
        assert adapter.supports({"type": "device"}) is True

    def test_does_not_support_cloud(self):
        adapter = LLDPDiscoveryAdapter()
        assert adapter.supports({"type": "cloud_account"}) is False

    def test_discover_yields_neighbor_observations(self):
        mock_neighbors = {
            "switch-01": [
                {
                    "local_interface": "Gi0/1",
                    "remote_device": "router-01",
                    "remote_interface": "Gi0/0",
                    "remote_ip": "10.0.0.1",
                    "protocol": "lldp",
                    "chassis_id": "aa:bb:cc:dd:ee:ff",
                }
            ]
        }
        adapter = LLDPDiscoveryAdapter(mock_neighbors=mock_neighbors)
        target = {"type": "device", "device_id": "switch-01"}

        results = _run_async_gen(adapter.discover(target))

        assert len(results) == 1
        obs = results[0]
        assert isinstance(obs, DiscoveryObservation)
        assert obs.observation_type == ObservationType.NEIGHBOR
        assert obs.source == "lldp"
        assert obs.device_id == "switch-01"
        assert obs.confidence == 0.95
        assert obs.data["local_interface"] == "Gi0/1"
        assert obs.data["remote_device"] == "router-01"
        assert obs.data["remote_interface"] == "Gi0/0"
        assert obs.data["remote_ip"] == "10.0.0.1"
        assert obs.data["protocol"] == "lldp"
        assert obs.data["chassis_id"] == "aa:bb:cc:dd:ee:ff"

    def test_discover_cdp_confidence(self):
        mock_neighbors = {
            "switch-02": [
                {
                    "local_interface": "Fa0/1",
                    "remote_device": "phone-01",
                    "remote_interface": "Port 1",
                    "remote_ip": "10.0.1.5",
                    "protocol": "cdp",
                    "chassis_id": "11:22:33:44:55:66",
                }
            ]
        }
        adapter = LLDPDiscoveryAdapter(mock_neighbors=mock_neighbors)
        target = {"type": "device", "device_id": "switch-02"}

        results = _run_async_gen(adapter.discover(target))
        assert len(results) == 1
        assert results[0].confidence == 0.90

    def test_discover_empty_neighbors(self):
        adapter = LLDPDiscoveryAdapter(mock_neighbors={})
        target = {"type": "device", "device_id": "switch-99"}

        results = _run_async_gen(adapter.discover(target))

        assert len(results) == 0

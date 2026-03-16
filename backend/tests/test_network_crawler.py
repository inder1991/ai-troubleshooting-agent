"""Tests for BFS network crawler."""

import asyncio

import pytest

from src.network.discovery.crawler import CrawlResult, NetworkCrawler
from src.network.discovery.entity_resolver import EntityResolver
from src.network.discovery.lldp_adapter import LLDPDiscoveryAdapter
from src.network.discovery.observation_handler import ObservationHandler
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.topology_store import TopologyStore


# ── Mock neighbor chain: rtr-01 → sw-01 → sw-02 ─────────────────────────

MOCK_NEIGHBORS = {
    "rtr-01": [
        {
            "local_interface": "Gi0/0",
            "remote_device": "sw-01",
            "remote_interface": "Gi0/48",
            "protocol": "lldp",
            "remote_ip": "10.0.0.2",
        }
    ],
    "sw-01": [
        {
            "local_interface": "Gi0/48",
            "remote_device": "rtr-01",
            "remote_interface": "Gi0/0",
            "protocol": "lldp",
            "remote_ip": "10.0.0.1",
        },
        {
            "local_interface": "Gi0/1",
            "remote_device": "sw-02",
            "remote_interface": "Gi0/1",
            "protocol": "lldp",
            "remote_ip": "10.0.0.3",
        },
    ],
    "sw-02": [
        {
            "local_interface": "Gi0/1",
            "remote_device": "sw-01",
            "remote_interface": "Gi0/1",
            "protocol": "lldp",
            "remote_ip": "10.0.0.2",
        }
    ],
}


@pytest.fixture()
def crawler_components(tmp_path):
    """Build all crawler components with a temp topology store."""
    store = TopologyStore(db_path=str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)
    resolver = EntityResolver(repo)
    handler = ObservationHandler(repo, resolver)
    adapter = LLDPDiscoveryAdapter(mock_neighbors=MOCK_NEIGHBORS)
    return adapter, handler, repo


@pytest.fixture()
def crawler(crawler_components):
    adapter, handler, _repo = crawler_components
    return NetworkCrawler(adapters=[adapter], handler=handler)


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestNetworkCrawler:
    def test_crawl_from_seed(self, crawler):
        """Seeding rtr-01 should discover at least 1 device."""
        seeds = [{"type": "device", "device_id": "rtr-01"}]
        result = _run(crawler.crawl(seeds))

        assert isinstance(result, CrawlResult)
        assert result.devices_discovered >= 1

    def test_crawl_discovers_neighbors(self, crawler):
        """BFS from rtr-01 with depth 3 should reach sw-01 and sw-02."""
        seeds = [{"type": "device", "device_id": "rtr-01"}]
        result = _run(crawler.crawl(seeds, max_depth=3))

        assert result.devices_discovered >= 2
        assert result.links_discovered >= 1

    def test_crawl_respects_max_depth(self, crawler):
        """max_depth=1 limits how far BFS can reach from the seed."""
        seeds = [{"type": "device", "device_id": "rtr-01"}]
        result = _run(crawler.crawl(seeds, max_depth=1))

        # depth=0 is rtr-01, depth=1 is sw-01, sw-02 would be depth=2
        assert result.max_depth_reached <= 1
        # Should NOT have reached sw-02
        assert "sw-02" not in result.devices

    def test_crawl_no_infinite_loop(self, crawler):
        """Even with high max_depth, visited set prevents infinite loops."""
        seeds = [{"type": "device", "device_id": "rtr-01"}]
        result = _run(crawler.crawl(seeds, max_depth=10))

        # The chain is only 3 devices; must terminate
        assert result.devices_discovered <= 3
        assert result.max_depth_reached <= 10

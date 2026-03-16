"""Tests for DiscoveryScheduler — orchestrates periodic discovery runs."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.network.discovery.scheduler import DiscoveryScheduler


def test_instantiation():
    """Default intervals should be 300, 900, 3600."""
    scheduler = DiscoveryScheduler(adapters=[])
    assert scheduler.incremental_interval == 300
    assert scheduler.cloud_sync_interval == 900
    assert scheduler.full_crawl_interval == 3600


def test_custom_intervals():
    """Custom intervals should override the defaults."""
    scheduler = DiscoveryScheduler(
        adapters=[],
        handler=MagicMock(),
        crawler=MagicMock(),
        incremental_interval=60,
        cloud_sync_interval=120,
        full_crawl_interval=600,
    )
    assert scheduler.incremental_interval == 60
    assert scheduler.cloud_sync_interval == 120
    assert scheduler.full_crawl_interval == 600

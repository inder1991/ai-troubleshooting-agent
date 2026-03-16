"""DiscoveryScheduler — orchestrates periodic discovery runs.

Three concurrent loops run at different cadences:
  * **Incremental** — polls known devices for changes (fast).
  * **Cloud sync** — refreshes cloud-provider adapters (medium).
  * **Full crawl** — BFS walk of the entire topology (slow).

Each loop catches and logs exceptions so that a single failure never
kills the scheduler.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .adapter import DiscoveryAdapter

logger = logging.getLogger(__name__)


class DiscoveryScheduler:
    """Orchestrate periodic discovery across adapters, handler, and crawler."""

    def __init__(
        self,
        adapters: List["DiscoveryAdapter"],
        handler: Optional[object] = None,
        crawler: Optional[object] = None,
        incremental_interval: int = 300,
        cloud_sync_interval: int = 900,
        full_crawl_interval: int = 3600,
    ) -> None:
        self.adapters = adapters
        self.handler = handler
        self.crawler = crawler
        self.incremental_interval = incremental_interval
        self.cloud_sync_interval = cloud_sync_interval
        self.full_crawl_interval = full_crawl_interval
        self._running = False

    # ── Public API ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start all three discovery loops concurrently."""
        self._running = True
        logger.info("DiscoveryScheduler starting")
        await asyncio.gather(
            self._run_incremental_loop(),
            self._run_cloud_sync_loop(),
            self._run_full_crawl_loop(),
        )

    def stop(self) -> None:
        """Signal all loops to stop after their current iteration."""
        logger.info("DiscoveryScheduler stopping")
        self._running = False

    # ── Private loops ─────────────────────────────────────────────────────

    async def _run_incremental_loop(self) -> None:
        """Poll known devices every *incremental_interval* seconds."""
        while self._running:
            try:
                logger.debug("Incremental discovery tick")
                if self.handler is None:
                    await asyncio.sleep(self.incremental_interval)
                    continue
                # Run device-type adapters against known devices
                for adapter in self.adapters:
                    if adapter.supports({"type": "device"}):
                        # In production, iterate known devices from repo
                        # For now, adapters with mock data run against their own targets
                        try:
                            async for obs in adapter.discover({"type": "device", "device_id": "__incremental__"}):
                                self.handler.handle(obs)
                        except Exception:
                            logger.debug("Adapter %s has no incremental targets", adapter.__class__.__name__)
            except Exception:
                logger.exception("Error in incremental discovery loop")
            await asyncio.sleep(self.incremental_interval)

    async def _run_cloud_sync_loop(self) -> None:
        """Run cloud-provider adapters every *cloud_sync_interval* seconds."""
        while self._running:
            try:
                logger.debug("Cloud sync tick")
                if self.handler is None:
                    await asyncio.sleep(self.cloud_sync_interval)
                    continue
                for adapter in self.adapters:
                    if adapter.supports({"type": "cloud_account", "provider": "aws"}):
                        try:
                            async for obs in adapter.discover({"type": "cloud_account", "provider": "aws"}):
                                self.handler.handle(obs)
                        except Exception:
                            logger.debug("Cloud adapter %s failed", adapter.__class__.__name__)
            except Exception:
                logger.exception("Error in cloud sync loop")
            await asyncio.sleep(self.cloud_sync_interval)

    async def _run_full_crawl_loop(self) -> None:
        """BFS crawl the topology every *full_crawl_interval* seconds."""
        while self._running:
            try:
                logger.debug("Full crawl tick")
                if self.crawler is not None and hasattr(self.crawler, "crawl"):
                    seeds = getattr(self, "seed_devices", [])
                    if seeds:
                        await self.crawler.crawl(seeds=seeds, max_depth=5, max_devices=1000)
                    else:
                        logger.debug("No seed devices configured for full crawl")
            except Exception:
                logger.exception("Error in full crawl loop")
            await asyncio.sleep(self.full_crawl_interval)

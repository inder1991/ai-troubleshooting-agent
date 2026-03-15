"""Ping probe scheduler — ICMP probes to configured targets."""

from __future__ import annotations

import asyncio
import random
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def _mock_ping(target_ip: str) -> dict:
    """Mock ping — returns realistic RTT and loss.

    In production, use subprocess with 'ping' or raw ICMP socket.
    """
    await asyncio.sleep(random.uniform(0.01, 0.05))

    # Most targets respond well; occasionally simulate degradation
    base_rtt = hash(target_ip) % 20 + 1  # 1-20ms base
    if random.random() < 0.05:  # 5% chance of packet loss
        return {"avg_rtt_ms": base_rtt * 3, "packet_loss_pct": random.choice([20, 33, 50, 100]), "status": "degraded"}
    return {"avg_rtt_ms": base_rtt + random.uniform(-0.5, 2), "packet_loss_pct": 0, "status": "ok"}


class PingProbeScheduler:
    """Probes configured targets at regular intervals."""

    def __init__(self, metrics_store, interval_seconds: int = 30):
        self.store = metrics_store
        self.interval = interval_seconds
        self._targets: list[dict] = []
        self._running = False

    def set_targets(self, targets: list[dict]) -> None:
        """Set probe targets. Each: {"ip": "10.1.40.10", "name": "pa-core-fw-01"}"""
        self._targets = targets
        logger.info("Ping probes: %d targets configured", len(targets))

    async def start(self) -> None:
        self._running = True
        logger.info("Ping probe scheduler started (interval: %ds, targets: %d)", self.interval, len(self._targets))
        while self._running:
            if self._targets:
                tasks = [self._probe(t) for t in self._targets]
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(self.interval)

    async def _probe(self, target: dict) -> None:
        ip = target.get("ip", "")
        if not ip:
            return
        try:
            result = await _mock_ping(ip)
            self.store.write_probe_metric(
                target_ip=ip,
                probe_type="icmp",
                latency_ms=result["avg_rtt_ms"],
                packet_loss_pct=result["packet_loss_pct"],
                status=result["status"],
            )
        except Exception as e:
            logger.error("Ping probe failed for %s: %s", ip, e)

    def stop(self) -> None:
        self._running = False

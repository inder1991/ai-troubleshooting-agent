"""ICMP ping prober — lightweight reachability + RTT for monitored devices."""
from __future__ import annotations

import asyncio
import logging
import platform
import time

from .models import DeviceInstance, PingConfig, PingResult

logger = logging.getLogger(__name__)


class PingProber:
    """ICMP reachability + RTT prober for monitored devices."""

    def __init__(self, max_concurrent: int = 20) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def probe(self, ip: str, config: PingConfig | None = None) -> PingResult:
        """Ping a single IP and return results."""
        cfg = config or PingConfig()
        if not cfg.enabled:
            return PingResult(reachable=False, timestamp=time.time())

        async with self._semaphore:
            return await self._do_ping(ip, cfg)

    async def probe_batch(
        self, devices: list[DeviceInstance]
    ) -> dict[str, PingResult]:
        """Probe multiple devices concurrently. Returns {device_id: PingResult}."""
        tasks = {}
        for dev in devices:
            if dev.ping_config and dev.ping_config.enabled:
                tasks[dev.device_id] = self.probe(dev.management_ip, dev.ping_config)

        if not tasks:
            return {}

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        out: dict[str, PingResult] = {}
        for device_id, result in zip(tasks.keys(), results):
            if isinstance(result, PingResult):
                out[device_id] = result
            else:
                out[device_id] = PingResult(
                    reachable=False, packet_loss_pct=100.0, timestamp=time.time()
                )
        return out

    async def _do_ping(self, ip: str, cfg: PingConfig) -> PingResult:
        """Execute system ping and parse output."""
        system = platform.system().lower()
        count_flag = "-n" if system == "windows" else "-c"
        timeout_flag = "-w" if system == "windows" else "-W"
        timeout_val = str(cfg.timeout // 1000) if system != "windows" else str(cfg.timeout)

        cmd = ["ping", count_flag, str(cfg.count), timeout_flag, timeout_val, ip]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=cfg.timeout / 1000 + 5
            )
            output = stdout.decode(errors="replace")
            return self._parse_ping_output(output, cfg.count)
        except asyncio.TimeoutError:
            return PingResult(
                reachable=False, packet_loss_pct=100.0, timestamp=time.time()
            )
        except Exception as e:
            logger.debug("Ping %s failed: %s", ip, e)
            return PingResult(
                reachable=False, packet_loss_pct=100.0, timestamp=time.time()
            )

    @staticmethod
    def _parse_ping_output(output: str, count: int) -> PingResult:
        """Parse ping command output for RTT and packet loss."""
        import re

        now = time.time()

        # Parse packet loss
        loss_match = re.search(r"(\d+(?:\.\d+)?)%\s*packet\s*loss", output)
        loss_pct = float(loss_match.group(1)) if loss_match else 100.0

        # Parse RTT (macOS/Linux: "min/avg/max/stddev = 1.2/3.4/5.6/0.8 ms")
        rtt_match = re.search(
            r"(?:rtt|round-trip)\s+min/avg/max/(?:stddev|mdev)\s*=\s*"
            r"([\d.]+)/([\d.]+)/([\d.]+)",
            output,
        )

        if rtt_match:
            rtt_min = float(rtt_match.group(1))
            rtt_avg = float(rtt_match.group(2))
            rtt_max = float(rtt_match.group(3))
        else:
            # Windows: "Minimum = 1ms, Maximum = 5ms, Average = 3ms"
            win_match = re.search(
                r"Minimum\s*=\s*(\d+)\s*ms.*Maximum\s*=\s*(\d+)\s*ms.*Average\s*=\s*(\d+)\s*ms",
                output,
            )
            if win_match:
                rtt_min = float(win_match.group(1))
                rtt_max = float(win_match.group(2))
                rtt_avg = float(win_match.group(3))
            else:
                rtt_min = rtt_avg = rtt_max = 0.0

        return PingResult(
            rtt_avg=rtt_avg,
            rtt_min=rtt_min,
            rtt_max=rtt_max,
            packet_loss_pct=loss_pct,
            reachable=loss_pct < 100.0,
            timestamp=now,
        )

"""DNS Monitor — query timing, health checks, and drift detection.

Provides the DNSMonitor class that resolves watched hostnames against
configured DNS servers, tracks NXDOMAIN counts, detects answer drift
(unexpected record values), and exposes per-query latency metrics.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .models import DNSMonitorConfig, DNSServerConfig, DNSWatchedHostname, DNSRecordType

# Graceful degradation when dnspython is not installed
try:
    import dns.asyncresolver  # type: ignore
    import dns.rdatatype  # type: ignore
    import dns.exception  # type: ignore
    import dns.name  # type: ignore
    HAS_DNSPYTHON = True
except ImportError:  # pragma: no cover
    HAS_DNSPYTHON = False

logger = logging.getLogger(__name__)

# ── Record-type to dnspython rdtype mapping ──
_RDTYPE_MAP: dict[str, str] = {
    "A": "A",
    "AAAA": "AAAA",
    "MX": "MX",
    "NS": "NS",
    "CNAME": "CNAME",
    "TXT": "TXT",
    "SOA": "SOA",
    "PTR": "PTR",
}


# ── Isolated resolver call (mockable in tests) ──

async def dns_resolver_resolve(
    server_ip: str,
    server_port: int,
    hostname: str,
    rdtype: str,
    timeout: float = 5.0,
) -> list[str]:
    """Perform a single DNS resolution and return answer strings.

    This function is extracted at module level so tests can patch
    ``src.network.dns_monitor.dns_resolver_resolve`` without touching the
    real dnspython library.
    """
    resolver = dns.asyncresolver.Resolver()  # type: ignore[name-defined]
    resolver.nameservers = [server_ip]
    resolver.port = server_port
    resolver.lifetime = timeout
    answer = await resolver.resolve(hostname, rdtype)
    return sorted(str(rdata) for rdata in answer)


# ── Query result dataclass ──

@dataclass
class DNSQueryResult:
    """Result of a single DNS query against one server for one hostname."""
    server_id: str
    server_ip: str
    hostname: str
    record_type: str
    values: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    success: bool = True
    error: str = ""
    nxdomain: bool = False


# ── DNSMonitor class ──

class DNSMonitor:
    """Runs DNS queries against configured servers, tracks health, drift, and NXDOMAIN counts."""

    def __init__(self, config: DNSMonitorConfig) -> None:
        self.config = config
        self._nxdomain_counts: dict[str, int] = defaultdict(int)  # hostname -> count
        self._server_health: dict[str, bool] = {}  # server_id -> healthy

    # ── Public API ──

    async def query_hostname(
        self,
        server: DNSServerConfig,
        watched: DNSWatchedHostname,
    ) -> DNSQueryResult:
        """Query a single hostname on a single server; return a DNSQueryResult."""
        rdtype = _RDTYPE_MAP.get(watched.record_type.value, "A")
        result = DNSQueryResult(
            server_id=server.id,
            server_ip=server.ip,
            hostname=watched.hostname,
            record_type=watched.record_type.value,
        )

        if not HAS_DNSPYTHON:
            result.success = False
            result.error = "dnspython not installed"
            return result

        t0 = time.monotonic()
        try:
            values = await dns_resolver_resolve(
                server.ip, server.port, watched.hostname, rdtype,
                timeout=self.config.query_timeout,
            )
            result.latency_ms = (time.monotonic() - t0) * 1000
            result.values = values
            result.success = True
        except Exception as exc:
            result.latency_ms = (time.monotonic() - t0) * 1000
            result.success = False
            exc_name = type(exc).__name__
            result.error = f"{exc_name}: {exc}"
            # Detect NXDOMAIN
            if "NXDOMAIN" in exc_name or "nxdomain" in str(exc).lower():
                result.nxdomain = True
                self._nxdomain_counts[watched.hostname] += 1

        return result

    async def check_server_health(self, server: DNSServerConfig) -> bool:
        """Probe a DNS server by resolving a well-known hostname.

        Returns True if the server responded successfully, False otherwise.
        """
        probe = DNSWatchedHostname(
            hostname=".",
            record_type=DNSRecordType.NS,
        )
        result = await self.query_hostname(server, probe)
        healthy = result.success
        self._server_health[server.id] = healthy
        return healthy

    def detect_drift(
        self,
        result: DNSQueryResult,
        watched: DNSWatchedHostname,
    ) -> dict[str, Any] | None:
        """Compare a query result against expected values; return drift dict or None."""
        if not watched.expected_values:
            return None
        if not result.success:
            return None

        expected = set(watched.expected_values)
        actual = set(result.values)

        if actual == expected:
            return None

        missing = expected - actual
        extra = actual - expected

        return {
            "hostname": watched.hostname,
            "record_type": watched.record_type.value,
            "server_id": result.server_id,
            "expected": sorted(expected),
            "actual": sorted(actual),
            "missing": sorted(missing),
            "extra": sorted(extra),
        }

    async def run_pass(self) -> list[dict[str, Any]]:
        """Execute a full monitoring pass across all servers and watched hostnames.

        Returns a list of metric dicts suitable for writing to InfluxDB.
        """
        if not self.config.enabled:
            return []

        metrics: list[dict[str, Any]] = []
        enabled_servers = [s for s in self.config.servers if s.enabled]

        for server in enabled_servers:
            for watched in self.config.watched_hostnames:
                result = await self.query_hostname(server, watched)
                drift = self.detect_drift(result, watched)

                metrics.append({
                    "measurement": "dns_query",
                    "server_id": server.id,
                    "server_ip": server.ip,
                    "hostname": watched.hostname,
                    "record_type": watched.record_type.value,
                    "latency_ms": result.latency_ms,
                    "success": result.success,
                    "nxdomain": result.nxdomain,
                    "values": result.values,
                    "drift": drift,
                    "critical": watched.critical,
                })

                if drift:
                    logger.warning(
                        "DNS drift detected: %s/%s on %s — expected %s, got %s",
                        watched.hostname,
                        watched.record_type.value,
                        server.id,
                        drift["expected"],
                        drift["actual"],
                    )

        return metrics

    def get_nxdomain_counts(self) -> dict[str, int]:
        """Return a copy of accumulated NXDOMAIN counts per hostname."""
        return dict(self._nxdomain_counts)

    def reset_nxdomain_counts(self) -> None:
        """Clear accumulated NXDOMAIN counts."""
        self._nxdomain_counts.clear()

"""Tests for discovery concurrency limiting via semaphore."""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.network.collectors.autodiscovery import AutodiscoveryEngine
from src.network.collectors.models import (
    DiscoveryConfig,
    PingConfig,
    SNMPVersion,
)


def _make_config(cidr: str = "10.0.0.0/28") -> DiscoveryConfig:
    """Create a minimal DiscoveryConfig for testing."""
    return DiscoveryConfig(
        config_id="test-config",
        cidr=cidr,
        snmp_version=SNMPVersion.V2C,
        community="public",
        port=161,
        interval_seconds=300,
        ping=PingConfig(enabled=False),
    )


class TestDiscoveryConcurrency:
    """Verify that discovery probes respect the concurrency semaphore."""

    @pytest.mark.asyncio
    async def test_discovery_concurrency_limited(self):
        """Discovery should not exceed max concurrent probes."""
        max_concurrent = 5
        concurrent_count = 0
        peak_concurrent = 0

        profile_loader = MagicMock()
        profile_loader.match.return_value = None

        snmp_collector = MagicMock()
        snmp_collector._pysnmp_available = False

        # Track concurrency inside the mock
        async def mock_query_sys_oid(ip, creds):
            nonlocal concurrent_count, peak_concurrent
            concurrent_count += 1
            if concurrent_count > peak_concurrent:
                peak_concurrent = concurrent_count
            await asyncio.sleep(0.01)  # Simulate network delay
            concurrent_count -= 1
            return None  # No device found

        snmp_collector.query_sys_object_id = AsyncMock(side_effect=mock_query_sys_oid)

        engine = AutodiscoveryEngine(
            profile_loader=profile_loader,
            snmp_collector=snmp_collector,
            max_concurrent=max_concurrent,
        )

        config = _make_config("10.0.0.0/26")  # 62 hosts
        await engine.scan_network(config)

        # Peak concurrency should never exceed the limit
        assert peak_concurrent <= max_concurrent, (
            f"Peak concurrency {peak_concurrent} exceeded limit {max_concurrent}"
        )
        # And should actually use concurrency (more than 1 if there are enough hosts)
        assert peak_concurrent > 1, "Should have had some concurrency"

    @pytest.mark.asyncio
    async def test_semaphore_uses_env_var(self, monkeypatch):
        """DISCOVERY_MAX_CONCURRENT_PROBES env var should control the semaphore limit."""
        monkeypatch.setenv("DISCOVERY_MAX_CONCURRENT_PROBES", "10")

        profile_loader = MagicMock()
        snmp_collector = MagicMock()

        engine = AutodiscoveryEngine(
            profile_loader=profile_loader,
            snmp_collector=snmp_collector,
        )

        assert engine._max_concurrent == 10

    @pytest.mark.asyncio
    async def test_default_concurrency_is_50(self):
        """Default concurrency should be 50 when no env var or arg is given."""
        # Ensure env var is not set
        os.environ.pop("DISCOVERY_MAX_CONCURRENT_PROBES", None)

        profile_loader = MagicMock()
        snmp_collector = MagicMock()

        engine = AutodiscoveryEngine(
            profile_loader=profile_loader,
            snmp_collector=snmp_collector,
        )

        assert engine._max_concurrent == 50

    @pytest.mark.asyncio
    async def test_constructor_arg_overrides_env_var(self, monkeypatch):
        """Explicit max_concurrent argument should take priority over env var."""
        monkeypatch.setenv("DISCOVERY_MAX_CONCURRENT_PROBES", "100")

        profile_loader = MagicMock()
        snmp_collector = MagicMock()

        engine = AutodiscoveryEngine(
            profile_loader=profile_loader,
            snmp_collector=snmp_collector,
            max_concurrent=25,
        )

        assert engine._max_concurrent == 25

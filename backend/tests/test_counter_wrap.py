"""Tests for 32-bit and 64-bit counter wraparound handling in SNMPCollector."""

import time
from unittest.mock import AsyncMock
import pytest

from src.network.snmp_collector import SNMPCollector


@pytest.fixture
def collector():
    metrics_store = AsyncMock()
    return SNMPCollector(metrics_store)


# ── _unwrap_counter unit tests ─────────────────────────────────

class TestUnwrapCounter:
    def test_no_wrap_32bit(self):
        """Normal delta with no wraparound for 32-bit counter."""
        delta = SNMPCollector._unwrap_counter(200, 100, is_64bit=False)
        assert delta == 100

    def test_no_wrap_64bit(self):
        """Normal delta with no wraparound for 64-bit counter."""
        delta = SNMPCollector._unwrap_counter(500, 300, is_64bit=True)
        assert delta == 200

    def test_wrap_32bit(self):
        """32-bit counter wraps: current < previous, add 2**32."""
        previous = 2**32 - 100
        current = 50
        delta = SNMPCollector._unwrap_counter(current, previous, is_64bit=False)
        assert delta == 150  # (50 - (2**32 - 100)) + 2**32 = 150

    def test_wrap_64bit(self):
        """64-bit counter wraps: current < previous, add 2**64."""
        previous = 2**64 - 500
        current = 200
        delta = SNMPCollector._unwrap_counter(current, previous, is_64bit=True)
        assert delta == 700  # (200 - (2**64 - 500)) + 2**64 = 700

    def test_zero_delta(self):
        """Same value produces zero delta (no wrap)."""
        delta = SNMPCollector._unwrap_counter(1000, 1000, is_64bit=False)
        assert delta == 0

    def test_wrap_32bit_exact_boundary(self):
        """Counter wraps from exactly 2**32-1 to 0."""
        delta = SNMPCollector._unwrap_counter(0, 2**32 - 1, is_64bit=False)
        assert delta == 1

    def test_wrap_64bit_exact_boundary(self):
        """Counter wraps from exactly 2**64-1 to 0."""
        delta = SNMPCollector._unwrap_counter(0, 2**64 - 1, is_64bit=True)
        assert delta == 1


# ── _compute_rates integration tests ──────────────────────────

class TestComputeRatesWrap:
    def test_32bit_wrap_in_rates(self, collector, monkeypatch):
        """_compute_rates correctly handles 32-bit counter wrap."""
        device = "sw-core-01"
        if_idx = 1
        t = time.time()

        # Seed previous counters (near max 32-bit value)
        monkeypatch.setattr(time, "time", lambda: t)
        prev = {"ifInOctets": 2**32 - 1000, "ifOutOctets": 2**32 - 500, "ifSpeed": 1_000_000_000}
        result = collector._compute_rates(device, if_idx, prev)
        assert result is None  # First call returns None

        # Second call: counters wrapped around
        monkeypatch.setattr(time, "time", lambda: t + 10)
        curr = {"ifInOctets": 500, "ifOutOctets": 200, "ifSpeed": 1_000_000_000}
        result = collector._compute_rates(device, if_idx, curr)

        assert result is not None
        expected_delta_in = 1500  # (500 - (2**32 - 1000)) + 2**32
        expected_delta_out = 700
        expected_bps_in = (expected_delta_in * 8) / 10
        expected_bps_out = (expected_delta_out * 8) / 10
        assert abs(result["bps_in"] - expected_bps_in) < 0.01
        assert abs(result["bps_out"] - expected_bps_out) < 0.01

    def test_64bit_wrap_in_rates(self, collector, monkeypatch):
        """_compute_rates correctly handles 64-bit HC counter wrap."""
        device = "sw-core-01"
        if_idx = 2
        t = time.time()

        # Seed previous counters with HC (64-bit) values near max
        monkeypatch.setattr(time, "time", lambda: t)
        prev = {
            "ifHCInOctets": 2**64 - 2000,
            "ifHCOutOctets": 2**64 - 3000,
            "ifSpeed": 10_000_000_000,
        }
        result = collector._compute_rates(device, if_idx, prev)
        assert result is None

        # Second call: counters wrapped
        monkeypatch.setattr(time, "time", lambda: t + 5)
        curr = {
            "ifHCInOctets": 1000,
            "ifHCOutOctets": 500,
            "ifSpeed": 10_000_000_000,
        }
        result = collector._compute_rates(device, if_idx, curr)
        assert result is not None
        expected_delta_in = 3000
        expected_delta_out = 3500
        expected_bps_in = (expected_delta_in * 8) / 5
        expected_bps_out = (expected_delta_out * 8) / 5
        assert abs(result["bps_in"] - expected_bps_in) < 0.01
        assert abs(result["bps_out"] - expected_bps_out) < 0.01

    def test_no_wrap_32bit_rates(self, collector, monkeypatch):
        """_compute_rates works normally without wrap for 32-bit counters."""
        device = "sw-core-01"
        if_idx = 3
        t = time.time()

        monkeypatch.setattr(time, "time", lambda: t)
        prev = {"ifInOctets": 1000, "ifOutOctets": 2000, "ifSpeed": 1_000_000_000}
        collector._compute_rates(device, if_idx, prev)

        monkeypatch.setattr(time, "time", lambda: t + 10)
        curr = {"ifInOctets": 5000, "ifOutOctets": 6000, "ifSpeed": 1_000_000_000}
        result = collector._compute_rates(device, if_idx, curr)

        assert result is not None
        assert abs(result["bps_in"] - (4000 * 8 / 10)) < 0.01
        assert abs(result["bps_out"] - (4000 * 8 / 10)) < 0.01

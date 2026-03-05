"""Regression test: semaphore must be released even when icmplib is unavailable."""
import unittest.mock as mock

import pytest


def test_semaphore_released_when_icmplib_missing():
    """Call traceroute_probe 4+ times with HAS_ICMPLIB=False.
    If semaphore leaks, the 4th call returns 'Rate limit'.
    If fixed, ALL calls return 'icmplib not available' (never rate-limited).
    """
    import src.agents.network.traceroute_probe as tp

    # Reset semaphore to a fresh state
    tp._semaphore = __import__("threading").Semaphore(tp._MAX_CONCURRENT)

    with mock.patch.object(tp, "HAS_ICMPLIB", False):
        results = []
        for _ in range(tp._MAX_CONCURRENT + 2):  # 5 calls with max=3
            r = tp.traceroute_probe({"dst_ip": "10.0.0.1"})
            results.append(r)

    # NONE of the results should say "Rate limit"
    for i, r in enumerate(results):
        details = [e["detail"] for e in r.get("evidence", [])]
        assert not any("Rate limit" in d for d in details), (
            f"Call {i} was rate-limited — semaphore leaked"
        )
        # All should report icmplib not available
        assert any("icmplib" in d for d in details), (
            f"Call {i} didn't report icmplib unavailable"
        )


def test_semaphore_released_when_no_dst_ip():
    """Early return for missing dst_ip must not leak semaphore."""
    import src.agents.network.traceroute_probe as tp

    tp._semaphore = __import__("threading").Semaphore(tp._MAX_CONCURRENT)

    for _ in range(tp._MAX_CONCURRENT + 2):
        r = tp.traceroute_probe({"dst_ip": ""})
        details = [e["detail"] for e in r.get("evidence", [])]
        assert any("No destination" in d for d in details)

    # One more call with a real IP should NOT be rate-limited
    with mock.patch.object(tp, "HAS_ICMPLIB", False):
        r = tp.traceroute_probe({"dst_ip": "10.0.0.1"})
        details = [e["detail"] for e in r.get("evidence", [])]
        assert not any("Rate limit" in d for d in details)

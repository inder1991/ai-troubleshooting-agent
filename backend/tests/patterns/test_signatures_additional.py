"""Task 4.2 — 7 additional signature patterns."""
from __future__ import annotations

from src.patterns import (
    CERT_EXPIRY,
    DNS_FLAP,
    HOT_KEY,
    IMAGE_PULL_BACKOFF,
    LIBRARY,
    NETWORK_POLICY_DENIAL,
    QUOTA_EXHAUSTION,
    THREAD_POOL_EXHAUSTION,
    Signal,
)


def sig(kind: str, t: float, service: str = "payment") -> Signal:
    return Signal(kind=kind, t=t, service=service)


class TestCertExpiry:
    def test_matches(self):
        m = CERT_EXPIRY.matches([
            sig("cert_expiry", t=0),
            sig("error_rate_spike", t=60),
        ])
        assert m.matched is True
        assert m.confidence >= 0.85

    def test_rejects_when_error_precedes_expiry(self):
        m = CERT_EXPIRY.matches([
            sig("error_rate_spike", t=0),
            sig("cert_expiry", t=60),
        ])
        assert m.matched is False


class TestHotKey:
    def test_matches(self):
        m = HOT_KEY.matches([
            sig("hot_key", t=0),
            sig("latency_spike", t=60),
        ])
        assert m.matched is True


class TestThreadPoolExhaustion:
    def test_matches(self):
        m = THREAD_POOL_EXHAUSTION.matches([
            sig("thread_pool_exhausted", t=0),
            sig("latency_spike", t=30),
        ])
        assert m.matched is True

    def test_rejects_without_saturation(self):
        m = THREAD_POOL_EXHAUSTION.matches([sig("latency_spike", t=0)])
        assert m.matched is False


class TestDnsFlap:
    def test_matches(self):
        m = DNS_FLAP.matches([
            sig("dns_failure", t=0),
            sig("error_rate_spike", t=120),
        ])
        assert m.matched is True


class TestImagePullBackoff:
    def test_matches_even_without_temporal_rule(self):
        # No temporal constraints — just presence.
        m = IMAGE_PULL_BACKOFF.matches([sig("image_pull_backoff", t=0)])
        assert m.matched is True
        assert m.confidence >= 0.85


class TestQuotaExhaustion:
    def test_matches(self):
        m = QUOTA_EXHAUSTION.matches([sig("quota_exceeded", t=0)])
        assert m.matched is True


class TestNetworkPolicyDenial:
    def test_matches(self):
        m = NETWORK_POLICY_DENIAL.matches([
            sig("network_policy_denial", t=0),
            sig("connection_refused", t=10),
        ])
        assert m.matched is True


class TestLibraryCompleteness:
    def test_library_has_ten_patterns(self):
        assert len(LIBRARY) == 10

    def test_all_names_unique(self):
        names = [p.name for p in LIBRARY]
        assert len(set(names)) == len(names)

    def test_all_have_non_empty_summary_template(self):
        for p in LIBRARY:
            assert p.summary_template.strip(), p.name

    def test_all_have_confidence_floor_in_0_1(self):
        for p in LIBRARY:
            assert 0.0 < p.confidence_floor <= 1.0, p.name

    def test_all_have_suggested_remediation(self):
        for p in LIBRARY:
            assert p.suggested_remediation and p.suggested_remediation.strip(), p.name

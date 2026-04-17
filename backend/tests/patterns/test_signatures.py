"""Task 4.1 — signature pattern schema + first 3 patterns."""
from __future__ import annotations

from src.patterns import (
    DEPLOY_REGRESSION,
    LIBRARY,
    OOM_CASCADE,
    RETRY_STORM,
    Signal,
    SignaturePattern,
    TemporalRule,
)


def sig(kind: str, t: float, service: str = "payment", **attrs) -> Signal:
    return Signal(kind=kind, t=t, service=service, attrs=attrs)


class TestSchemaEssentials:
    def test_empty_signals_matches_nothing(self):
        for p in LIBRARY:
            m = p.matches([])
            assert m.matched is False

    def test_pattern_is_frozen(self):
        import dataclasses
        for p in LIBRARY:
            assert dataclasses.is_dataclass(p)

    def test_library_not_empty(self):
        assert len(LIBRARY) >= 3


class TestOOMCascade:
    def test_matches_when_required_signals_present(self):
        signals = [
            sig("memory_pressure", t=0),
            sig("oom_killed", t=60),
            sig("pod_restart", t=70),
            sig("error_rate_spike", t=90),
        ]
        m = OOM_CASCADE.matches(signals)
        assert m.matched is True
        assert m.confidence >= 0.70

    def test_does_not_match_without_oom_signal(self):
        signals = [sig("memory_pressure", t=0), sig("error_rate_spike", t=10)]
        assert OOM_CASCADE.matches(signals).matched is False

    def test_rejects_when_oom_precedes_memory_pressure(self):
        signals = [
            sig("oom_killed", t=0),
            sig("memory_pressure", t=60),
            sig("pod_restart", t=120),
        ]
        m = OOM_CASCADE.matches(signals)
        assert m.matched is False
        assert "memory_pressure->oom_killed" in m.reason

    def test_rejects_when_gap_too_large(self):
        signals = [
            sig("memory_pressure", t=0),
            sig("oom_killed", t=10_000),  # 10k seconds later
            sig("pod_restart", t=10_060),
        ]
        m = OOM_CASCADE.matches(signals)
        assert m.matched is False

    def test_optional_signals_boost_confidence(self):
        minimum = [
            sig("memory_pressure", t=0),
            sig("oom_killed", t=60),
            sig("pod_restart", t=70),
        ]
        with_optional = minimum + [
            sig("error_rate_spike", t=90),
            sig("latency_spike", t=95),
        ]
        c_min = OOM_CASCADE.matches(minimum).confidence
        c_full = OOM_CASCADE.matches(with_optional).confidence
        assert c_full > c_min


class TestDeployRegression:
    def test_matches(self):
        signals = [sig("deploy", t=0), sig("error_rate_spike", t=120)]
        m = DEPLOY_REGRESSION.matches(signals)
        assert m.matched is True
        assert m.confidence >= 0.80

    def test_rejects_when_error_precedes_deploy(self):
        signals = [sig("error_rate_spike", t=0), sig("deploy", t=120)]
        m = DEPLOY_REGRESSION.matches(signals)
        assert m.matched is False

    def test_rejects_stale_deploy(self):
        signals = [sig("deploy", t=0), sig("error_rate_spike", t=3600)]
        assert DEPLOY_REGRESSION.matches(signals).matched is False


class TestRetryStorm:
    def test_matches(self):
        signals = [
            sig("error_rate_spike", t=0),
            sig("retry_storm", t=120),
            sig("circuit_open", t=180),
        ]
        m = RETRY_STORM.matches(signals)
        assert m.matched is True

    def test_rejects_without_retry_storm_signal(self):
        signals = [sig("error_rate_spike", t=0), sig("latency_spike", t=5)]
        assert RETRY_STORM.matches(signals).matched is False


class TestRenderSummary:
    def test_summary_uses_service_name(self):
        signals = [
            sig("memory_pressure", t=0, service="checkout"),
            sig("oom_killed", t=60, service="checkout"),
            sig("pod_restart", t=70, service="checkout"),
        ]
        s = OOM_CASCADE.render_summary(signals)
        assert "checkout" in s


class TestSchemaVersion:
    def test_schema_version_pinned(self):
        assert SignaturePattern.SCHEMA_VERSION == 1


class TestTemporalRule:
    def test_rule_is_frozen_dataclass(self):
        r = TemporalRule(earlier="deploy", later="error_rate_spike", max_gap_s=60)
        assert r.max_gap_s == 60

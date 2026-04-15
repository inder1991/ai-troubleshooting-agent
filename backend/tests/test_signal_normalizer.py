"""Tests for signal normalizer — derived signals with baseline comparison."""

from __future__ import annotations

import pytest

from src.models.hypothesis import EvidenceSignal
from src.hypothesis.signal_normalizer import SignalNormalizer


def _make_metric_signal(
    metric_name: str,
    value: float,
    baseline: float | None = None,
    labels: dict | None = None,
) -> EvidenceSignal:
    """Helper to build a raw metric signal."""
    raw = {"metric_name": metric_name, "value": value, "labels": labels or {}}
    if baseline is not None:
        raw["baseline"] = baseline
    return EvidenceSignal(
        signal_id="test_met_0",
        signal_type="metric",
        signal_name="raw_metric",
        raw_data=raw,
        source_agent="metrics_agent",
    )


def _make_k8s_signal(reason: str, event_type: str = "Warning") -> EvidenceSignal:
    """Helper to build a raw k8s event signal."""
    return EvidenceSignal(
        signal_id="test_k8s_0",
        signal_type="k8s",
        signal_name="raw_k8s_event",
        raw_data={"reason": reason, "type": event_type},
        source_agent="k8s_agent",
    )


class TestMetricNormalization:
    """Tests for _normalize_metric."""

    def setup_method(self):
        self.normalizer = SignalNormalizer()

    def test_working_set_memory_high(self):
        sig = _make_metric_signal("container_memory_working_set_bytes", 800_000_000, baseline=200_000_000)
        result = self.normalizer.normalize(sig)
        assert result is not None
        assert result.signal_name == "high_memory_usage"
        assert result.strength > 0.5

    def test_memory_cache_skipped(self):
        sig = _make_metric_signal("container_memory_cache", 100_000)
        result = self.normalizer.normalize(sig)
        assert result is None

    def test_memory_requested_skipped(self):
        sig = _make_metric_signal("kube_pod_container_resource_requests", 256_000_000)
        result = self.normalizer.normalize(sig)
        assert result is None

    def test_strength_from_baseline_ratio(self):
        # value=3.2x baseline → ratio=3.2, deviation=2.2, strength = min(1.0, 2.2/4.0) = 0.55
        sig = _make_metric_signal("container_memory_working_set_bytes", 320, baseline=100)
        result = self.normalizer.normalize(sig)
        assert result is not None
        assert abs(result.strength - 0.55) < 0.01

    def test_no_baseline_defaults_moderate(self):
        sig = _make_metric_signal("container_memory_working_set_bytes", 500_000_000)
        result = self.normalizer.normalize(sig)
        assert result is not None
        assert result.strength == 0.5

    def test_low_deviation_skipped(self):
        # 1.04x baseline → below MIN_DEVIATION_RATIO of 1.2
        sig = _make_metric_signal("container_memory_working_set_bytes", 104, baseline=100)
        result = self.normalizer.normalize(sig)
        assert result is None

    def test_cpu_high(self):
        sig = _make_metric_signal("container_cpu_usage_seconds_total", 0.95, baseline=0.3)
        result = self.normalizer.normalize(sig)
        assert result is not None
        assert result.signal_name == "high_cpu"

    def test_unrecognized_metric_skipped(self):
        sig = _make_metric_signal("some_totally_unknown_metric", 42.0, baseline=10.0)
        result = self.normalizer.normalize(sig)
        assert result is None


class TestK8sNormalization:
    """Tests for _normalize_k8s."""

    def setup_method(self):
        self.normalizer = SignalNormalizer()

    def test_oom_killed(self):
        sig = _make_k8s_signal("OOMKilled")
        result = self.normalizer.normalize(sig)
        assert result is not None
        assert result.signal_name == "oom_kill"
        assert result.strength == 1.0

    def test_crashloop(self):
        sig = _make_k8s_signal("CrashLoopBackOff")
        result = self.normalizer.normalize(sig)
        assert result is not None
        assert result.signal_name == "crashloop_backoff"
        assert result.strength == 0.9

    def test_normal_event_skipped(self):
        sig = _make_k8s_signal("OOMKilled", event_type="Normal")
        result = self.normalizer.normalize(sig)
        assert result is None

    def test_unknown_reason_passes_through(self):
        sig = _make_k8s_signal("SomeNewReason")
        result = self.normalizer.normalize(sig)
        assert result is not None
        assert result.signal_name == "raw_k8s_event"  # unchanged


class TestPassthrough:
    """Tests for already-normalized and non-metric/k8s signals."""

    def setup_method(self):
        self.normalizer = SignalNormalizer()

    def test_already_normalized_passes(self):
        sig = EvidenceSignal(
            signal_id="test_0",
            signal_type="k8s",
            signal_name="oom_kill",
            raw_data={},
            source_agent="k8s_agent",
            strength=1.0,
        )
        result = self.normalizer.normalize(sig)
        assert result is sig  # exact same object

    def test_log_signal_passes(self):
        sig = EvidenceSignal(
            signal_id="test_log_0",
            signal_type="log",
            signal_name="raw_log_pattern",
            raw_data={},
            source_agent="log_agent",
        )
        result = self.normalizer.normalize(sig)
        assert result is sig

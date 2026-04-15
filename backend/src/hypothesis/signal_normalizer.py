"""Signal normalizer — refines raw signals into meaningful derived signals.

Signals are DERIVED from data analysis (baselines, thresholds, labels),
not string-matched on metric names alone. The normalizer applies baseline
deviation ratios to compute signal strength rather than using fixed values.
"""

from __future__ import annotations

from typing import Optional

from src.models.hypothesis import EvidenceSignal


class SignalNormalizer:
    """Normalize raw signals into meaningful derived signals."""

    # Metric name patterns -> signal names (substring match on metric_name)
    METRIC_CLASSIFIERS = {
        "memory_working_set": "high_memory_usage",
        "memory_rss": "high_memory_usage",
        "cpu_usage": "high_cpu",
        "cpu_throttl": "cpu_throttling",
        "fs_usage": "disk_usage_high",
        "fs_writes": "disk_usage_high",
        "network_receive_errors": "network_errors",
        "network_transmit_errors": "network_errors",
        "requests_total": "error_rate_spike",  # only if error-related labels
        "http_server_duration": "latency_spike",
        "response_time": "latency_spike",
    }

    # Skip these metrics -- they're config/non-actionable, not signals
    SKIP_METRICS = [
        "memory_cache",
        "resource_requests",
        "resource_limits",
        "memory_mapped_file",
        "kube_pod_info",
        "kube_pod_labels",
        "kube_pod_status_phase",
        "kube_deployment_spec",
    ]

    # K8s event reason -> (signal_name, strength) or None to skip
    K8S_EVENT_MAP = {
        "OOMKilled": ("oom_kill", 1.0),
        "OOMKilling": ("oom_kill", 1.0),
        "CrashLoopBackOff": ("crashloop_backoff", 0.9),
        "BackOff": ("crashloop_backoff", 0.8),
        "FailedScheduling": ("scheduling_failure", 0.7),
        "Unhealthy": ("probe_failure", 0.6),
        "ImagePullBackOff": ("image_pull_failure", 0.8),
        "ErrImagePull": ("image_pull_failure", 0.8),
        "Evicted": ("eviction", 0.7),
        "FailedMount": ("volume_mount_failure", 0.7),
        # Skip non-error events
        "Preempted": None,
        "Scheduled": None,
        "Pulled": None,
        "Created": None,
        "Started": None,
        "Killing": None,
    }

    # Minimum baseline deviation ratio to consider meaningful
    MIN_DEVIATION_RATIO = 1.2  # 20% above baseline

    def normalize(self, signal: EvidenceSignal) -> Optional[EvidenceSignal]:
        """Normalize a raw signal into a meaningful derived signal.

        Returns None if signal is not meaningful (skip metrics, normal events,
        low deviation).
        Returns the signal unchanged if already meaningfully named (not
        prefixed with ``raw_``).
        """
        # Already normalized? Pass through.
        if not signal.signal_name.startswith("raw_"):
            return signal

        if signal.signal_type == "metric":
            return self._normalize_metric(signal)
        elif signal.signal_type == "k8s":
            return self._normalize_k8s(signal)
        else:
            return signal  # other types pass through

    # ------------------------------------------------------------------
    # Metric normalization
    # ------------------------------------------------------------------

    def _normalize_metric(self, signal: EvidenceSignal) -> Optional[EvidenceSignal]:
        """Normalize a metric signal.

        1. Check SKIP_METRICS -- return None if matches
        2. Match metric_name against METRIC_CLASSIFIERS
        3. Compute strength from baseline ratio:
           - If baseline available: strength = min(1.0, (current/baseline - 1.0) / 4.0)
           - If ratio < MIN_DEVIATION_RATIO (1.2): return None (not meaningful)
           - If no baseline: strength = 0.5 (moderate default)
        4. Return new EvidenceSignal with derived signal_name and computed strength
        """
        metric_name: str = signal.raw_data.get("metric_name", "")
        value: float = signal.raw_data.get("value", 0.0)
        baseline: float | None = signal.raw_data.get("baseline")

        # 1. Skip non-actionable metrics
        for skip_pattern in self.SKIP_METRICS:
            if skip_pattern in metric_name:
                return None

        # 2. Classify metric
        derived_name: str | None = None
        for pattern, name in self.METRIC_CLASSIFIERS.items():
            if pattern in metric_name:
                derived_name = name
                break

        if derived_name is None:
            return None  # unrecognized metric

        # 3. Compute strength from baseline
        if baseline is not None and baseline > 0:
            ratio = value / baseline
            if ratio < self.MIN_DEVIATION_RATIO:
                return None  # not meaningful deviation
            strength = min(1.0, (ratio - 1.0) / 4.0)
        else:
            strength = 0.5  # moderate default when no baseline

        # 4. Build derived signal
        return EvidenceSignal(
            signal_id=signal.signal_id,
            signal_type=signal.signal_type,
            signal_name=derived_name,
            raw_data=signal.raw_data,
            source_agent=signal.source_agent,
            timestamp=signal.timestamp,
            strength=strength,
            freshness=signal.freshness,
        )

    # ------------------------------------------------------------------
    # K8s event normalization
    # ------------------------------------------------------------------

    def _normalize_k8s(self, signal: EvidenceSignal) -> Optional[EvidenceSignal]:
        """Normalize a K8s event signal.

        1. Skip Normal-type events
        2. Look up reason in K8S_EVENT_MAP
        3. If mapped to None -> skip (return None)
        4. If not found -> return signal as-is (unknown event type)
        5. If found -> return new signal with mapped name and strength
        """
        raw = signal.raw_data
        event_type = raw.get("type", "Warning")
        reason = raw.get("reason", "")

        # 1. Skip Normal events
        if event_type == "Normal":
            return None

        # 2-3. Look up reason
        if reason in self.K8S_EVENT_MAP:
            mapping = self.K8S_EVENT_MAP[reason]
            if mapping is None:
                return None  # explicitly skipped event
            mapped_name, mapped_strength = mapping
            return EvidenceSignal(
                signal_id=signal.signal_id,
                signal_type=signal.signal_type,
                signal_name=mapped_name,
                raw_data=signal.raw_data,
                source_agent=signal.source_agent,
                timestamp=signal.timestamp,
                strength=mapped_strength,
                freshness=signal.freshness,
            )

        # 4. Unknown reason -- pass through unchanged
        return signal

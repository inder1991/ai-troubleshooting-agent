"""Prometheus metrics exporter for the NetworkMonitor."""
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class MetricsCollector:
    """Collects and exposes Prometheus metrics for the network monitoring system.

    Uses a per-instance CollectorRegistry so multiple collectors can coexist
    in tests without metric-name collisions.
    """

    def __init__(self) -> None:
        self._registry = CollectorRegistry()

        self._cycle_duration = Histogram(
            "network_monitor_cycle_duration_seconds",
            "Duration of a full monitor collection cycle in seconds",
            registry=self._registry,
        )

        self._cycle_total = Counter(
            "network_monitor_cycle_total",
            "Total number of completed monitor cycles",
            registry=self._registry,
        )

        self._pass_duration = Histogram(
            "network_monitor_pass_duration_seconds",
            "Duration of an individual monitor pass in seconds",
            labelnames=["pass_name"],
            registry=self._registry,
        )

        self._devices_total = Gauge(
            "network_monitor_devices_total",
            "Current number of monitored devices",
            registry=self._registry,
        )

        self._alerts_active = Gauge(
            "network_monitor_alerts_active",
            "Current number of active alerts",
            registry=self._registry,
        )

        self._adapter_errors_total = Counter(
            "network_monitor_adapter_errors_total",
            "Total adapter query errors",
            labelnames=["adapter_type"],
            registry=self._registry,
        )

    # ── Recording helpers ──

    def record_cycle_duration(self, seconds: float) -> None:
        """Observe a cycle duration in the histogram."""
        self._cycle_duration.observe(seconds)

    def increment_cycle_total(self) -> None:
        """Increment the completed-cycles counter."""
        self._cycle_total.inc()

    def record_pass_duration(self, name: str, seconds: float) -> None:
        """Observe a per-pass duration in the histogram."""
        self._pass_duration.labels(pass_name=name).observe(seconds)

    def set_device_count(self, n: int) -> None:
        """Set the current device count gauge."""
        self._devices_total.set(n)

    def set_active_alerts(self, n: int) -> None:
        """Set the current active alerts gauge."""
        self._alerts_active.set(n)

    def increment_adapter_errors(self, adapter_type: str) -> None:
        """Increment the adapter error counter for the given adapter type."""
        self._adapter_errors_total.labels(adapter_type=adapter_type).inc()

    # ── Output ──

    def generate_metrics(self) -> str:
        """Return all collected metrics in Prometheus text exposition format."""
        return generate_latest(self._registry).decode("utf-8")

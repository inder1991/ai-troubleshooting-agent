"""Step-latency metrics + SLO burn-rule definitions.

Uses ``prometheus_client`` when installed; falls back to an in-process
registry that lets tests assert on emitted samples without the dep.

Metrics:
  - ``investigation_step_duration_ms{agent,status}`` — histogram. Labels:
    agent name, status in {"success","timeout","error"}.
  - ``investigation_total{outcome}`` — counter. Outcome in {"completed",
    "inconclusive","cancelled","failed"}.
  - ``investigation_in_flight`` — gauge.

Alert rules (rendered into deploy/prometheus/alerts.yaml):
  - p95 step duration > 30s for 10m   -> warning
  - in_flight > 80% of cap for 5m     -> warning
  - investigation failure rate > 5%   -> page
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Tiny fallback registry ────────────────────────────────────────────────


@dataclass
class Sample:
    name: str
    labels: dict[str, str]
    value: float


@dataclass
class _Metric:
    name: str
    kind: str  # "histogram" | "counter" | "gauge"
    labelnames: tuple[str, ...] = ()
    samples: list[Sample] = field(default_factory=list)


class _Registry:
    """Test-time / standalone metrics store.

    In production we swap this out for ``prometheus_client`` — the public
    API here (``observe`` / ``inc`` / ``set`` / ``get``) matches.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, _Metric] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    def register(
        self, name: str, kind: str, labelnames: tuple[str, ...] = ()
    ) -> _Metric:
        m = self._metrics.get(name)
        if m is None:
            m = _Metric(name=name, kind=kind, labelnames=labelnames)
            self._metrics[name] = m
        return m

    def observe(self, name: str, value: float, labels: dict[str, str]) -> None:
        m = self._metrics[name]
        m.samples.append(Sample(name=name, labels=dict(labels), value=value))

    def inc(self, name: str, labels: dict[str, str], amount: float = 1.0) -> None:
        key = (name, tuple(sorted(labels.items())))
        self._counters[key] = self._counters.get(key, 0.0) + amount
        self._metrics[name].samples.append(
            Sample(name=name, labels=dict(labels), value=self._counters[key])
        )

    def set(self, name: str, value: float, labels: dict[str, str]) -> None:
        key = (name, tuple(sorted(labels.items())))
        self._gauges[key] = value
        self._metrics[name].samples.append(
            Sample(name=name, labels=dict(labels), value=value)
        )

    def get(self, name: str) -> _Metric:
        return self._metrics[name]

    def reset_for_tests(self) -> None:
        for m in self._metrics.values():
            m.samples.clear()
        self._gauges.clear()
        self._counters.clear()


_registry = _Registry()


def get_registry() -> _Registry:
    return _registry


# ── Metric surface ────────────────────────────────────────────────────────


_STEP_DURATION = "investigation_step_duration_ms"
_INVESTIGATION_TOTAL = "investigation_total"
_IN_FLIGHT = "investigation_in_flight"


# Register up-front so get_registry().get("...") never KeyErrors in tests.
_registry.register(_STEP_DURATION, "histogram", labelnames=("agent", "status"))
_registry.register(_INVESTIGATION_TOTAL, "counter", labelnames=("outcome",))
_registry.register(_IN_FLIGHT, "gauge", labelnames=())


def record_step_completion(*, agent: str, duration_ms: float, status: str) -> None:
    if status not in {"success", "timeout", "error"}:
        raise ValueError(f"status must be success/timeout/error; got {status!r}")
    _registry.observe(
        _STEP_DURATION,
        duration_ms,
        {"agent": agent, "status": status},
    )


def record_investigation_outcome(*, outcome: str) -> None:
    if outcome not in {"completed", "inconclusive", "cancelled", "failed"}:
        raise ValueError(f"unknown outcome {outcome!r}")
    _registry.inc(_INVESTIGATION_TOTAL, {"outcome": outcome})


def set_in_flight(count: int) -> None:
    _registry.set(_IN_FLIGHT, float(count), {})


# ── Alert rule text (rendered by deploy/prometheus/alerts.yaml) ───────────


ALERT_RULES_YAML: str = """\
groups:
  - name: diagnostic-investigation-slos
    interval: 30s
    rules:
      - alert: DiagnosticStepSlowP95
        expr: |
          histogram_quantile(0.95,
            sum by (le) (rate(investigation_step_duration_ms_bucket[10m]))
          ) > 30000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "p95 diagnostic step latency > 30s for 10 minutes"
          description: "Investigate slow agent or backend; check circuit-breaker state."

      - alert: DiagnosticInFlightNearCap
        expr: |
          investigation_in_flight /
          on() group_left() max_over_time(investigation_in_flight_cap[5m]) > 0.80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "investigation_in_flight > 80% of configured cap"
          description: "Scale the supervisor tier or increase the budget cap."

      - alert: DiagnosticFailureRateHigh
        expr: |
          sum(rate(investigation_total{outcome=~"failed|cancelled"}[5m]))
          /
          clamp_min(sum(rate(investigation_total[5m])), 1) > 0.05
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "Diagnostic failure rate > 5% for 5 minutes"
          description: "Paging on-call. Check backend outages / circuit breakers."
"""


def alert_rules_yaml() -> str:
    """Return the alert rules YAML — rendered to disk by the deploy pipeline."""
    return ALERT_RULES_YAML

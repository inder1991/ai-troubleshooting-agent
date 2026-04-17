"""Stage A.2 — state-to-Signal extraction."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.agents.orchestration.signal_extractor import extract_signals_from_state


@dataclass
class StubPin:
    claim: str = ""
    raw_output: str = ""
    service: Optional[str] = None
    source_agent: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class StubPod:
    oom_killed: bool = False
    crash_loop: bool = False
    service: Optional[str] = None
    namespace: Optional[str] = None


@dataclass
class StubK8s:
    pod_statuses: list[StubPod] = field(default_factory=list)


@dataclass
class StubAnomaly:
    metric_name: str
    service: Optional[str] = None


@dataclass
class StubMetrics:
    anomalies: list[StubAnomaly] = field(default_factory=list)


@dataclass
class StubState:
    evidence_pins: list[Any] = field(default_factory=list)
    k8s_analysis: Optional[StubK8s] = None
    metrics_analysis: Optional[StubMetrics] = None
    change_analysis: Optional[Any] = None
    patient_zero: Optional[Any] = None


class TestKeywordMatching:
    def test_oomkilled_claim_maps_to_oom_killed(self):
        s = StubState(evidence_pins=[StubPin(claim="Pod OOMKilled")])
        sigs = extract_signals_from_state(s)
        kinds = {sig.kind for sig in sigs}
        assert "oom_killed" in kinds

    def test_deploy_claim_maps_to_deploy(self):
        s = StubState(evidence_pins=[StubPin(claim="Deploy of v2.3 rolled out")])
        sigs = extract_signals_from_state(s)
        assert "deploy" in {sig.kind for sig in sigs}

    def test_error_rate_spike_claim(self):
        s = StubState(evidence_pins=[StubPin(claim="error rate spike from 0.1% to 15%")])
        sigs = extract_signals_from_state(s)
        assert "error_rate_spike" in {sig.kind for sig in sigs}

    def test_multiple_keywords_in_one_claim(self):
        s = StubState(evidence_pins=[StubPin(claim="OOMKilled followed by CrashLoopBackOff")])
        sigs = extract_signals_from_state(s)
        kinds = {sig.kind for sig in sigs}
        assert {"oom_killed", "pod_restart"} <= kinds

    def test_no_match_returns_empty(self):
        s = StubState(evidence_pins=[StubPin(claim="everything is normal")])
        assert extract_signals_from_state(s) == []


class TestK8sAnalysis:
    def test_oom_killed_pod_adds_signal(self):
        s = StubState(
            k8s_analysis=StubK8s(
                pod_statuses=[StubPod(oom_killed=True, service="payment")]
            ),
        )
        sigs = extract_signals_from_state(s)
        assert any(sig.kind == "oom_killed" and sig.service == "payment" for sig in sigs)

    def test_crashloop_pod_adds_pod_restart(self):
        s = StubState(
            k8s_analysis=StubK8s(
                pod_statuses=[StubPod(crash_loop=True, service="checkout")]
            ),
        )
        sigs = extract_signals_from_state(s)
        assert any(sig.kind == "pod_restart" for sig in sigs)


class TestMetricsAnalysis:
    def test_error_metric_maps_to_error_rate_spike(self):
        s = StubState(
            metrics_analysis=StubMetrics(
                anomalies=[StubAnomaly(metric_name="http_5xx_rate", service="payment")]
            ),
        )
        sigs = extract_signals_from_state(s)
        assert any(sig.kind == "error_rate_spike" for sig in sigs)

    def test_latency_metric_maps_to_latency_spike(self):
        s = StubState(
            metrics_analysis=StubMetrics(
                anomalies=[StubAnomaly(metric_name="p99_latency_ms", service="checkout")]
            ),
        )
        sigs = extract_signals_from_state(s)
        assert any(sig.kind == "latency_spike" for sig in sigs)


class TestDeduplication:
    def test_same_kind_same_service_dedup(self):
        s = StubState(
            evidence_pins=[
                StubPin(claim="OOMKilled in payment", service="payment"),
                StubPin(claim="OOMKilled in payment again", service="payment"),
            ],
        )
        sigs = extract_signals_from_state(s)
        oom = [sig for sig in sigs if sig.kind == "oom_killed"]
        # Both pins have the same relative time (origin can't be established)
        # so they dedup by (kind, service, t).
        assert len(oom) == 1


class TestDeterminism:
    def test_same_state_same_signals(self):
        s = StubState(
            evidence_pins=[StubPin(claim="Deploy triggered"), StubPin(claim="OOMKilled")],
        )
        a = extract_signals_from_state(s)
        b = extract_signals_from_state(s)
        assert [(sig.kind, sig.service, sig.t) for sig in a] == [
            (sig.kind, sig.service, sig.t) for sig in b
        ]


class TestRelativeTime:
    def test_origin_from_patient_zero(self):
        origin = datetime(2026, 4, 17, 14, 0, 0, tzinfo=timezone.utc)
        later = origin + timedelta(seconds=60)
        s = StubState(
            patient_zero={"service": "payment", "timestamp": origin.isoformat()},
            evidence_pins=[
                StubPin(
                    claim="OOMKilled",
                    service="payment",
                    timestamp=later,
                )
            ],
        )
        sigs = extract_signals_from_state(s)
        assert sigs[0].t == 60.0

"""Tests for signal_extractor — converts raw agent output dicts to EvidenceSignal objects."""

import pytest
from datetime import datetime

from src.hypothesis.signal_extractor import (
    extract_from_log_patterns,
    extract_from_metrics_anomalies,
    extract_from_k8s_events,
    extract_from_k8s_pods,
    extract_from_trace_spans,
    extract_from_code_findings,
    extract_from_change_correlations,
)
from src.models.hypothesis import EvidenceSignal


# ── Empty input returns empty list ──────────────────────────────────


class TestEmptyInputs:
    def test_log_patterns_empty(self):
        assert extract_from_log_patterns([]) == []

    def test_metrics_anomalies_empty(self):
        assert extract_from_metrics_anomalies([]) == []

    def test_k8s_events_empty(self):
        assert extract_from_k8s_events([]) == []

    def test_k8s_pods_empty(self):
        assert extract_from_k8s_pods([]) == []

    def test_trace_spans_empty(self):
        assert extract_from_trace_spans([]) == []

    def test_code_findings_empty(self):
        assert extract_from_code_findings([]) == []

    def test_change_correlations_empty(self):
        assert extract_from_change_correlations([]) == []


# ── Log patterns ────────────────────────────────────────────────────


class TestLogPatterns:
    def test_basic_extraction(self):
        patterns = [
            {
                "pattern_id": "p1",
                "exception_type": "NullPointer Exception",
                "error_message": "obj is null",
                "frequency": 42,
                "severity": "high",
                "affected_components": ["svc-a"],
            }
        ]
        signals = extract_from_log_patterns(patterns)
        assert len(signals) == 1
        s = signals[0]
        assert isinstance(s, EvidenceSignal)
        assert s.signal_id == "log_p1_0"
        assert s.signal_type == "log"
        assert s.signal_name == "nullpointer_exception"
        assert s.source_agent == "log_agent"
        assert s.raw_data == patterns[0]

    def test_multiple_patterns(self):
        patterns = [
            {
                "pattern_id": "p1",
                "exception_type": "Timeout Error",
                "error_message": "timed out",
                "frequency": 10,
                "severity": "medium",
                "affected_components": [],
            },
            {
                "pattern_id": "p2",
                "exception_type": "Connection Reset",
                "error_message": "reset by peer",
                "frequency": 5,
                "severity": "low",
                "affected_components": [],
            },
        ]
        signals = extract_from_log_patterns(patterns)
        assert len(signals) == 2
        assert signals[0].signal_name == "timeout_error"
        assert signals[1].signal_name == "connection_reset"
        assert signals[1].signal_id == "log_p2_1"


# ── Metrics anomalies ──────────────────────────────────────────────


class TestMetricsAnomalies:
    def test_basic_extraction(self):
        anomalies = [
            {
                "metric_name": "cpu_usage",
                "baseline_value": 30.0,
                "peak_value": 95.0,
                "severity": "critical",
                "spike_start": "2026-04-12T10:00:00",
                "correlation_to_incident": 0.9,
            }
        ]
        signals = extract_from_metrics_anomalies(anomalies)
        assert len(signals) == 1
        s = signals[0]
        assert s.signal_id == "met_0"
        assert s.signal_type == "metric"
        assert s.signal_name == "raw_metric"
        assert s.source_agent == "metrics_agent"
        assert s.timestamp == datetime(2026, 4, 12, 10, 0, 0)

    def test_missing_spike_start(self):
        anomalies = [
            {
                "metric_name": "mem_usage",
                "baseline_value": 50.0,
                "peak_value": 80.0,
                "severity": "high",
                "correlation_to_incident": 0.7,
            }
        ]
        signals = extract_from_metrics_anomalies(anomalies)
        assert len(signals) == 1
        assert signals[0].timestamp is None


# ── K8s events ──────────────────────────────────────────────────────


class TestK8sEvents:
    def test_normal_events_skipped(self):
        events = [
            {
                "reason": "Scheduled",
                "message": "Successfully assigned",
                "type": "Normal",
                "timestamp": "2026-04-12T10:00:00",
                "source_component": "scheduler",
                "involved_object": "pod/web-1",
            }
        ]
        signals = extract_from_k8s_events(events)
        assert signals == []

    def test_warning_events_extracted(self):
        events = [
            {
                "reason": "FailedScheduling",
                "message": "0/3 nodes available",
                "type": "Warning",
                "timestamp": "2026-04-12T10:05:00",
                "source_component": "scheduler",
                "involved_object": "pod/web-1",
            }
        ]
        signals = extract_from_k8s_events(events)
        assert len(signals) == 1
        s = signals[0]
        assert s.signal_id == "k8s_evt_0"
        assert s.signal_type == "k8s"
        assert s.signal_name == "raw_k8s_event"
        assert s.source_agent == "k8s_agent"

    def test_mixed_events(self):
        events = [
            {"reason": "Pulled", "message": "ok", "type": "Normal", "timestamp": None, "source_component": "kubelet", "involved_object": "pod/a"},
            {"reason": "BackOff", "message": "back-off", "type": "Warning", "timestamp": None, "source_component": "kubelet", "involved_object": "pod/b"},
            {"reason": "Started", "message": "ok", "type": "Normal", "timestamp": None, "source_component": "kubelet", "involved_object": "pod/c"},
        ]
        signals = extract_from_k8s_events(events)
        assert len(signals) == 1
        assert signals[0].raw_data["reason"] == "BackOff"


# ── K8s pods ────────────────────────────────────────────────────────


class TestK8sPods:
    def test_healthy_pod_skipped(self):
        pods = [
            {
                "pod_name": "web-1",
                "status": "Running",
                "restart_count": 0,
                "last_termination_reason": None,
                "resource_requests": {},
                "resource_limits": {},
            }
        ]
        signals = extract_from_k8s_pods(pods)
        assert signals == []

    def test_oom_killed(self):
        pods = [
            {
                "pod_name": "worker-1",
                "status": "CrashLoopBackOff",
                "restart_count": 8,
                "last_termination_reason": "OOMKilled",
                "resource_requests": {},
                "resource_limits": {},
            }
        ]
        signals = extract_from_k8s_pods(pods)
        # OOMKilled should produce an oom_kill signal
        oom = [s for s in signals if s.signal_name == "oom_kill"]
        assert len(oom) == 1
        assert oom[0].strength == 1.0

    def test_crashloop_backoff(self):
        pods = [
            {
                "pod_name": "api-1",
                "status": "CrashLoopBackOff",
                "restart_count": 6,
                "last_termination_reason": None,
                "resource_requests": {},
                "resource_limits": {},
            }
        ]
        signals = extract_from_k8s_pods(pods)
        crashloop = [s for s in signals if s.signal_name == "crashloop_backoff"]
        assert len(crashloop) == 1
        assert crashloop[0].strength == 0.9

    def test_high_restarts(self):
        pods = [
            {
                "pod_name": "svc-1",
                "status": "Running",
                "restart_count": 4,
                "last_termination_reason": None,
                "resource_requests": {},
                "resource_limits": {},
            }
        ]
        signals = extract_from_k8s_pods(pods)
        restart = [s for s in signals if s.signal_name == "pod_restart"]
        assert len(restart) == 1
        assert restart[0].strength == pytest.approx(0.4)

    def test_restart_count_five_triggers_crashloop(self):
        pods = [
            {
                "pod_name": "svc-2",
                "status": "Running",
                "restart_count": 5,
                "last_termination_reason": None,
                "resource_requests": {},
                "resource_limits": {},
            }
        ]
        signals = extract_from_k8s_pods(pods)
        names = [s.signal_name for s in signals]
        assert "crashloop_backoff" in names
        assert "pod_restart" in names


# ── Trace spans ─────────────────────────────────────────────────────


class TestTraceSpans:
    def test_only_error_or_slow_extracted(self):
        spans = [
            {"span_id": "s1", "service_name": "web", "operation_name": "GET /", "duration_ms": 50, "status": "ok", "error_message": None},
            {"span_id": "s2", "service_name": "api", "operation_name": "POST /pay", "duration_ms": 100, "status": "error", "error_message": "500"},
            {"span_id": "s3", "service_name": "db", "operation_name": "SELECT", "duration_ms": 6000, "status": "ok", "error_message": None},
        ]
        signals = extract_from_trace_spans(spans)
        assert len(signals) == 2

    def test_error_span(self):
        spans = [
            {"span_id": "s1", "service_name": "api", "operation_name": "POST /", "duration_ms": 100, "status": "error", "error_message": "timeout"},
        ]
        signals = extract_from_trace_spans(spans)
        assert signals[0].signal_name == "trace_error"
        assert signals[0].signal_id == "trace_0"
        assert signals[0].signal_type == "trace"
        assert signals[0].source_agent == "tracing_agent"

    def test_slow_span(self):
        spans = [
            {"span_id": "s1", "service_name": "db", "operation_name": "SELECT", "duration_ms": 8000, "status": "ok", "error_message": None},
        ]
        signals = extract_from_trace_spans(spans)
        assert signals[0].signal_name == "trace_latency"

    def test_healthy_spans_skipped(self):
        spans = [
            {"span_id": "s1", "service_name": "web", "operation_name": "GET /", "duration_ms": 50, "status": "ok", "error_message": None},
        ]
        signals = extract_from_trace_spans(spans)
        assert signals == []


# ── Code findings ───────────────────────────────────────────────────


class TestCodeFindings:
    def test_basic_extraction(self):
        findings = [
            {
                "finding_id": "f1",
                "category": "Memory Leak",
                "summary": "Unbounded cache growth",
                "severity": "high",
                "confidence_score": 85,
            }
        ]
        signals = extract_from_code_findings(findings)
        assert len(signals) == 1
        s = signals[0]
        assert s.signal_id == "code_0"
        assert s.signal_type == "code"
        assert s.signal_name == "memory leak"
        assert s.source_agent == "code_agent"
        assert s.strength == pytest.approx(0.85)

    def test_strength_from_confidence(self):
        findings = [
            {"finding_id": "f1", "category": "Race Condition", "summary": "x", "severity": "low", "confidence_score": 40},
            {"finding_id": "f2", "category": "SQL Injection", "summary": "y", "severity": "critical", "confidence_score": 100},
        ]
        signals = extract_from_code_findings(findings)
        assert signals[0].strength == pytest.approx(0.4)
        assert signals[1].strength == pytest.approx(1.0)

    def test_missing_confidence(self):
        findings = [
            {"finding_id": "f1", "category": "Deadlock", "summary": "x", "severity": "medium"},
        ]
        signals = extract_from_code_findings(findings)
        assert signals[0].strength == 1.0  # default


# ── Change correlations ────────────────────────────────────────────


class TestChangeCorrelations:
    def test_basic_extraction(self):
        correlations = [
            {
                "description": "Deploy v2.3.1",
                "timestamp": "2026-04-12T09:30:00",
                "files_changed": ["app.py"],
                "risk_score": 70,
            }
        ]
        signals = extract_from_change_correlations(correlations)
        assert len(signals) == 1
        s = signals[0]
        assert s.signal_id == "change_0"
        assert s.signal_type == "change"
        assert s.signal_name == "deployment_change"
        assert s.source_agent == "change_agent"
        assert s.strength == pytest.approx(0.7)

    def test_missing_risk_score(self):
        correlations = [
            {"description": "hotfix", "timestamp": None, "files_changed": []},
        ]
        signals = extract_from_change_correlations(correlations)
        assert signals[0].strength == pytest.approx(0.5)

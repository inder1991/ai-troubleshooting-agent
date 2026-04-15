"""Signal extractor — converts raw agent output dicts into typed EvidenceSignal objects.

Pure structured extraction with NO interpretation. Each function maps a specific
agent's output format to a list of EvidenceSignal instances.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from src.models.hypothesis import EvidenceSignal


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Best-effort ISO timestamp parsing."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# ── Log agent ───────────────────────────────────────────────────────


def extract_from_log_patterns(patterns: list[dict]) -> list[EvidenceSignal]:
    """Convert log agent error patterns to signals."""
    signals: list[EvidenceSignal] = []
    for i, p in enumerate(patterns):
        pid = p.get("pattern_id", str(i))
        exception_type = p.get("exception_type", "unknown")
        signal_name = exception_type.lower().replace(" ", "_")
        signals.append(
            EvidenceSignal(
                signal_id=f"log_{pid}_{i}",
                signal_type="log",
                signal_name=signal_name,
                raw_data=p,
                source_agent="log_agent",
            )
        )
    return signals


# ── Metrics agent ──────────────────────────────────────────────────


def extract_from_metrics_anomalies(anomalies: list[dict]) -> list[EvidenceSignal]:
    """Convert metric anomalies to signals."""
    signals: list[EvidenceSignal] = []
    for i, a in enumerate(anomalies):
        ts = _parse_timestamp(a.get("spike_start"))
        signals.append(
            EvidenceSignal(
                signal_id=f"met_{i}",
                signal_type="metric",
                signal_name="raw_metric",
                raw_data=a,
                source_agent="metrics_agent",
                timestamp=ts,
            )
        )
    return signals


# ── K8s events ─────────────────────────────────────────────────────


def extract_from_k8s_events(events: list[dict]) -> list[EvidenceSignal]:
    """Convert K8s events to signals. Only Warning events are extracted."""
    signals: list[EvidenceSignal] = []
    idx = 0
    for e in events:
        if e.get("type") == "Normal":
            continue
        ts = _parse_timestamp(e.get("timestamp"))
        signals.append(
            EvidenceSignal(
                signal_id=f"k8s_evt_{idx}",
                signal_type="k8s",
                signal_name="raw_k8s_event",
                raw_data=e,
                source_agent="k8s_agent",
                timestamp=ts,
            )
        )
        idx += 1
    return signals


# ── K8s pods ───────────────────────────────────────────────────────


def extract_from_k8s_pods(pods: list[dict]) -> list[EvidenceSignal]:
    """Convert K8s pod statuses to signals."""
    signals: list[EvidenceSignal] = []
    idx = 0
    for pod in pods:
        status = pod.get("status", "")
        restart_count = pod.get("restart_count", 0)
        termination_reason = pod.get("last_termination_reason")

        # Skip healthy pods
        if status == "Running" and restart_count == 0 and not termination_reason:
            continue

        # OOMKilled
        if termination_reason == "OOMKilled":
            signals.append(
                EvidenceSignal(
                    signal_id=f"k8s_pod_{idx}",
                    signal_type="k8s",
                    signal_name="oom_kill",
                    raw_data=pod,
                    source_agent="k8s_agent",
                    strength=1.0,
                )
            )
            idx += 1

        # CrashLoopBackOff
        if status == "CrashLoopBackOff" or restart_count >= 5:
            signals.append(
                EvidenceSignal(
                    signal_id=f"k8s_pod_{idx}",
                    signal_type="k8s",
                    signal_name="crashloop_backoff",
                    raw_data=pod,
                    source_agent="k8s_agent",
                    strength=0.9,
                )
            )
            idx += 1

        # High restarts
        if restart_count >= 3:
            signals.append(
                EvidenceSignal(
                    signal_id=f"k8s_pod_{idx}",
                    signal_type="k8s",
                    signal_name="pod_restart",
                    raw_data=pod,
                    source_agent="k8s_agent",
                    strength=min(1.0, restart_count / 10),
                )
            )
            idx += 1

    return signals


# ── Tracing agent ──────────────────────────────────────────────────


def extract_from_trace_spans(spans: list[dict]) -> list[EvidenceSignal]:
    """Convert trace spans to signals. Only error or slow (>5000ms) spans."""
    signals: list[EvidenceSignal] = []
    idx = 0
    for span in spans:
        status = span.get("status", "")
        duration_ms = span.get("duration_ms", 0)
        is_error = status == "error"
        is_slow = duration_ms > 5000

        if not is_error and not is_slow:
            continue

        signal_name = "trace_error" if is_error else "trace_latency"
        signals.append(
            EvidenceSignal(
                signal_id=f"trace_{idx}",
                signal_type="trace",
                signal_name=signal_name,
                raw_data=span,
                source_agent="tracing_agent",
            )
        )
        idx += 1
    return signals


# ── Code agent ─────────────────────────────────────────────────────


def extract_from_code_findings(findings: list[dict]) -> list[EvidenceSignal]:
    """Convert code analysis findings to signals."""
    signals: list[EvidenceSignal] = []
    for i, f in enumerate(findings):
        category = f.get("category", "unknown")
        confidence = f.get("confidence_score")
        strength = confidence / 100 if confidence is not None else 1.0
        signals.append(
            EvidenceSignal(
                signal_id=f"code_{i}",
                signal_type="code",
                signal_name=category.lower(),
                raw_data=f,
                source_agent="code_agent",
                strength=strength,
            )
        )
    return signals


# ── Change agent ───────────────────────────────────────────────────


def extract_from_change_correlations(correlations: list[dict]) -> list[EvidenceSignal]:
    """Convert change agent correlations to signals."""
    signals: list[EvidenceSignal] = []
    for i, c in enumerate(correlations):
        risk = c.get("risk_score")
        strength = risk / 100 if risk is not None else 0.5
        ts = _parse_timestamp(c.get("timestamp"))
        signals.append(
            EvidenceSignal(
                signal_id=f"change_{i}",
                signal_type="change",
                signal_name="deployment_change",
                raw_data=c,
                source_agent="change_agent",
                timestamp=ts,
                strength=strength,
            )
        )
    return signals

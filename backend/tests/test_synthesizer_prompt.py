"""Tests for synthesizer prompt construction."""
import pytest
from src.agents.cluster.synthesizer import _build_bounded_causal_prompt, CAUSAL_RULES, CONSTRAINED_LINK_TYPES


def test_causal_rules_included_in_system_prompt():
    """CAUSAL_RULES must appear in the synthesizer system prompt."""
    assert "TEMPORAL" in CAUSAL_RULES
    assert "MECHANISM" in CAUSAL_RULES
    assert "SINGLE ROOT" in CAUSAL_RULES
    assert "WEAKEST LINK" in CAUSAL_RULES
    assert len(CONSTRAINED_LINK_TYPES) > 5


def test_bounded_prompt_includes_anomalies():
    anomalies = [{"domain": "node", "anomaly_id": "n-001", "description": "DiskPressure", "severity": "high"}]
    reports = []
    prompt = _build_bounded_causal_prompt(anomalies, reports, {}, [])
    assert "DiskPressure" in prompt
    assert "Anomalies Found" in prompt


def test_bounded_prompt_includes_ruled_out():
    """ruled_out from domain reports must be included in synthesizer prompt."""
    from unittest.mock import MagicMock
    report = MagicMock()
    report.domain = "node"
    report.status = MagicMock(value="SUCCESS")
    report.confidence = 85
    report.anomalies = []
    report.ruled_out = ["etcd healthy", "API server responsive"]
    report.truncation_flags = MagicMock(events=False, pods=False, nodes=False)

    anomalies = [{"domain": "node", "anomaly_id": "n-001", "description": "test", "severity": "high"}]
    prompt = _build_bounded_causal_prompt(anomalies, [report], {}, [])
    assert "etcd healthy" in prompt

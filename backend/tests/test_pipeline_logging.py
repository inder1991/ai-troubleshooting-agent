"""Tests for intelligence pipeline logging."""
import asyncio
import logging

import pytest


@pytest.fixture
def _event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def test_signal_normalizer_logs_extraction(caplog, _event_loop):
    from src.agents.cluster.signal_normalizer import signal_normalizer
    state = {
        "domain_reports": [{
            "domain": "node",
            "status": "SUCCESS",
            "anomalies": [{"anomaly_id": "n-001", "description": "CrashLoopBackOff on pod/app-1", "severity": "high", "evidence_ref": "pod/default/app-1"}],
            "ruled_out": [],
        }],
    }
    sn_logger = logging.getLogger("src.agents.cluster.signal_normalizer")
    old = sn_logger.propagate
    sn_logger.propagate = True
    try:
        with caplog.at_level(logging.INFO):
            result = _event_loop.run_until_complete(signal_normalizer(state, {}))
        messages = " ".join(r.message for r in caplog.records)
        assert "signal" in messages.lower()
    finally:
        sn_logger.propagate = old


def test_hypothesis_engine_logs_scoring(caplog, _event_loop):
    from src.agents.cluster.hypothesis_engine import hypothesis_engine
    state = {
        "normalized_signals": [],
        "pattern_matches": [],
        "diagnostic_graph": {"nodes": {}, "edges": []},
        "diagnostic_issues": [],
        "domain_reports": [],
    }
    he_logger = logging.getLogger("src.agents.cluster.hypothesis_engine")
    old = he_logger.propagate
    he_logger.propagate = True
    try:
        with caplog.at_level(logging.INFO):
            result = _event_loop.run_until_complete(hypothesis_engine(state, {}))
        messages = " ".join(r.message for r in caplog.records)
        assert "hypothes" in messages.lower() or "no hypotheses" in messages.lower() or "0 hypotheses" in messages.lower()
    finally:
        he_logger.propagate = old

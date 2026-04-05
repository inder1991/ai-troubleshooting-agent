"""Tests for graph decision logging."""
import logging


def test_dispatch_router_logs_decision(caplog):
    from src.agents.cluster.graph import dispatch_router, logger as graph_logger

    state = {
        "diagnostic_scope": {"level": "cluster", "domains": ["ctrl_plane", "node", "network", "storage", "rbac"]},
        "rbac_check": {"status": "pass", "granted": [], "denied": ["routes"], "warnings": []},
    }
    # Enable propagation so caplog can capture records
    graph_logger.propagate = True
    try:
        with caplog.at_level(logging.INFO):
            result = dispatch_router(state)
        assert any("dispatch" in r.message.lower() for r in caplog.records)
    finally:
        graph_logger.propagate = False


def test_should_redispatch_logs_decision(caplog):
    from src.agents.cluster.graph import _should_redispatch, logger as graph_logger

    state = {
        "re_dispatch_domains": ["node"],
        "re_dispatch_count": 0,
        "dispatch_domains": ["ctrl_plane", "node"],
    }
    graph_logger.propagate = True
    try:
        with caplog.at_level(logging.INFO):
            result = _should_redispatch(state)
        assert any("redispatch" in r.message.lower() or "re-dispatch" in r.message.lower() or "dispatch" in r.message.lower() for r in caplog.records)
    finally:
        graph_logger.propagate = False

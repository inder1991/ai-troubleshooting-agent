"""Tests for tool executor logging."""
import asyncio
import logging
from unittest.mock import AsyncMock
from src.agents.cluster.tool_executor import execute_tool_call
from src.agents.cluster_client.base import QueryResult


def _enable_caplog(caplog):
    """Enable caplog to capture from the tool_executor logger."""
    tool_logger = logging.getLogger("src.agents.cluster.tool_executor")
    old_propagate = tool_logger.propagate
    old_level = tool_logger.level
    tool_logger.propagate = True
    tool_logger.setLevel(logging.DEBUG)
    return old_propagate, old_level


def _restore_logger(old_propagate, old_level):
    tool_logger = logging.getLogger("src.agents.cluster.tool_executor")
    tool_logger.propagate = old_propagate
    tool_logger.setLevel(old_level)


def test_tool_executor_logs_call(caplog):
    mock_client = AsyncMock()
    mock_client.list_nodes = AsyncMock(return_value=QueryResult(data=[{"name": "node-1"}]))
    old_propagate, old_level = _enable_caplog(caplog)
    try:
        with caplog.at_level(logging.DEBUG):
            result = asyncio.run(
                execute_tool_call("list_nodes", {}, mock_client)
            )
        messages = [r.message for r in caplog.records]
        assert any("list_nodes" in m for m in messages), f"No tool log in: {messages}"
    finally:
        _restore_logger(old_propagate, old_level)


def test_tool_executor_logs_truncation(caplog):
    mock_client = AsyncMock()
    large_data = [{"name": f"pod-{i}", "status": "Running", "details": "x" * 200} for i in range(100)]
    mock_client.list_pods = AsyncMock(return_value=QueryResult(data=large_data))
    old_propagate, old_level = _enable_caplog(caplog)
    try:
        with caplog.at_level(logging.DEBUG):
            result = asyncio.run(
                execute_tool_call("list_pods", {"namespace": "default"}, mock_client)
            )
        messages = [r.message for r in caplog.records]
        assert any("truncat" in m.lower() for m in messages), f"No truncation log in: {messages}"
    finally:
        _restore_logger(old_propagate, old_level)

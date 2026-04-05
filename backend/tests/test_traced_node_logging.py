"""Tests for traced_node decorator logging."""
import asyncio
import logging
import pytest
from src.agents.cluster.traced_node import traced_node, logger as traced_logger


@traced_node(timeout_seconds=5)
async def _sample_node(state: dict, config: dict) -> dict:
    return {"result": "ok"}


def test_traced_node_logs_start_and_success(caplog):
    traced_logger.propagate = True
    old_level = traced_logger.level
    traced_logger.setLevel(logging.DEBUG)
    try:
        with caplog.at_level(logging.DEBUG):
            result = asyncio.run(_sample_node({}, {}))
        messages = [r.message for r in caplog.records]
        assert any("_sample_node" in m and "start" in m.lower() for m in messages), f"No start log in: {messages}"
        assert any("_sample_node" in m and ("success" in m.lower() or "completed" in m.lower()) for m in messages), f"No success log in: {messages}"
    finally:
        traced_logger.propagate = False
        traced_logger.setLevel(old_level)


@traced_node(timeout_seconds=0.001)
async def _slow_node(state: dict, config: dict) -> dict:
    await asyncio.sleep(1)
    return {}


def test_traced_node_logs_timeout(caplog):
    traced_logger.propagate = True
    old_level = traced_logger.level
    traced_logger.setLevel(logging.DEBUG)
    try:
        with caplog.at_level(logging.DEBUG):
            result = asyncio.run(_slow_node({}, {}))
        messages = [r.message for r in caplog.records]
        assert any("timeout" in m.lower() for m in messages), f"No timeout log in: {messages}"
    finally:
        traced_logger.propagate = False
        traced_logger.setLevel(old_level)

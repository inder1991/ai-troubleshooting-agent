"""Tests for the ToolGuard safety layer (Task 2 of Network AI Chat)."""

import json

import pytest

from src.agents.network.tool_guard import (
    MAX_RESULT_BYTES,
    MAX_ROWS_DEFAULT,
    MAX_TOOL_CALLS_PER_MINUTE,
    ToolGuard,
    ToolGuardError,
)


@pytest.fixture
def guard() -> ToolGuard:
    return ToolGuard()


# ── validate() ──────────────────────────────────────────────────────


def test_allows_valid_read_tool(guard: ToolGuard):
    """validate() should pass for a normal read tool with limit <= MAX_ROWS_DEFAULT."""
    # Should not raise
    guard.validate(
        tool_name="get_flows",
        tool_args={"filter": "src=10.0.0.1", "limit": 100},
        view="network",
    )


def test_rejects_over_max_rows(guard: ToolGuard):
    """validate() should reject tool calls where limit > MAX_ROWS_DEFAULT (500)."""
    with pytest.raises(ToolGuardError, match="limit"):
        guard.validate(
            tool_name="get_flows",
            tool_args={"limit": MAX_ROWS_DEFAULT + 1},
            view="network",
        )


def test_rejects_simulate_in_non_investigation(guard: ToolGuard):
    """validate() should reject simulate tools when is_investigation is False."""
    with pytest.raises(ToolGuardError, match="simulate"):
        guard.validate(
            tool_name="simulate_rule_change",
            tool_args={"rule_id": "r1"},
            view="network",
            is_investigation=False,
        )


def test_allows_simulate_in_investigation(guard: ToolGuard):
    """validate() should allow simulate tools when is_investigation is True."""
    # Should not raise
    guard.validate(
        tool_name="simulate_connectivity",
        tool_args={"src": "10.0.0.1", "dst": "10.0.0.2"},
        view="network",
        is_investigation=True,
    )


# ── check_rate_limit() ──────────────────────────────────────────────


def test_rate_limit(guard: ToolGuard):
    """check_rate_limit() allows MAX_TOOL_CALLS_PER_MINUTE calls, rejects the next."""
    thread_id = "thread-rate-test"

    for _ in range(MAX_TOOL_CALLS_PER_MINUTE):
        guard.check_rate_limit(thread_id)

    with pytest.raises(ToolGuardError, match="rate"):
        guard.check_rate_limit(thread_id)


# ── truncate_result() ───────────────────────────────────────────────


def test_truncates_large_result(guard: ToolGuard):
    """truncate_result() should shrink large JSON to <= max_bytes with truncated flag."""
    # Build a dict larger than MAX_RESULT_BYTES
    big_dict = {f"key_{i}": "x" * 500 for i in range(30)}
    big_json = json.dumps(big_dict)
    assert len(big_json.encode()) > MAX_RESULT_BYTES

    result = guard.truncate_result(big_json, max_bytes=MAX_RESULT_BYTES)
    assert len(result.encode()) <= MAX_RESULT_BYTES

    parsed = json.loads(result)
    assert parsed.get("truncated") is True


def test_truncates_large_list(guard: ToolGuard):
    """truncate_result() should wrap large lists with items/total/truncated."""
    big_list = [{"id": i, "data": "y" * 200} for i in range(100)]
    big_json = json.dumps(big_list)
    assert len(big_json.encode()) > MAX_RESULT_BYTES

    result = guard.truncate_result(big_json, max_bytes=MAX_RESULT_BYTES)
    assert len(result.encode()) <= MAX_RESULT_BYTES

    parsed = json.loads(result)
    assert parsed["truncated"] is True
    assert parsed["total"] == 100
    assert len(parsed["items"]) <= 50


def test_small_result_unchanged(guard: ToolGuard):
    """truncate_result() should return small results as-is."""
    small = json.dumps({"status": "ok"})
    result = guard.truncate_result(small)
    assert result == small

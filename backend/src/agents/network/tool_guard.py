"""ToolGuard — safety layer between LLM tool calls and actual tool execution.

Every tool call passes through validate() + check_rate_limit() before running,
and every result passes through truncate_result() after.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

# ── Constants ────────────────────────────────────────────────────────

MAX_ROWS_DEFAULT: int = 500
MAX_TOOL_CALLS_PER_MINUTE: int = 20
MAX_RESULT_BYTES: int = 8192

_SIMULATE_TOOLS: frozenset[str] = frozenset(
    {"simulate_rule_change", "simulate_connectivity"}
)


# ── Exception ────────────────────────────────────────────────────────


class ToolGuardError(Exception):
    """Raised when a tool call is rejected by the guard."""


# ── Guard ────────────────────────────────────────────────────────────


class ToolGuard:
    """Validates, rate-limits, and truncates LLM tool calls."""

    def __init__(self) -> None:
        # thread_id -> list of monotonic timestamps
        self._call_timestamps: dict[str, list[float]] = defaultdict(list)

    # ── validate ─────────────────────────────────────────────────

    def validate(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        view: str,
        is_investigation: bool = False,
    ) -> None:
        """Raise ToolGuardError if the tool call violates safety constraints.

        Checks:
        1. ``limit`` arg must not exceed MAX_ROWS_DEFAULT.
        2. Simulate tools are only allowed during investigations.
        """
        # Check row limit
        limit = tool_args.get("limit")
        if limit is not None and limit > MAX_ROWS_DEFAULT:
            raise ToolGuardError(
                f"limit {limit} exceeds maximum of {MAX_ROWS_DEFAULT}"
            )

        # Check simulate tools
        if tool_name in _SIMULATE_TOOLS and not is_investigation:
            raise ToolGuardError(
                f"simulate tool '{tool_name}' is only allowed during investigations"
            )

    # ── check_rate_limit ─────────────────────────────────────────

    def check_rate_limit(self, thread_id: str) -> None:
        """Raise ToolGuardError if the thread exceeds the per-minute call quota.

        Uses a sliding 60-second window with ``time.monotonic()`` timestamps.
        """
        now = time.monotonic()
        window_start = now - 60.0

        # Prune old entries
        timestamps = self._call_timestamps[thread_id]
        self._call_timestamps[thread_id] = [
            ts for ts in timestamps if ts > window_start
        ]
        timestamps = self._call_timestamps[thread_id]

        if len(timestamps) >= MAX_TOOL_CALLS_PER_MINUTE:
            raise ToolGuardError(
                f"rate limit exceeded: {MAX_TOOL_CALLS_PER_MINUTE} tool calls "
                f"per minute for thread '{thread_id}'"
            )

        timestamps.append(now)

    # ── truncate_result ──────────────────────────────────────────

    def truncate_result(
        self,
        result_json: str,
        max_bytes: int = MAX_RESULT_BYTES,
    ) -> str:
        """Return *result_json* trimmed to at most *max_bytes* UTF-8 bytes.

        Strategies (in order):
        1. If it already fits, return as-is.
        2. If the parsed value is a **list**, wrap in
           ``{"items": first_50, "total": N, "truncated": true}`` and
           re-serialize (re-slicing items if still too large).
        3. If the parsed value is a **dict**, add ``"truncated": true`` and
           iteratively drop the largest-value fields until it fits.
        4. Fallback: raw byte-slice to *max_bytes*.
        """
        if len(result_json.encode()) <= max_bytes:
            return result_json

        try:
            data = json.loads(result_json)
        except (json.JSONDecodeError, TypeError):
            return result_json[:max_bytes]

        if isinstance(data, list):
            return self._truncate_list(data, max_bytes)
        if isinstance(data, dict):
            return self._truncate_dict(data, max_bytes)

        # Fallback for other JSON types (string, number, etc.)
        return result_json.encode()[:max_bytes].decode(errors="ignore")

    # ── private helpers ──────────────────────────────────────────

    @staticmethod
    def _truncate_list(data: list, max_bytes: int) -> str:
        total = len(data)
        items = data[:50]
        while True:
            candidate = json.dumps(
                {"items": items, "total": total, "truncated": True}
            )
            if len(candidate.encode()) <= max_bytes:
                return candidate
            # Halve the items list until it fits
            if len(items) <= 1:
                break
            items = items[: len(items) // 2]
        # Ultimate fallback
        return json.dumps({"items": [], "total": total, "truncated": True})

    @staticmethod
    def _truncate_dict(data: dict, max_bytes: int) -> str:
        data["truncated"] = True
        candidate = json.dumps(data)
        if len(candidate.encode()) <= max_bytes:
            return candidate

        # Iteratively remove the field whose serialized value is largest
        while len(candidate.encode()) > max_bytes:
            if len(data) <= 1:
                break
            # Find the key with the largest serialized value (skip 'truncated')
            largest_key = max(
                (k for k in data if k != "truncated"),
                key=lambda k: len(json.dumps(data[k])),
                default=None,
            )
            if largest_key is None:
                break
            del data[largest_key]
            candidate = json.dumps(data)

        if len(candidate.encode()) <= max_bytes:
            return candidate

        # Fallback: raw slice
        return result_json_slice(candidate, max_bytes)


def result_json_slice(s: str, max_bytes: int) -> str:
    """Slice a string to fit within max_bytes when encoded as UTF-8."""
    encoded = s.encode()[:max_bytes]
    return encoded.decode(errors="ignore")

"""
Tool Policy Engine — production guardrails for LLM tool-calling agents.

Enforces per-agent call policies (dependency ordering, max invocations),
result-set limits, SQL sanitisation, and structured call logging.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# 1. Per-agent tool policies
# ---------------------------------------------------------------------------

TOOL_POLICIES: dict[str, dict[str, dict[str, Any]]] = {
    "query_analyst": {
        "get_active_queries": {"allowed_anytime": True, "max_calls": 1},
        "get_slow_queries_from_stats": {"allowed_anytime": True, "max_calls": 1},
        "explain_query": {
            "requires_any": ["get_active_queries", "get_slow_queries_from_stats"],
            "max_calls": 3,
        },
        "get_wait_events": {"requires_any": ["get_active_queries"], "max_calls": 1},
        "get_long_transactions": {"allowed_anytime": True, "max_calls": 1},
    },
    "health_analyst": {
        "get_connection_pool": {"allowed_anytime": True, "max_calls": 1},
        "get_performance_stats": {"allowed_anytime": True, "max_calls": 1},
        "get_replication_status": {"allowed_anytime": True, "max_calls": 1},
        "get_lock_chains": {
            "requires_any": ["get_connection_pool", "get_performance_stats"],
            "max_calls": 1,
        },
        "get_autovacuum_status": {"allowed_anytime": True, "max_calls": 1},
    },
    "schema_analyst": {
        "get_schema_snapshot": {"allowed_anytime": True, "max_calls": 1},
        "get_table_detail": {"requires": ["get_schema_snapshot"], "max_calls": 5},
        "get_table_access_patterns": {
            "requires": ["get_schema_snapshot"],
            "max_calls": 1,
        },
    },
}

# ---------------------------------------------------------------------------
# 2. Result-set size caps (max items returned per tool)
# ---------------------------------------------------------------------------

TOOL_RESULT_LIMITS: dict[str, int] = {
    "get_active_queries": 10,
    "get_slow_queries_from_stats": 10,
    "explain_query": 1,
    "get_wait_events": 10,
    "get_long_transactions": 5,
    "get_connection_pool": 1,
    "get_performance_stats": 1,
    "get_replication_status": 1,
    "get_lock_chains": 5,
    "get_autovacuum_status": 10,
    "get_schema_snapshot": 20,
    "get_table_detail": 1,
    "get_table_access_patterns": 10,
}

# ---------------------------------------------------------------------------
# 3. ToolPolicyEnforcer
# ---------------------------------------------------------------------------


class ToolPolicyEnforcer:
    """Validates tool calls against the declared policy for a single agent."""

    def __init__(self, agent_name: str):
        # Note: Thread-safety is not needed here because each agent runs its own
        # ToolPolicyEnforcer instance, and tool calls within a single agent's turn
        # are sequential (LLM returns one response at a time). No concurrent access.
        self.agent_name = agent_name
        self.policies = TOOL_POLICIES.get(agent_name, {})
        self.call_counts: dict[str, int] = {}
        self.called_tools: set[str] = set()

    def validate(self, tool_name: str) -> tuple[bool, str]:
        """Return ``(allowed, reason)`` for the proposed *tool_name* call."""
        policy = self.policies.get(tool_name)
        if policy is None:
            return False, f"Tool '{tool_name}' is not in the policy for agent '{self.agent_name}'"

        # --- max_calls guard ---
        max_calls = policy.get("max_calls", 1)
        current = self.call_counts.get(tool_name, 0)
        if current >= max_calls:
            return False, (
                f"Tool '{tool_name}' has reached its max call limit "
                f"({current}/{max_calls})"
            )

        # --- dependency: requires (ALL must have been called) ---
        requires = policy.get("requires")
        if requires:
            missing = [t for t in requires if t not in self.called_tools]
            if missing:
                return False, (
                    f"Tool '{tool_name}' requires prior call(s) to: "
                    f"{', '.join(missing)}"
                )

        # --- dependency: requires_any (at least ONE must have been called) ---
        requires_any = policy.get("requires_any")
        if requires_any:
            if not any(t in self.called_tools for t in requires_any):
                return False, (
                    f"Tool '{tool_name}' requires at least one prior call to: "
                    f"{', '.join(requires_any)}"
                )

        return True, "ok"

    def record(self, tool_name: str) -> None:
        """Record a successful invocation of *tool_name*."""
        self.call_counts[tool_name] = self.call_counts.get(tool_name, 0) + 1
        self.called_tools.add(tool_name)


# ---------------------------------------------------------------------------
# 4. ToolCallRecord
# ---------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    """Immutable audit entry for a single tool invocation."""

    call_id: str
    tool_name: str
    args: dict
    status: str  # "success" | "rejected" | "timeout" | "error"
    reason: str = ""
    result_summary: str = ""
    result_count: int = 0
    truncated: bool = False
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# 5. SQL sanitisation for EXPLAIN
# ---------------------------------------------------------------------------

FORBIDDEN_PATTERNS = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|ALTER\s+TABLE|INSERT|UPDATE|CREATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def sanitize_sql_for_explain(sql: str) -> str | None:
    """Return a cleaned SQL string safe for ``EXPLAIN``, or ``None`` if unsafe."""
    clean = sql.strip().rstrip(";")
    if FORBIDDEN_PATTERNS.search(clean):
        return None
    if not clean.upper().startswith("SELECT"):
        return None
    return clean


# ---------------------------------------------------------------------------
# 6. ToolCallExecutor
# ---------------------------------------------------------------------------


class ToolCallExecutor:
    """Orchestrates tool execution within a single agent turn.

    Parameters
    ----------
    agent_name:
        Logical agent identifier (must match a key in ``TOOL_POLICIES``).
    adapter:
        Database adapter instance whose methods correspond to tool names.
    emitter:
        Callable / object with an ``emit`` method used to stream reasoning
        and tool results back to the caller.
    policy:
        Pre-built ``ToolPolicyEnforcer`` for this agent.
    """

    def __init__(
        self,
        agent_name: str,
        adapter: Any,
        emitter: Any,
        policy: ToolPolicyEnforcer,
    ):
        self.agent_name = agent_name
        self.adapter = adapter
        self.emitter = emitter
        self.policy = policy
        self.call_log: list[ToolCallRecord] = []

    # ----- public API -----

    async def process_response(self, response: Any) -> list[dict]:
        """Walk through each content block of an LLM *response*.

        * ``tool_use`` blocks are validated, executed, and recorded.
        * ``text`` blocks are emitted as reasoning; free-text tool
          invocation attempts are flagged.

        Returns a list of tool-result dicts suitable for feeding back
        to the model as the ``tool`` role.
        """
        results: list[dict] = []

        for block in getattr(response, "content", []):
            block_type = getattr(block, "type", None)

            if block_type == "tool_use":
                tool_name = getattr(block, "name", None)
                if not tool_name:
                    continue
                args = getattr(block, "input", {})
                if not isinstance(args, dict):
                    args = {}
                call_id = getattr(block, "id", str(uuid.uuid4()))

                result = await self.execute_tool_call(tool_name, args, call_id)
                results.append(result)

            elif block_type == "text":
                text = getattr(block, "text", "")
                if hasattr(self.emitter, "emit"):
                    await self.emitter.emit("reasoning", text)
                if self._looks_like_tool_call(text):
                    if hasattr(self.emitter, "emit"):
                        await self.emitter.emit(
                            "warning",
                            f"[{self.agent_name}] LLM attempted free-text tool call — ignored",
                        )

        return results

    async def execute_tool_call(
        self, tool_name: str, args: dict, call_id: str
    ) -> dict:
        """Validate, execute, and record a single tool call."""

        # --- policy check ---
        allowed, reason = self.policy.validate(tool_name)
        if not allowed:
            record = ToolCallRecord(
                call_id=call_id,
                tool_name=tool_name,
                args=args,
                status="rejected",
                reason=reason,
            )
            self.call_log.append(record)
            return {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": f"REJECTED: {reason}",
                "is_error": True,
            }

        # --- SQL sanitisation for explain_query ---
        if tool_name == "explain_query":
            raw_sql = args.get("sql", args.get("query", ""))
            sanitized = sanitize_sql_for_explain(raw_sql)
            if sanitized is None:
                record = ToolCallRecord(
                    call_id=call_id,
                    tool_name=tool_name,
                    args=args,
                    status="rejected",
                    reason="SQL failed sanitisation (non-SELECT or forbidden keyword)",
                )
                self.call_log.append(record)
                return {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": "REJECTED: SQL query is not a safe SELECT statement",
                    "is_error": True,
                }
            # Replace with sanitised version
            if "sql" in args:
                args["sql"] = sanitized
            elif "query" in args:
                args["query"] = sanitized

        # --- invoke adapter method ---
        try:
            method = getattr(self.adapter, tool_name, None)
            if method is None:
                raise AttributeError(
                    f"Adapter has no method '{tool_name}'"
                )
            raw_result = await asyncio.wait_for(method(**args), timeout=30.0)
        except asyncio.TimeoutError:
            record = ToolCallRecord(
                call_id=call_id,
                tool_name=tool_name,
                args=args,
                status="timeout",
                reason=f"Tool '{tool_name}' timed out after 30s",
            )
            self.call_log.append(record)
            return {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": f"TIMEOUT: Tool '{tool_name}' did not respond within 30s",
                "is_error": True,
            }
        except Exception as exc:
            record = ToolCallRecord(
                call_id=call_id,
                tool_name=tool_name,
                args=args,
                status="error",
                reason=str(exc),
            )
            self.call_log.append(record)
            return {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": f"ERROR: {exc}",
                "is_error": True,
            }

        # --- format & limit ---
        formatted = self._format_result(tool_name, raw_result)

        # --- record success ---
        self.policy.record(tool_name)
        record = ToolCallRecord(
            call_id=call_id,
            tool_name=tool_name,
            args=args,
            status="success",
            result_summary=formatted.get("summary", ""),
            result_count=formatted.get("count", 0),
            truncated=formatted.get("truncated", False),
        )
        self.call_log.append(record)

        return {
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": formatted.get("data"),
        }

    # ----- internal helpers -----

    def _format_result(self, tool_name: str, raw_result: Any) -> dict:
        """Convert adapter return values to JSON-serialisable dicts.

        Applies ``TOOL_RESULT_LIMITS`` and generates a human-readable
        summary string.
        """
        limit = TOOL_RESULT_LIMITS.get(tool_name)
        truncated = False

        # --- Pydantic model (single object) ---
        if hasattr(raw_result, "model_dump"):
            data = raw_result.model_dump()
            return {
                "data": data,
                "count": 1,
                "truncated": False,
                "summary": f"{tool_name}: 1 result",
            }

        # --- list of results ---
        if isinstance(raw_result, list):
            converted: list[Any] = []
            for item in raw_result:
                if hasattr(item, "model_dump"):
                    converted.append(item.model_dump())
                elif isinstance(item, dict):
                    converted.append(item)
                else:
                    converted.append(str(item))

            total = len(converted)
            if limit is not None and total > limit:
                converted = converted[:limit]
                truncated = True

            return {
                "data": converted,
                "count": len(converted),
                "truncated": truncated,
                "summary": (
                    f"{tool_name}: {len(converted)}/{total} results"
                    if truncated
                    else f"{tool_name}: {total} results"
                ),
            }

        # --- plain dict ---
        if isinstance(raw_result, dict):
            return {
                "data": raw_result,
                "count": 1,
                "truncated": False,
                "summary": f"{tool_name}: 1 result",
            }

        # --- None / other ---
        return {
            "data": raw_result,
            "count": 0 if raw_result is None else 1,
            "truncated": False,
            "summary": f"{tool_name}: {'no data' if raw_result is None else '1 result'}",
        }

    @staticmethod
    def _looks_like_tool_call(text: str) -> bool:
        """Heuristic check for free-text tool invocation attempts."""
        patterns = [
            r"get_\w+\(",
            r"explain_query\(",
            r"adapter\.\w+",
            r"Tool:\s*\w+",
        ]
        return any(re.search(p, text) for p in patterns)

"""LLM call telemetry: per-call records, session summaries, cost calculation."""

from __future__ import annotations
import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


MODEL_PRICING = {
    "claude-haiku-4-5-20251001": {
        "input_per_1k": 0.0008,
        "output_per_1k": 0.004,
    },
    "claude-sonnet-4-20250514": {
        "input_per_1k": 0.003,
        "output_per_1k": 0.015,
    },
}


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute estimated cost in USD for an LLM call."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["claude-sonnet-4-20250514"])
    return (input_tokens / 1000 * pricing["input_per_1k"] +
            output_tokens / 1000 * pricing["output_per_1k"])


@dataclass
class LLMCallRecord:
    """Telemetry record for a single LLM API call."""
    call_id: str = ""
    session_id: str = ""
    agent_name: str = ""
    model: str = ""
    call_type: str = ""           # "tool_calling", "analysis", "synthesis"

    # Request
    input_tokens: int = 0
    input_messages_count: int = 0
    tools_provided: int = 0
    system_prompt_tokens: int = 0

    # Response
    output_tokens: int = 0
    tool_calls_made: int = 0
    stop_reason: str = ""         # "end_turn", "tool_use", "max_tokens"

    # Performance
    latency_ms: int = 0
    time_to_first_token_ms: int = 0

    # Status
    success: bool = True
    error: str = ""
    retried: bool = False
    fallback_used: bool = False

    # Cost
    estimated_cost_usd: float = 0.0

    timestamp: str = ""

    def __post_init__(self):
        if not self.call_id:
            self.call_id = str(uuid.uuid4())[:8]
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.estimated_cost_usd == 0.0 and self.model:
            self.estimated_cost_usd = compute_cost(self.model, self.input_tokens, self.output_tokens)

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "model": self.model,
            "call_type": self.call_type,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "tool_calls_made": self.tool_calls_made,
            "stop_reason": self.stop_reason,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error": self.error,
            "fallback_used": self.fallback_used,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "timestamp": self.timestamp,
        }


@dataclass
class AgentLLMStats:
    """Per-agent aggregated stats."""
    agent_name: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    fallback_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: int = 0
    total_cost_usd: float = 0.0
    source: str = "llm"   # "llm" or "heuristic"

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "calls": self.total_calls,
            "tokens": f"{self.total_input_tokens // 1000}K/{self.total_output_tokens // 1000}K",
            "cost_usd": round(self.total_cost_usd, 4),
            "latency_ms": self.total_latency_ms,
            "source": self.source,
            "success_rate": self.successful_calls / max(self.total_calls, 1),
        }


@dataclass
class SessionLLMSummary:
    """Session-level aggregated LLM telemetry."""
    session_id: str = ""
    scan_mode: str = ""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    fallback_calls: int = 0

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: int = 0
    total_cost_usd: float = 0.0
    budget_used_pct: float = 0.0

    per_agent: dict[str, AgentLLMStats] = field(default_factory=dict)

    # Anomalies
    slowest_call_ms: int = 0
    most_expensive_call_usd: float = 0.0
    rate_limit_hits: int = 0
    timeout_count: int = 0
    parse_failures: int = 0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "scan_mode": self.scan_mode,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "fallback_calls": self.fallback_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_latency_ms": self.total_latency_ms,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "budget_used_pct": round(self.budget_used_pct, 3),
            "per_agent": {k: v.to_dict() for k, v in self.per_agent.items()},
            "slowest_call_ms": self.slowest_call_ms,
            "most_expensive_call_usd": round(self.most_expensive_call_usd, 6),
            "rate_limit_hits": self.rate_limit_hits,
            "timeout_count": self.timeout_count,
            "parse_failures": self.parse_failures,
        }


class SessionTelemetryCollector:
    """Thread-safe collector for LLM call records within a session."""

    def __init__(self, session_id: str, scan_mode: str = ""):
        self.session_id = session_id
        self.scan_mode = scan_mode
        self._records: list[LLMCallRecord] = []
        self._lock = threading.Lock()

    def record_call(self, record: LLMCallRecord) -> None:
        """Add a call record."""
        record.session_id = self.session_id
        with self._lock:
            self._records.append(record)

    def get_records(self) -> list[LLMCallRecord]:
        """Return all records."""
        with self._lock:
            return list(self._records)

    def get_summary(self, budget_used_pct: float = 0.0) -> SessionLLMSummary:
        """Compute session summary from all records."""
        records = self.get_records()
        summary = SessionLLMSummary(
            session_id=self.session_id,
            scan_mode=self.scan_mode,
            budget_used_pct=budget_used_pct,
        )

        per_agent: dict[str, AgentLLMStats] = {}

        for r in records:
            summary.total_calls += 1
            if r.success:
                summary.successful_calls += 1
            else:
                summary.failed_calls += 1
            if r.fallback_used:
                summary.fallback_calls += 1

            summary.total_input_tokens += r.input_tokens
            summary.total_output_tokens += r.output_tokens
            summary.total_latency_ms += r.latency_ms
            summary.total_cost_usd += r.estimated_cost_usd

            if r.latency_ms > summary.slowest_call_ms:
                summary.slowest_call_ms = r.latency_ms
            if r.estimated_cost_usd > summary.most_expensive_call_usd:
                summary.most_expensive_call_usd = r.estimated_cost_usd

            if r.error == "rate_limit":
                summary.rate_limit_hits += 1
            elif r.error == "timeout":
                summary.timeout_count += 1
            elif r.error == "parse_error":
                summary.parse_failures += 1

            # Per-agent stats
            if r.agent_name not in per_agent:
                per_agent[r.agent_name] = AgentLLMStats(agent_name=r.agent_name)
            agent = per_agent[r.agent_name]
            agent.total_calls += 1
            if r.success:
                agent.successful_calls += 1
            else:
                agent.failed_calls += 1
            if r.fallback_used:
                agent.fallback_calls += 1
                agent.source = "heuristic"
            agent.total_input_tokens += r.input_tokens
            agent.total_output_tokens += r.output_tokens
            agent.total_latency_ms += r.latency_ms
            agent.total_cost_usd += r.estimated_cost_usd

        summary.per_agent = per_agent
        return summary

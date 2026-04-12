"""Session budget system for LLM cost control."""

from __future__ import annotations
import copy
import threading
from dataclasses import dataclass, field
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SessionBudget:
    """Budget constraints for a single diagnostic session."""
    max_llm_calls: int
    max_tool_calls_per_agent: int
    max_tokens_input: int
    max_tokens_output: int
    max_total_latency_ms: int

    # Tracking (mutable)
    current_llm_calls: int = 0
    current_tokens_input: int = 0
    current_tokens_output: int = 0
    current_latency_ms: int = 0

    # Thread safety
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def can_call(self) -> bool:
        """Check if budget allows another LLM call."""
        return (self.current_llm_calls < self.max_llm_calls
                and self.current_tokens_input < self.max_tokens_input
                and self.current_latency_ms < self.max_total_latency_ms)

    def record(self, input_tokens: int, output_tokens: int, latency_ms: int) -> None:
        """Record an LLM call's resource usage."""
        with self._lock:
            self.current_llm_calls += 1
            self.current_tokens_input += input_tokens
            self.current_tokens_output += output_tokens
            self.current_latency_ms += latency_ms

    def remaining_budget_pct(self) -> float:
        """Return remaining budget as a percentage (0.0 to 1.0)."""
        if self.max_llm_calls == 0:
            return 0.0
        return max(0.0, 1.0 - (self.current_llm_calls / self.max_llm_calls))

    def budget_used_pct(self) -> float:
        """Return used budget as a percentage (0.0 to 1.0)."""
        return 1.0 - self.remaining_budget_pct()

    def is_budget_warning(self) -> bool:
        """Return True if budget > 80% consumed."""
        return self.budget_used_pct() > 0.8

    def to_dict(self) -> dict:
        """Serialize budget state for API responses."""
        return {
            "max_llm_calls": self.max_llm_calls,
            "max_tool_calls_per_agent": self.max_tool_calls_per_agent,
            "max_tokens_input": self.max_tokens_input,
            "max_tokens_output": self.max_tokens_output,
            "max_total_latency_ms": self.max_total_latency_ms,
            "current_llm_calls": self.current_llm_calls,
            "current_tokens_input": self.current_tokens_input,
            "current_tokens_output": self.current_tokens_output,
            "current_latency_ms": self.current_latency_ms,
            "budget_used_pct": round(self.budget_used_pct(), 3),
            "is_warning": self.is_budget_warning(),
        }


# Pre-configured budgets for different scan modes
SCAN_BUDGETS = {
    "quick": SessionBudget(
        max_llm_calls=8,
        max_tool_calls_per_agent=0,
        max_tokens_input=50_000,
        max_tokens_output=10_000,
        max_total_latency_ms=30_000,
    ),
    "standard": SessionBudget(
        max_llm_calls=20,
        max_tool_calls_per_agent=4,
        max_tokens_input=150_000,
        max_tokens_output=30_000,
        max_total_latency_ms=90_000,
    ),
    "deep": SessionBudget(
        max_llm_calls=40,
        max_tool_calls_per_agent=5,
        max_tokens_input=300_000,
        max_tokens_output=60_000,
        max_total_latency_ms=180_000,
    ),
    "diagnostic": SessionBudget(  # Default for cluster diagnostics
        max_llm_calls=20,
        max_tool_calls_per_agent=4,
        max_tokens_input=150_000,
        max_tokens_output=30_000,
        max_total_latency_ms=90_000,
    ),
    "guard": SessionBudget(  # Guard mode: lighter budget
        max_llm_calls=12,
        max_tool_calls_per_agent=3,
        max_tokens_input=80_000,
        max_tokens_output=15_000,
        max_total_latency_ms=60_000,
    ),
    "cross_repo": SessionBudget(
        max_llm_calls=40,
        max_tool_calls_per_agent=6,
        max_tokens_input=300_000,
        max_tokens_output=60_000,
        max_total_latency_ms=180_000,
    ),
}


def get_budget_for_mode(scan_mode: str) -> SessionBudget:
    """Create a fresh budget for the given scan mode."""
    template = SCAN_BUDGETS.get(scan_mode, SCAN_BUDGETS["standard"])
    return SessionBudget(
        max_llm_calls=template.max_llm_calls,
        max_tool_calls_per_agent=template.max_tool_calls_per_agent,
        max_tokens_input=template.max_tokens_input,
        max_tokens_output=template.max_tokens_output,
        max_total_latency_ms=template.max_total_latency_ms,
    )


def adapt_budget(budget: SessionBudget, cluster_size: dict) -> SessionBudget:
    """Adjust budget based on cluster size.

    Only scale UP for large clusters (more data = more tool rounds).
    Never scale down — the diagnostic pipeline (4 agents + synthesizer + verdict)
    needs a minimum of ~16 LLM calls regardless of cluster size.
    """
    node_count = cluster_size.get("nodes", 0)
    pod_count = cluster_size.get("pods", 0)

    if node_count > 100 or pod_count > 5000:
        budget.max_llm_calls = int(budget.max_llm_calls * 1.5)
        budget.max_total_latency_ms = int(budget.max_total_latency_ms * 1.5)
        budget.max_tool_calls_per_agent = max(2, budget.max_tool_calls_per_agent - 1)
        logger.info("Budget adapted for large cluster: nodes=%d, pods=%d", node_count, pod_count)

    return budget

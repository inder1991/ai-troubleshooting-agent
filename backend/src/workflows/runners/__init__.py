"""Workflow runner registry — process-wide singleton.

Mirrors ``src.contracts.service`` pattern.

Task 5 wires the registry skeleton; Task 6 fills ``init_runners()`` with
the 10 Phase-0 adapters.
"""

from __future__ import annotations

from .registry import AgentRunner, AgentRunnerRegistry

__all__ = [
    "AgentRunner",
    "AgentRunnerRegistry",
    "init_runners",
    "get_runner_registry",
]

_registry: AgentRunnerRegistry | None = None


def init_runners() -> AgentRunnerRegistry:
    """Create and install the process-wide ``AgentRunnerRegistry``.

    Task 6 populates this with the 10 Phase-0 adapters; for Task 5 the
    body is intentionally minimal so integrity checks can be wired end
    to end before adapter code lands.
    """
    global _registry
    reg = AgentRunnerRegistry()
    _registry = reg
    return reg


def get_runner_registry() -> AgentRunnerRegistry:
    if _registry is None:
        raise RuntimeError(
            "runners not initialized — call init_runners() at startup"
        )
    return _registry

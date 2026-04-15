"""Typed ``AgentRunnerRegistry`` with contract-coverage integrity check.

Phase 2 Task 5.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.contracts.registry import ContractRegistry


@runtime_checkable
class AgentRunner(Protocol):
    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]: ...


class AgentRunnerRegistry:
    """In-memory registry mapping ``(agent_name, agent_version)`` → runner.

    Mirrors ``ContractRegistry`` — the integrity check in
    :meth:`verify_covers` asserts every declared contract has a runner.
    """

    def __init__(self) -> None:
        self._runners: dict[tuple[str, int], AgentRunner] = {}

    def register(self, name: str, version: int, runner: AgentRunner) -> None:
        self._runners[(name, version)] = runner

    def get(self, name: str, version: int) -> AgentRunner:
        return self._runners[(name, version)]

    def covers(self, name: str, version: int) -> bool:
        return (name, version) in self._runners

    def verify_covers(
        self, contracts: ContractRegistry
    ) -> list[tuple[str, int]]:
        """Return ``(name, version)`` tuples present in ``contracts`` but
        not in this registry. Empty list means full coverage."""
        missing: list[tuple[str, int]] = []
        for c in contracts.list_all_versions():
            if not self.covers(c.name, c.version):
                missing.append((c.name, c.version))
        return missing

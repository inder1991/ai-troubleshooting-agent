"""Runner adapter for ``change_agent`` (Phase-0 ``ChangeAgent``).

Entry point is ``run_two_pass`` (not ``run``).
"""

from __future__ import annotations

from typing import Any

from src.agents.change_agent import ChangeAgent


class ChangeAgentRunner:
    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        agent = ChangeAgent()
        return await agent.run_two_pass(inputs)

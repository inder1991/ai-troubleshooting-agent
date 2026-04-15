"""Runner adapter for ``code_agent`` (Phase-0 ``CodeNavigatorAgent``).

Entry point is ``run_two_pass`` (not ``run``).
"""

from __future__ import annotations

from typing import Any

from src.agents.code_agent import CodeNavigatorAgent


class CodeAgentRunner:
    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        agent = CodeNavigatorAgent()
        return await agent.run_two_pass(inputs)

"""Runner adapter for ``log_agent`` (Phase-0 ``LogAnalysisAgent``).

Pass-through: executor ``inputs`` IS the Phase-0 context dict.
"""

from __future__ import annotations

from typing import Any

from src.agents.log_agent import LogAnalysisAgent


class LogAgentRunner:
    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        agent = LogAnalysisAgent()
        return await agent.run(inputs)

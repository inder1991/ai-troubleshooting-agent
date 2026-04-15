"""Runner adapter for ``tracing_agent`` (Phase-0 ``TracingAgent``).

Entry point is ``run_two_pass`` (not ``run``).
"""

from __future__ import annotations

from typing import Any

from src.agents.tracing_agent import TracingAgent


class TracingAgentRunner:
    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        agent = TracingAgent()
        return await agent.run_two_pass(inputs)

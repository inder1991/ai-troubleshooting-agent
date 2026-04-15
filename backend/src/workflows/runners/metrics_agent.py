"""Runner adapter for ``metrics_agent`` (Phase-0 ``MetricsAgent``)."""

from __future__ import annotations

from typing import Any

from src.agents.metrics_agent import MetricsAgent


class MetricsAgentRunner:
    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        agent = MetricsAgent()
        return await agent.run(inputs)

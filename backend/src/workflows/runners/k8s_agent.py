"""Runner adapter for ``k8s_agent`` (Phase-0 ``K8sAgent``)."""

from __future__ import annotations

from typing import Any

from src.agents.k8s_agent import K8sAgent


class K8sAgentRunner:
    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        agent = K8sAgent()
        return await agent.run(inputs)

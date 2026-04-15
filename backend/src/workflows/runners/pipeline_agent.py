"""Runner adapter for ``pipeline_agent`` (Phase-0 ``PipelineAgent``).

``PipelineAgent`` requires an LLM client at construction time. The adapter
holds a reference to the shared client passed in by ``init_runners()``
so we do not spin up a new Anthropic session on every invocation.
"""

from __future__ import annotations

from typing import Any

from src.agents.pipeline_agent import PipelineAgent


class PipelineAgentRunner:
    def __init__(self, *, llm: Any) -> None:
        self._agent = PipelineAgent(llm=llm)

    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._agent.run(inputs)

"""Bridge adapter: wraps existing investigation agents (LogAnalysisAgent, MetricsAgent, etc.)
to conform to the AgentRunner protocol expected by WorkflowExecutor."""
from __future__ import annotations

from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

TWO_PASS_AGENTS = {"code_agent", "change_agent", "metrics_agent", "tracing_agent", "k8s_agent"}


class InvestigationAgentRunner:
    def __init__(
        self,
        agent_cls: type,
        agent_name: str,
        connection_config: dict,
        use_two_pass: bool | None = None,
    ):
        self._agent_cls = agent_cls
        self._agent_name = agent_name
        self._connection_config = connection_config
        self._use_two_pass = use_two_pass if use_two_pass is not None else (agent_name in TWO_PASS_AGENTS)

    async def run(self, inputs: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
        agent = self._agent_cls(connection_config=self._connection_config)

        if self._use_two_pass and hasattr(agent, "run_two_pass"):
            result = await agent.run_two_pass(inputs, None)
        else:
            result = await agent.run(inputs, None)

        return result

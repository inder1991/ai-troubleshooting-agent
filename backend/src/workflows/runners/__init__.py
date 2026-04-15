"""Workflow runner registry — process-wide singleton.

Mirrors ``src.contracts.service`` pattern. ``init_runners()`` registers
all 10 Phase-0 adapters at version 1, matching the shipped manifests.

All adapter imports happen lazily inside ``init_runners()`` so that
importing :mod:`src.workflows.runners` at module-load time does not pull
in the full Phase-0 agent graph.
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
    """Build and install the process-wide ``AgentRunnerRegistry`` with
    all 10 Phase-1 agents at version 1."""
    global _registry
    reg = AgentRunnerRegistry()

    # Shared LLM client for ``pipeline_agent``. The repo exposes
    # ``AnthropicClient`` as the canonical LLM wrapper — hold a single
    # instance on the pipeline runner so it is reused across runs.
    from src.utils.llm_client import AnthropicClient

    pipeline_llm = AnthropicClient(agent_name="pipeline_agent")

    from .change_agent import ChangeAgentRunner
    from .code_agent import CodeAgentRunner
    from .critic_agent import CriticAgentRunner
    from .impact_analyzer import ImpactAnalyzerRunner
    from .intent_parser import IntentParserRunner
    from .k8s_agent import K8sAgentRunner
    from .log_agent import LogAgentRunner
    from .metrics_agent import MetricsAgentRunner
    from .pipeline_agent import PipelineAgentRunner
    from .tracing_agent import TracingAgentRunner

    reg.register("log_agent", 1, LogAgentRunner())
    reg.register("k8s_agent", 1, K8sAgentRunner())
    reg.register("metrics_agent", 1, MetricsAgentRunner())
    reg.register("tracing_agent", 1, TracingAgentRunner())
    reg.register("code_agent", 1, CodeAgentRunner())
    reg.register("change_agent", 1, ChangeAgentRunner())
    reg.register("critic_agent", 1, CriticAgentRunner())
    reg.register("pipeline_agent", 1, PipelineAgentRunner(llm=pipeline_llm))
    reg.register("impact_analyzer", 1, ImpactAnalyzerRunner())
    reg.register("intent_parser", 1, IntentParserRunner())

    _registry = reg
    return reg


def get_runner_registry() -> AgentRunnerRegistry:
    if _registry is None:
        raise RuntimeError(
            "runners not initialized — call init_runners() at startup"
        )
    return _registry

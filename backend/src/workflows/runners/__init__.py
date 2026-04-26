"""Workflow runner registry — process-wide singleton.

Mirrors ``src.contracts.service`` pattern. ``init_runners()`` registers
all 10 Phase-0 adapters at version 1, matching the shipped manifests.

All adapter imports happen lazily inside ``init_runners()`` so that
importing :mod:`src.workflows.runners` at module-load time does not pull
in the full Phase-0 agent graph.
"""

from __future__ import annotations

import os

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

    if os.getenv("WORKFLOW_RUNNERS_STUB", "").lower() in ("1", "true", "yes"):
        from ._stub_testing import StubRunner

        stub = StubRunner()
        for name in [
            "log_agent",
            "k8s_agent",
            "metrics_agent",
            "tracing_agent",
            "code_agent",
            "change_agent",
            "critic_agent",
            "pipeline_agent",
            "impact_analyzer",
            "intent_parser",
        ]:
            reg.register(name, 1, stub)
        # tracing_agent manifest is at v2; stub must cover that version too.
        reg.register("tracing_agent", 2, stub)
        _registry = reg
        return reg

    from src.utils.llm_client import get_default_llm_client

    pipeline_llm = get_default_llm_client(agent_name="pipeline_agent")

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
    # tracing_agent's manifest ships at v2 (TA-PR1/PR2 additions); the
    # runner is backwards-compatible, so register it under both versions.
    _tracing_runner = TracingAgentRunner()
    reg.register("tracing_agent", 1, _tracing_runner)
    reg.register("tracing_agent", 2, _tracing_runner)
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

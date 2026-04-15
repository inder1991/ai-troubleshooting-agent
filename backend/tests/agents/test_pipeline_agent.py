from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.cicd.base import Build, DeployEvent, ResolveResult


def _event(source_id: str = "svc#1", name: str = "svc", status: str = "failed"):
    return DeployEvent(
        source="jenkins",
        source_id=source_id,
        name=name,
        status=status,
        started_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        url="https://j/svc/1",
    )


def _jenkins_client(name="prod"):
    c = MagicMock()
    c.source = "jenkins"
    c.name = name
    return c


@pytest.mark.asyncio
async def test_pipeline_agent_produces_finding_from_deploy_event():
    from src.agents.pipeline_agent import PipelineAgent

    fake = _jenkins_client()
    fake.list_deploy_events = AsyncMock(return_value=[_event()])
    fake.get_build_artifacts = AsyncMock(return_value=Build(
        event=_event(),
        parameters={},
        log_tail="error: boom",
        failed_stage="deploy",
    ))

    with patch(
        "src.agents.pipeline_agent.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(jenkins=[fake], argocd=[], errors=[])),
    ):
        llm = MagicMock()
        llm.invoke = AsyncMock(side_effect=[
            {"action": "list_recent_deploys", "args": {"hours": 2}},
            {"action": "get_deploy_details", "args": {"event_id": "svc#1"}},
            {"action": "finish", "args": {
                "finding": "Deploy svc#1 failed at stage 'deploy'",
                "root_cause": "error: boom",
            }},
        ])
        agent = PipelineAgent(llm=llm)
        result = await agent.run({"cluster_id": "c1", "time_window_minutes": 120})

    assert "svc#1" in result["finding"]
    assert result["root_cause"] == "error: boom"
    assert result["terminated_reason"] == "finished"


@pytest.mark.asyncio
async def test_pipeline_agent_stops_after_max_iterations():
    from src.agents.pipeline_agent import PipelineAgent

    with patch(
        "src.agents.pipeline_agent.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(jenkins=[], argocd=[], errors=[])),
    ):
        llm = MagicMock()
        llm.invoke = AsyncMock(return_value={
            "action": "list_recent_deploys", "args": {"hours": 1},
        })
        agent = PipelineAgent(llm=llm, max_iterations=4)
        result = await agent.run({"cluster_id": "c1"})

    assert result["terminated_reason"] == "max_iterations"
    assert llm.invoke.await_count == 4


@pytest.mark.asyncio
async def test_pipeline_agent_accepts_capability_input_model():
    from src.agents.pipeline_agent import PipelineAgent, PipelineCapabilityInput

    with patch(
        "src.agents.pipeline_agent.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(jenkins=[], argocd=[], errors=[])),
    ):
        llm = MagicMock()
        llm.invoke = AsyncMock(return_value={"action": "finish", "args": {"finding": "noop"}})
        agent = PipelineAgent(llm=llm)
        result = await agent.run(PipelineCapabilityInput(cluster_id="c1"))

    assert result["finding"] == "noop"


@pytest.mark.asyncio
async def test_pipeline_agent_tolerates_tool_errors():
    from src.agents.pipeline_agent import PipelineAgent

    bad = _jenkins_client("bad")
    bad.list_deploy_events = AsyncMock(side_effect=RuntimeError("boom"))
    good = _jenkins_client("good")
    good.list_deploy_events = AsyncMock(return_value=[_event("good#1", "web")])

    with patch(
        "src.agents.pipeline_agent.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(jenkins=[bad, good], argocd=[], errors=[])),
    ):
        llm = MagicMock()
        llm.invoke = AsyncMock(side_effect=[
            {"action": "list_recent_deploys", "args": {"hours": 1}},
            {"action": "finish", "args": {"finding": "survived"}},
        ])
        agent = PipelineAgent(llm=llm)
        result = await agent.run({"cluster_id": "c1"})

    assert result["finding"] == "survived"


@pytest.mark.asyncio
async def test_pipeline_agent_surfaces_resolver_errors():
    from src.agents.pipeline_agent import PipelineAgent
    from src.integrations.cicd.base import InstanceError

    with patch(
        "src.agents.pipeline_agent.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(
            jenkins=[],
            argocd=[],
            errors=[InstanceError(name="bad-jenkins", source="jenkins", message="auth failed")],
        )),
    ):
        llm = MagicMock()
        llm.invoke = AsyncMock(return_value={"action": "finish", "args": {"finding": "none"}})
        agent = PipelineAgent(llm=llm)
        result = await agent.run({"cluster_id": "c1"})

    assert result["resolver_errors"] == [
        {"name": "bad-jenkins", "source": "jenkins", "message": "auth failed"},
    ]

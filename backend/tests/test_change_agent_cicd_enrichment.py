"""Tests for ChangeAgent CI/CD pre-fetch enrichment."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.change_agent import _prefetch_cicd_events
from src.integrations.cicd.base import DeployEvent, ResolveResult


def _event(
    name: str = "checkout-api",
    source: str = "jenkins",
    status: str = "success",
) -> DeployEvent:
    return DeployEvent(
        source=source,
        source_id=f"{name}#1",
        name=name,
        status=status,
        started_at=datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 4, 11, 10, 5, tzinfo=timezone.utc),
        git_sha="abcdef1",
        git_repo="acme/checkout",
        git_ref="refs/heads/main",
        triggered_by="alice",
        url="https://jenkins.local/job/checkout-api/1",
        target="prod",
    )


def _fake_client(events=None, exc=None):
    m = MagicMock()
    m.source = "jenkins"
    m.name = "jenkins-prod"
    if exc is not None:
        m.list_deploy_events = AsyncMock(side_effect=exc)
    else:
        m.list_deploy_events = AsyncMock(return_value=events or [])
    return m


@pytest.mark.asyncio
async def test_change_agent_prefetch_includes_cicd_events():
    client = _fake_client(events=[_event(name="checkout-api")])
    resolve_result = ResolveResult(jenkins=[client], argocd=[], errors=[])

    ctx = {
        "cluster_id": "cluster-a",
        "namespace": "checkout",
    }
    incident_start = datetime(2026, 4, 11, 10, 30, tzinfo=timezone.utc)

    with patch(
        "src.agents.change_agent.resolve_cicd_clients",
        AsyncMock(return_value=resolve_result),
    ):
        events = await _prefetch_cicd_events(ctx, incident_start, "checkout")

    assert len(events) == 1
    assert events[0].name == "checkout-api"
    client.list_deploy_events.assert_awaited_once()
    # Confirm window bounds: since = incident - 2h, until = incident + 30m
    call_kwargs = client.list_deploy_events.await_args
    args, kwargs = call_kwargs
    since = args[0] if args else kwargs["since"]
    until = args[1] if len(args) > 1 else kwargs["until"]
    assert since == incident_start - timedelta(hours=2)
    assert until == incident_start + timedelta(minutes=30)


@pytest.mark.asyncio
async def test_change_agent_prefetch_returns_empty_when_no_clients():
    resolve_result = ResolveResult(jenkins=[], argocd=[], errors=[])
    ctx = {"cluster_id": None}
    incident_start = datetime(2026, 4, 11, 10, 30, tzinfo=timezone.utc)

    with patch(
        "src.agents.change_agent.resolve_cicd_clients",
        AsyncMock(return_value=resolve_result),
    ):
        events = await _prefetch_cicd_events(ctx, incident_start, "checkout")

    assert events == []


@pytest.mark.asyncio
async def test_change_agent_prefetch_tolerates_one_client_failing():
    good = _fake_client(events=[_event(name="checkout-api")])
    bad = _fake_client(exc=RuntimeError("boom"))
    resolve_result = ResolveResult(jenkins=[good, bad], argocd=[], errors=[])

    ctx = {"cluster_id": "cluster-a"}
    incident_start = datetime(2026, 4, 11, 10, 30, tzinfo=timezone.utc)

    with patch(
        "src.agents.change_agent.resolve_cicd_clients",
        AsyncMock(return_value=resolve_result),
    ):
        events = await _prefetch_cicd_events(ctx, incident_start, "checkout")

    assert len(events) == 1
    assert events[0].name == "checkout-api"

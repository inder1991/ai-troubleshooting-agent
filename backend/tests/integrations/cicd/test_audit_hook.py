from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.integrations.cicd.audit_hook as audit_hook
from src.integrations.cicd.argocd_client import ArgoCDClient
from src.integrations.cicd.audit_hook import record_cicd_read
from src.integrations.cicd.jenkins_client import JenkinsClient


@pytest.fixture
def _reset_singleton():
    """Reset the lazy module-level AuditLogger singleton around each test."""
    audit_hook._audit_logger = None
    yield
    audit_hook._audit_logger = None


@pytest.fixture
def _unmock_hook(monkeypatch):
    """Undo the autouse conftest patch so we can exercise the real hook."""
    monkeypatch.setattr(
        "src.integrations.cicd.jenkins_client.record_cicd_read",
        record_cicd_read,
    )
    monkeypatch.setattr(
        "src.integrations.cicd.argocd_client.record_cicd_read",
        record_cicd_read,
    )


# ---------- unit tests for record_cicd_read itself ----------

def test_record_cicd_read_calls_audit_logger_log(
    monkeypatch, _reset_singleton
):
    mock_logger = MagicMock()
    mock_cls = MagicMock(return_value=mock_logger)
    monkeypatch.setattr(
        "src.integrations.cicd.audit_hook.AuditLogger", mock_cls
    )

    record_cicd_read("jenkins", "prod", "list_deploy_events")

    mock_cls.assert_called_once_with()
    mock_logger._ensure_tables.assert_called_once_with()
    mock_logger.log.assert_called_once_with(
        entity_type="integration_cicd",
        entity_id="jenkins/prod",
        action="read:list_deploy_events",
        details=None,
        actor="system",
    )


def test_record_cicd_read_passes_details(monkeypatch, _reset_singleton):
    mock_logger = MagicMock()
    monkeypatch.setattr(
        "src.integrations.cicd.audit_hook.AuditLogger",
        MagicMock(return_value=mock_logger),
    )

    record_cicd_read("argocd", "staging", "health_check", details="probe=ok")

    mock_logger.log.assert_called_once_with(
        entity_type="integration_cicd",
        entity_id="argocd/staging",
        action="read:health_check",
        details="probe=ok",
        actor="system",
    )


def test_record_cicd_read_swallows_exceptions(monkeypatch, _reset_singleton):
    mock_logger = MagicMock()
    mock_logger.log.side_effect = RuntimeError("db exploded")
    monkeypatch.setattr(
        "src.integrations.cicd.audit_hook.AuditLogger",
        MagicMock(return_value=mock_logger),
    )

    # Must not raise.
    record_cicd_read("jenkins", "prod", "health_check")


def test_record_cicd_read_singleton_is_reused(monkeypatch, _reset_singleton):
    mock_logger = MagicMock()
    mock_cls = MagicMock(return_value=mock_logger)
    monkeypatch.setattr(
        "src.integrations.cicd.audit_hook.AuditLogger", mock_cls
    )

    record_cicd_read("jenkins", "a", "health_check")
    record_cicd_read("jenkins", "b", "health_check")

    assert mock_cls.call_count == 1
    assert mock_logger._ensure_tables.call_count == 1
    assert mock_logger.log.call_count == 2


# ---------- wiring tests for client read methods ----------

@pytest.mark.asyncio
async def test_jenkins_health_check_fires_hook(_mock_cicd_audit_hook):
    client = JenkinsClient(
        base_url="https://j.example",
        username="u",
        api_token="t",
        instance_name="prod",
    )
    client._get_json = AsyncMock(return_value={"mode": "NORMAL"})  # type: ignore

    assert await client.health_check() is True
    _mock_cicd_audit_hook.assert_any_call("jenkins", "prod", "health_check")


@pytest.mark.asyncio
async def test_jenkins_list_deploy_events_fires_hook(_mock_cicd_audit_hook):
    client = JenkinsClient(
        base_url="https://j.example",
        username="u",
        api_token="t",
        instance_name="prod",
    )
    client._get_json = AsyncMock(return_value={"jobs": []})  # type: ignore

    since = datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)
    until = datetime(2026, 4, 10, 23, 0, tzinfo=timezone.utc)
    await client.list_deploy_events(since, until)

    _mock_cicd_audit_hook.assert_any_call(
        "jenkins", "prod", "list_deploy_events"
    )


@pytest.mark.asyncio
async def test_jenkins_get_build_artifacts_fires_hook(_mock_cicd_audit_hook):
    from src.integrations.cicd.base import DeployEvent

    client = JenkinsClient(
        base_url="https://j.example",
        username="u",
        api_token="t",
        instance_name="prod",
    )
    client._get_json = AsyncMock(return_value={"actions": []})  # type: ignore
    client._get_text = AsyncMock(return_value="")  # type: ignore

    event = DeployEvent(
        source="jenkins",
        source_id="checkout-api#1847",
        name="checkout-api",
        status="success",
        started_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        finished_at=None,
        git_sha=None,
        git_repo=None,
        git_ref=None,
        triggered_by=None,
        url="",
        target=None,
    )
    await client.get_build_artifacts(event)

    _mock_cicd_audit_hook.assert_any_call(
        "jenkins", "prod", "get_build_artifacts"
    )


@pytest.mark.asyncio
async def test_argocd_health_check_fires_hook(_mock_cicd_audit_hook):
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value={"items": []})  # type: ignore

    assert await client.health_check() is True
    _mock_cicd_audit_hook.assert_any_call("argocd", "prod", "health_check")


@pytest.mark.asyncio
async def test_argocd_list_deploy_events_fires_hook(_mock_cicd_audit_hook):
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value={"items": []})  # type: ignore

    since = datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)
    until = datetime(2026, 4, 10, 23, 0, tzinfo=timezone.utc)
    await client.list_deploy_events(since, until)

    _mock_cicd_audit_hook.assert_any_call(
        "argocd", "prod", "list_deploy_events"
    )


@pytest.mark.asyncio
async def test_argocd_get_build_artifacts_fires_hook(_mock_cicd_audit_hook):
    from src.integrations.cicd.base import DeployEvent

    app = {
        "metadata": {"name": "checkout-api"},
        "status": {
            "health": {"status": "Healthy"},
            "resources": [],
        },
    }
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value={"items": [app]})  # type: ignore

    event = DeployEvent(
        source="argocd",
        source_id="checkout-api@abc",
        name="checkout-api",
        status="success",
        started_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        finished_at=None,
        git_sha=None,
        git_repo=None,
        git_ref=None,
        triggered_by=None,
        url="",
        target=None,
    )
    await client.get_build_artifacts(event)

    _mock_cicd_audit_hook.assert_any_call(
        "argocd", "prod", "get_build_artifacts"
    )

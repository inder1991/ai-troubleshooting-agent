from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.integrations.cicd.argocd_client import ArgoCDClient, _parse_iso
from src.integrations.cicd.base import CICDClientError, DeployEvent


APPS_PAYLOAD = {
    "items": [
        {
            "metadata": {"name": "checkout-api", "namespace": "argocd"},
            "spec": {
                "source": {"repoURL": "https://github.com/acme/checkout-api"},
                "destination": {"namespace": "prod"},
            },
            "status": {
                "sync": {"status": "Synced", "revision": "abc123"},
                "health": {"status": "Healthy"},
                "operationState": {
                    "startedAt": "2026-04-10T14:02:00Z",
                    "finishedAt": "2026-04-10T14:02:11Z",
                    "phase": "Succeeded",
                    "syncResult": {"revision": "abc123"},
                },
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_list_deploy_events_parses_argocd_sync():
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value=APPS_PAYLOAD)  # type: ignore
    since = datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc)
    until = datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc)
    events = await client.list_deploy_events(since, until)
    assert len(events) == 1
    ev = events[0]
    assert ev.source == "argocd"
    assert ev.name == "checkout-api"
    assert ev.status == "success"
    assert ev.git_sha == "abc123"
    assert ev.git_repo == "acme/checkout-api"
    assert ev.target == "prod"


@pytest.mark.asyncio
async def test_list_deploy_events_filters_by_target_namespace():
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value=APPS_PAYLOAD)  # type: ignore
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
        target_filter="staging",
    )
    assert events == []


@pytest.mark.asyncio
async def test_health_check_returns_true_on_valid_list():
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value={"items": []})  # type: ignore
    assert await client.health_check() is True


@pytest.mark.asyncio
async def test_list_deploy_events_skips_app_without_operation_state():
    payload = {
        "items": [
            {
                "metadata": {"name": "no-op-state", "namespace": "argocd"},
                "spec": {
                    "source": {"repoURL": "https://github.com/acme/no-op"},
                    "destination": {"namespace": "prod"},
                },
                "status": {
                    "sync": {"status": "Synced", "revision": "xyz"},
                    "health": {"status": "Healthy"},
                    # operationState missing
                },
            },
            {
                "metadata": {"name": "null-op-state", "namespace": "argocd"},
                "spec": {
                    "source": {"repoURL": "https://github.com/acme/null-op"},
                    "destination": {"namespace": "prod"},
                },
                "status": {
                    "operationState": None,
                },
            },
        ]
    }
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value=payload)  # type: ignore
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
    )
    assert events == []


@pytest.mark.asyncio
async def test_list_deploy_events_skips_app_outside_window():
    payload = {
        "items": [
            {
                "metadata": {"name": "old", "namespace": "argocd"},
                "spec": {
                    "source": {"repoURL": "https://github.com/acme/old"},
                    "destination": {"namespace": "prod"},
                },
                "status": {
                    "operationState": {
                        "startedAt": "2026-04-09T12:00:00Z",
                        "finishedAt": "2026-04-09T12:00:10Z",
                        "phase": "Succeeded",
                        "syncResult": {"revision": "old-sha"},
                    },
                },
            }
        ]
    }
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value=payload)  # type: ignore
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
    )
    assert events == []


@pytest.mark.asyncio
async def test_list_deploy_events_handles_missing_sync_result_revision():
    payload = {
        "items": [
            {
                "metadata": {"name": "fallback", "namespace": "argocd"},
                "spec": {
                    "source": {"repoURL": "https://github.com/acme/fallback"},
                    "destination": {"namespace": "prod"},
                },
                "status": {
                    "sync": {"status": "Synced", "revision": "fallback-sha"},
                    "health": {"status": "Healthy"},
                    "operationState": {
                        "startedAt": "2026-04-10T14:02:00Z",
                        "finishedAt": "2026-04-10T14:02:11Z",
                        "phase": "Succeeded",
                        # no syncResult
                    },
                },
            }
        ]
    }
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value=payload)  # type: ignore
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
    )
    assert len(events) == 1
    assert events[0].git_sha == "fallback-sha"


@pytest.mark.asyncio
async def test_get_build_artifacts_returns_sync_diff_with_unhealthy_resources():
    payload = {
        "items": [
            {
                "metadata": {"name": "checkout-api", "namespace": "argocd"},
                "spec": {
                    "source": {"repoURL": "https://github.com/acme/checkout-api"},
                    "destination": {"namespace": "prod"},
                },
                "status": {
                    "health": {"status": "Degraded"},
                    "resources": [
                        {"name": "r1", "status": "Synced"},
                        {"name": "r2", "status": "OutOfSync"},
                        {"name": "r3", "status": "OutOfSync"},
                    ],
                },
            }
        ]
    }
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value=payload)  # type: ignore
    event = DeployEvent(
        source="argocd",
        source_id="checkout-api@abc",
        name="checkout-api",
        status="success",
        started_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        url="https://argo.example/applications/checkout-api",
    )
    diff = await client.get_build_artifacts(event)
    assert diff.health == "degraded"
    assert len(diff.out_of_sync_resources) == 2
    assert all(r["status"] == "OutOfSync" for r in diff.out_of_sync_resources)


@pytest.mark.asyncio
async def test_get_build_artifacts_raises_parse_when_app_missing():
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value={"items": []})  # type: ignore
    event = DeployEvent(
        source="argocd",
        source_id="missing@abc",
        name="missing",
        status="success",
        started_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        url="https://argo.example/applications/missing",
    )
    with pytest.raises(CICDClientError) as exc_info:
        await client.get_build_artifacts(event)
    assert exc_info.value.kind == "parse"


@pytest.mark.asyncio
async def test_health_check_returns_false_on_auth_error():
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )

    async def fail(_path: str):
        raise CICDClientError(
            source="argocd", instance="prod", kind="auth", message="401",
        )

    client._get_json = fail  # type: ignore[assignment]
    assert await client.health_check() is False


@pytest.mark.asyncio
async def test_health_check_returns_false_on_network_error():
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )

    async def fail(_path: str):
        raise CICDClientError(
            source="argocd", instance="prod", kind="network", message="500",
        )

    client._get_json = fail  # type: ignore[assignment]
    assert await client.health_check() is False


@pytest.mark.asyncio
async def test_list_deploy_events_includes_boundary_equality():
    payload = {
        "items": [
            {
                "metadata": {"name": "at-since", "namespace": "argocd"},
                "spec": {
                    "source": {"repoURL": "https://github.com/acme/at-since"},
                    "destination": {"namespace": "prod"},
                },
                "status": {
                    "operationState": {
                        "startedAt": "2026-04-10T13:00:00Z",
                        "finishedAt": "2026-04-10T13:00:10Z",
                        "phase": "Succeeded",
                        "syncResult": {"revision": "sha-since"},
                    },
                },
            },
            {
                "metadata": {"name": "at-until", "namespace": "argocd"},
                "spec": {
                    "source": {"repoURL": "https://github.com/acme/at-until"},
                    "destination": {"namespace": "prod"},
                },
                "status": {
                    "operationState": {
                        "startedAt": "2026-04-10T15:00:00Z",
                        "finishedAt": "2026-04-10T15:00:10Z",
                        "phase": "Succeeded",
                        "syncResult": {"revision": "sha-until"},
                    },
                },
            },
        ]
    }
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value=payload)  # type: ignore
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
    )
    assert len(events) == 2
    names = {e.name for e in events}
    assert names == {"at-since", "at-until"}


def test_parse_iso_naive_defaults_to_utc():
    dt = _parse_iso("2026-04-10T14:00:00")
    assert dt is not None
    assert dt.tzinfo is timezone.utc
    assert _parse_iso(None) is None
    assert _parse_iso("bad-date") is None


@pytest.mark.asyncio
async def test_source_id_uses_sync_status_revision_fallback():
    payload = {
        "items": [
            {
                "metadata": {"name": "fallback-app", "namespace": "argocd"},
                "spec": {
                    "source": {
                        "repoURL": "https://github.com/acme/fallback-app",
                    },
                    "destination": {"namespace": "prod"},
                },
                "status": {
                    "sync": {
                        "status": "Synced",
                        "revision": "fallback-sha",
                    },
                    "health": {"status": "Healthy"},
                    "operationState": {
                        "startedAt": "2026-04-10T14:02:00Z",
                        "finishedAt": "2026-04-10T14:02:11Z",
                        "phase": "Succeeded",
                        "syncResult": {},
                    },
                },
            }
        ]
    }
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value=payload)  # type: ignore
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
    )
    assert len(events) == 1
    assert events[0].git_sha == "fallback-sha"
    assert events[0].source_id == "fallback-app@fallback-sha"


@pytest.mark.asyncio
async def test_list_deploy_events_rate_limit_raises_with_kind():
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )

    async def raise_rate_limit(_path: str):
        raise CICDClientError(
            source="argocd",
            instance="prod",
            kind="rate_limit",
            message="429",
        )

    client._get_json = raise_rate_limit  # type: ignore[assignment]
    with pytest.raises(CICDClientError) as exc_info:
        await client.list_deploy_events(
            datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
        )
    assert exc_info.value.kind == "rate_limit"

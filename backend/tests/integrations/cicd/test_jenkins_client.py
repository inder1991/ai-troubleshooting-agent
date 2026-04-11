from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.integrations.cicd.base import CICDClientError
from src.integrations.cicd.jenkins_client import JenkinsClient


JOBS_PAYLOAD = {
    "jobs": [
        {"name": "checkout-api", "url": "https://j.example/job/checkout-api/"},
    ]
}
JOB_PAYLOAD = {
    "builds": [
        {"number": 1847, "url": "https://j.example/job/checkout-api/1847/"},
    ]
}
BUILD_PAYLOAD = {
    "number": 1847,
    "result": "SUCCESS",
    "timestamp": 1775829600000,  # 2026-04-10T14:00:00Z
    "duration": 60000,
    "url": "https://j.example/job/checkout-api/1847/",
    "actions": [
        {"_class": "hudson.plugins.git.util.BuildData",
         "lastBuiltRevision": {"SHA1": "abc123"},
         "remoteUrls": ["https://github.com/acme/checkout-api.git"]},
        {"_class": "hudson.model.CauseAction",
         "causes": [{"userName": "ci-bot"}]},
    ],
}


def _mk_client(mock_get):
    client = JenkinsClient(
        base_url="https://j.example",
        username="u",
        api_token="t",
        instance_name="prod",
    )
    client._get_json = mock_get  # type: ignore[assignment]
    return client


@pytest.mark.asyncio
async def test_list_deploy_events_parses_builds_within_window():
    mock_get = AsyncMock(side_effect=[JOBS_PAYLOAD, JOB_PAYLOAD, BUILD_PAYLOAD])
    client = _mk_client(mock_get)

    since = datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc)
    until = datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc)
    events = await client.list_deploy_events(since, until)

    assert len(events) == 1
    ev = events[0]
    assert ev.source == "jenkins"
    assert ev.name == "checkout-api"
    assert ev.status == "success"
    assert ev.git_sha == "abc123"
    assert ev.git_repo == "acme/checkout-api"
    assert ev.triggered_by == "ci-bot"


@pytest.mark.asyncio
async def test_list_deploy_events_skips_builds_outside_window():
    old_build = {**BUILD_PAYLOAD, "timestamp": 0}
    mock_get = AsyncMock(side_effect=[JOBS_PAYLOAD, JOB_PAYLOAD, old_build])
    client = _mk_client(mock_get)
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
    )
    assert events == []


@pytest.mark.asyncio
async def test_list_deploy_events_raises_auth_error_on_401():
    async def raise_auth(*a, **kw):
        raise CICDClientError(
            source="jenkins", instance="prod", kind="auth", message="401",
        )
    client = _mk_client(AsyncMock(side_effect=raise_auth))

    with pytest.raises(CICDClientError) as exc_info:
        await client.list_deploy_events(
            datetime(2026, 4, 10, tzinfo=timezone.utc),
            datetime(2026, 4, 11, tzinfo=timezone.utc),
        )
    assert exc_info.value.kind == "auth"


@pytest.mark.asyncio
async def test_list_deploy_events_isolates_per_job_failures():
    """One failing job must not take down the whole sync."""
    good_job = {"name": "checkout-api", "url": "https://j.example/job/checkout-api/"}
    bad_job = {"name": "bad", "url": "https://j.example/job/bad/"}

    call_log: list[str] = []

    async def fake_get(path: str):
        call_log.append(path)
        if "/api/json?tree=jobs" in path:
            return {"jobs": [good_job, bad_job]}
        if path.startswith("/job/checkout-api/api"):
            return JOB_PAYLOAD
        if path.startswith("/job/checkout-api/1847"):
            return BUILD_PAYLOAD
        if path.startswith("/job/bad"):
            raise CICDClientError(
                source="jenkins", instance="prod",
                kind="network", message="500",
            )
        raise AssertionError(f"unexpected path: {path}")

    client = _mk_client(AsyncMock(side_effect=fake_get))
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
    )
    assert len(events) == 1
    assert events[0].name == "checkout-api"


@pytest.mark.asyncio
async def test_parse_build_uses_first_match_for_git_metadata():
    """Multi-SCM jobs emit multiple BuildData actions — first wins."""
    multi_scm_build = {
        **BUILD_PAYLOAD,
        "actions": [
            {"_class": "hudson.plugins.git.util.BuildData",
             "lastBuiltRevision": {"SHA1": "first-sha"},
             "remoteUrls": ["https://github.com/acme/first.git"]},
            {"_class": "hudson.plugins.git.util.BuildData",
             "lastBuiltRevision": {"SHA1": "second-sha"},
             "remoteUrls": ["https://github.com/acme/second.git"]},
            {"_class": "hudson.model.CauseAction",
             "causes": [{"userName": "ci-bot"}]},
        ],
    }
    mock_get = AsyncMock(side_effect=[JOBS_PAYLOAD, JOB_PAYLOAD, multi_scm_build])
    client = _mk_client(mock_get)
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
    )
    assert events[0].git_sha == "first-sha"
    assert events[0].git_repo == "acme/first"


@pytest.mark.asyncio
async def test_get_build_artifacts_returns_log_tail_and_failed_stage():
    from src.integrations.cicd.base import DeployEvent

    event = DeployEvent(
        source="jenkins",
        source_id="checkout-api#1847",
        name="checkout-api",
        status="failed",
        started_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        url="https://j.example/job/checkout-api/1847/",
    )

    detail = {
        **BUILD_PAYLOAD,
        "result": "FAILURE",
        "actions": [
            {"parameters": [{"name": "ENV", "value": "prod"}]},
        ],
    }
    log_text = "\n".join(f"line {i}" for i in range(250)) + "\n[Pipeline] stage 'deploy' FAILED"

    mock_get = AsyncMock(side_effect=[detail])
    client = _mk_client(mock_get)

    async def fake_log(path: str) -> str:
        assert path.endswith("/consoleText")
        return log_text

    client._get_text = fake_log  # type: ignore[assignment]

    build = await client.get_build_artifacts(event)
    assert build.event.source_id == "checkout-api#1847"
    assert build.parameters == {"ENV": "prod"}
    assert "line 249" in build.log_tail
    assert build.log_tail.count("\n") <= 210  # bounded
    assert build.failed_stage == "deploy"


@pytest.mark.asyncio
async def test_health_check_returns_true_on_200():
    mock_get = AsyncMock(return_value={"mode": "NORMAL"})
    client = _mk_client(mock_get)
    assert await client.health_check() is True


@pytest.mark.asyncio
async def test_health_check_returns_false_on_auth_error():
    async def fail(*a, **kw):
        raise CICDClientError(
            source="jenkins", instance="prod", kind="auth", message="401",
        )
    client = _mk_client(AsyncMock(side_effect=fail))
    assert await client.health_check() is False

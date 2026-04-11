from __future__ import annotations
from datetime import datetime, timezone

from src.integrations.cicd.base import (
    DeployEvent, Build, SyncDiff, DeliveryItem,
)


def test_deploy_event_roundtrips_required_fields():
    event = DeployEvent(
        source="jenkins",
        source_id="checkout-api#1847",
        name="checkout-api",
        status="success",
        started_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 4, 10, 14, 1, tzinfo=timezone.utc),
        git_sha="abc123",
        git_repo="acme/checkout-api",
        git_ref="main",
        triggered_by="ci-bot",
        url="https://jenkins.example/job/checkout-api/1847/",
        target="prod",
    )
    dumped = event.model_dump()
    assert dumped["source"] == "jenkins"
    assert dumped["status"] == "success"
    assert DeployEvent.model_validate(dumped) == event


def test_delivery_item_accepts_commit_kind_without_duration():
    item = DeliveryItem(
        kind="commit",
        id="abc123",
        title="fix: null guard on cart",
        source="github",
        source_instance="acme-github",
        status="committed",
        author="gunjan",
        git_sha="abc123",
        git_repo="acme/checkout-api",
        target="main",
        timestamp=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        duration_s=None,
        url="https://github.com/acme/checkout-api/commit/abc123",
    )
    assert item.kind == "commit"
    assert item.duration_s is None

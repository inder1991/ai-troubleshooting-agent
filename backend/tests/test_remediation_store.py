"""Tests for RemediationStore — SQLite persistence for plans + audit log."""
import os
import tempfile
import pytest


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from src.database.remediation_store import RemediationStore
    s = RemediationStore(db_path=path)
    yield s
    os.unlink(path)


def test_create_plan(store):
    plan = store.create_plan(
        profile_id="prof-1", action="vacuum",
        params={"table": "orders"}, sql_preview="VACUUM orders",
        impact_assessment="~30s", rollback_sql=None,
        requires_downtime=False, finding_id=None,
    )
    assert plan["plan_id"]
    assert plan["status"] == "pending"
    assert plan["action"] == "vacuum"


def test_get_plan(store):
    created = store.create_plan(
        profile_id="prof-1", action="vacuum",
        params={"table": "orders"}, sql_preview="VACUUM orders",
    )
    fetched = store.get_plan(created["plan_id"])
    assert fetched is not None
    assert fetched["plan_id"] == created["plan_id"]
    assert fetched["params"] == {"table": "orders"}


def test_update_plan_status(store):
    plan = store.create_plan(
        profile_id="prof-1", action="vacuum",
        params={}, sql_preview="VACUUM orders",
    )
    store.update_plan(plan["plan_id"], status="approved", approved_at="2026-03-09T00:00:00")
    updated = store.get_plan(plan["plan_id"])
    assert updated["status"] == "approved"
    assert updated["approved_at"] == "2026-03-09T00:00:00"


def test_list_plans(store):
    store.create_plan(profile_id="prof-1", action="vacuum", params={}, sql_preview="V1")
    store.create_plan(profile_id="prof-1", action="reindex", params={}, sql_preview="R1")
    store.create_plan(profile_id="prof-2", action="vacuum", params={}, sql_preview="V2")
    plans = store.list_plans("prof-1")
    assert len(plans) == 2
    filtered = store.list_plans("prof-1", status="pending")
    assert len(filtered) == 2


def test_add_audit_entry(store):
    entry = store.add_audit_entry(
        plan_id="plan-1", profile_id="prof-1", action="vacuum",
        sql_executed="VACUUM orders", status="success",
        before_state={"rows": 1000}, after_state={"rows": 1000},
    )
    assert entry["entry_id"]
    assert entry["status"] == "success"


def test_get_audit_log(store):
    store.add_audit_entry(
        plan_id="p1", profile_id="prof-1", action="vacuum",
        sql_executed="V1", status="success",
    )
    store.add_audit_entry(
        plan_id="p2", profile_id="prof-1", action="reindex",
        sql_executed="R1", status="failed", error="lock timeout",
    )
    log = store.get_audit_log("prof-1")
    assert len(log) == 2
    assert log[0]["action"] in ("vacuum", "reindex")

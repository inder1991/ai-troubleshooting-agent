"""Tests for RemediationEngine — saga orchestrator."""
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from src.database.remediation_store import RemediationStore
    from src.database.remediation_engine import RemediationEngine
    store = RemediationStore(db_path=path)
    adapter_registry = MagicMock()
    profile_store = MagicMock()
    e = RemediationEngine(
        plan_store=store,
        adapter_registry=adapter_registry,
        profile_store=profile_store,
        secret_key="test-secret-key-for-jwt",
    )
    yield e
    os.unlink(path)


def test_plan_creates_pending(engine):
    plan = engine.plan(
        profile_id="prof-1", action="vacuum",
        params={"table": "orders"},
    )
    assert plan["plan_id"]
    assert plan["status"] == "pending"
    assert plan["sql_preview"]
    assert "VACUUM" in plan["sql_preview"]


def test_plan_kill_query(engine):
    plan = engine.plan(
        profile_id="prof-1", action="kill_query",
        params={"pid": 12345},
    )
    assert "12345" in plan["sql_preview"]


def test_plan_create_index(engine):
    plan = engine.plan(
        profile_id="prof-1", action="create_index",
        params={"table": "orders", "columns": ["customer_id"], "unique": False},
    )
    assert "CREATE" in plan["sql_preview"]
    assert "customer_id" in plan["sql_preview"]


def test_plan_alter_config(engine):
    plan = engine.plan(
        profile_id="prof-1", action="alter_config",
        params={"param": "work_mem", "value": "64MB"},
    )
    assert "work_mem" in plan["sql_preview"]


def test_plan_failover_runbook(engine):
    plan = engine.plan(
        profile_id="prof-1", action="failover_runbook",
        params={},
    )
    assert plan["sql_preview"] == "-- Read-only runbook generation"
    assert plan["requires_downtime"] is False


def test_approve_generates_token(engine):
    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t"})
    result = engine.approve(plan["plan_id"])
    assert "approval_token" in result
    assert "expires_at" in result
    # Plan status should be approved
    updated = engine.get_plan(plan["plan_id"])
    assert updated["status"] == "approved"


def test_approve_rejects_non_pending(engine):
    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t"})
    engine.approve(plan["plan_id"])
    with pytest.raises(ValueError, match="not in pending status"):
        engine.approve(plan["plan_id"])


def test_reject_plan(engine):
    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t"})
    engine.reject(plan["plan_id"])
    updated = engine.get_plan(plan["plan_id"])
    assert updated["status"] == "rejected"


def test_list_plans(engine):
    engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t1"})
    engine.plan(profile_id="prof-1", action="reindex", params={"table": "t2"})
    plans = engine.list_plans("prof-1")
    assert len(plans) == 2


@pytest.mark.asyncio
async def test_execute_vacuum(engine):
    # Set up mock adapter
    mock_adapter = AsyncMock()
    mock_adapter.vacuum_table.return_value = {"success": True, "table": "orders"}
    engine._adapter_registry.get_by_profile.return_value = mock_adapter

    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "orders"})
    approval = engine.approve(plan["plan_id"])
    result = await engine.execute(plan["plan_id"], approval["approval_token"])
    assert result["status"] in ("completed", "success")
    mock_adapter.vacuum_table.assert_called_once()


@pytest.mark.asyncio
async def test_execute_invalid_token(engine):
    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t"})
    engine.approve(plan["plan_id"])
    with pytest.raises(ValueError, match="Invalid or expired"):
        await engine.execute(plan["plan_id"], "bad-token")


@pytest.mark.asyncio
async def test_execute_writes_audit_log(engine):
    mock_adapter = AsyncMock()
    mock_adapter.vacuum_table.return_value = {"success": True, "table": "t"}
    engine._adapter_registry.get_by_profile.return_value = mock_adapter

    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t"})
    approval = engine.approve(plan["plan_id"])
    await engine.execute(plan["plan_id"], approval["approval_token"])
    log = engine.get_audit_log("prof-1")
    assert len(log) == 1
    assert log[0]["status"] == "success"

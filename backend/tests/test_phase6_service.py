"""Phase 6: service layer — delete, rename, duplicate, rollback, run listing, rerun data."""

from __future__ import annotations

import asyncio
import json

import pytest

from src.contracts.registry import ContractRegistry
from src.contracts.service import init_registry
from src.workflows.repository import WorkflowRepository
from src.workflows.service import ActiveRunsError, WorkflowService


def _min_dag() -> dict:
    return {
        "inputs_schema": {
            "type": "object",
            "properties": {"service_name": {"type": "string"}},
            "required": ["service_name"],
        },
        "steps": [
            {
                "id": "s1",
                "agent": "log_agent",
                "agent_version": 1,
                "inputs": {
                    "service_name": {
                        "ref": {"from": "input", "path": "service_name"}
                    }
                },
            }
        ],
    }


@pytest.fixture
def contracts() -> ContractRegistry:
    return init_registry()


@pytest.fixture
def repo(tmp_path):
    db_path = str(tmp_path / "wf.db")
    r = WorkflowRepository(db_path)
    asyncio.new_event_loop().run_until_complete(r.init())
    return r


@pytest.fixture
def svc(repo, contracts) -> WorkflowService:
    return WorkflowService(repo=repo, contracts=contracts)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _create_wf_with_version(svc: WorkflowService, name: str = "test-wf") -> str:
    wf = await svc.create_workflow(name=name, description="d", created_by="t")
    await svc.create_version(wf["id"], _min_dag())
    return wf["id"]


# ---- delete ----

def test_delete_workflow(svc, repo):
    async def go():
        wf_id = await _create_wf_with_version(svc)
        result = await svc.delete_workflow(wf_id)
        assert result is True
        # not in list
        wfs = await svc.list_workflows()
        assert not any(w["id"] == wf_id for w in wfs)
        # get returns None
        assert await svc.get_workflow(wf_id) is None

    _run(go())


def test_delete_workflow_not_found(svc):
    async def go():
        result = await svc.delete_workflow("nonexistent-id")
        assert result is False

    _run(go())


def test_delete_workflow_with_active_runs_returns_conflict(svc, repo):
    async def go():
        wf_id = await _create_wf_with_version(svc)
        # create a run directly in the repo with 'running' status
        latest = await repo.get_latest_version(wf_id)
        run_id = await repo.create_run(
            workflow_version_id=latest["id"],
            inputs_json=json.dumps({"service_name": "x"}),
            idempotency_key=None,
        )
        await repo.update_run_status(run_id, "running")
        with pytest.raises(ActiveRunsError):
            await svc.delete_workflow(wf_id)

    _run(go())


def test_delete_idempotent(svc):
    async def go():
        wf_id = await _create_wf_with_version(svc)
        assert await svc.delete_workflow(wf_id) is True
        assert await svc.delete_workflow(wf_id) is True

    _run(go())


# ---- update ----

def test_rename_workflow(svc):
    async def go():
        wf_id = await _create_wf_with_version(svc)
        updated = await svc.update_workflow(wf_id, name="new-name")
        assert updated is not None
        assert updated["name"] == "new-name"

    _run(go())


def test_update_description(svc):
    async def go():
        wf_id = await _create_wf_with_version(svc)
        updated = await svc.update_workflow(wf_id, description="new desc")
        assert updated is not None
        assert updated["description"] == "new desc"

    _run(go())


# ---- duplicate ----

def test_duplicate_workflow(svc):
    async def go():
        wf_id = await _create_wf_with_version(svc, name="original")
        dup = await svc.duplicate_workflow(wf_id)
        assert dup["name"] == "original (copy)"
        assert dup["id"] != wf_id

    _run(go())


def test_duplicate_name_collision(svc):
    async def go():
        wf_id = await _create_wf_with_version(svc, name="original")
        dup1 = await svc.duplicate_workflow(wf_id)
        assert dup1["name"] == "original (copy)"
        dup2 = await svc.duplicate_workflow(wf_id)
        assert dup2["name"] == "original (copy 2)"

    _run(go())


# ---- rollback ----

def test_rollback_version(svc):
    async def go():
        wf_id = await _create_wf_with_version(svc)
        # create v2
        await svc.create_version(wf_id, _min_dag())
        # rollback to v1 -> creates v3
        result = await svc.rollback_version(wf_id, 1)
        assert result["version"] == 3
        assert result["workflow_id"] == wf_id
        assert "version_id" in result

    _run(go())


def test_rollback_nonexistent_version(svc):
    async def go():
        wf_id = await _create_wf_with_version(svc)
        with pytest.raises(LookupError):
            await svc.rollback_version(wf_id, 99)

    _run(go())


# ---- list_runs ----

def test_list_runs(svc, repo):
    async def go():
        wf_id = await _create_wf_with_version(svc)
        latest = await repo.get_latest_version(wf_id)
        await repo.create_run(
            workflow_version_id=latest["id"],
            inputs_json=json.dumps({"service_name": "a"}),
            idempotency_key=None,
        )
        result = await svc.list_runs(workflow_id=wf_id)
        assert "runs" in result
        assert "total" in result
        assert "limit" in result
        assert "offset" in result
        assert result["total"] == 1
        assert len(result["runs"]) == 1

    _run(go())


def test_list_runs_with_filters(svc, repo):
    async def go():
        wf_id = await _create_wf_with_version(svc)
        latest = await repo.get_latest_version(wf_id)
        run_id = await repo.create_run(
            workflow_version_id=latest["id"],
            inputs_json=json.dumps({"service_name": "a"}),
            idempotency_key=None,
        )
        await repo.update_run_status(run_id, "succeeded")
        # filter for succeeded
        result = await svc.list_runs(workflow_id=wf_id, statuses=["succeeded"])
        assert result["total"] == 1
        # filter for failed -> none
        result2 = await svc.list_runs(workflow_id=wf_id, statuses=["failed"])
        assert result2["total"] == 0

    _run(go())


# ---- rerun ----

def test_rerun_returns_version_and_inputs(svc, repo):
    async def go():
        wf_id = await _create_wf_with_version(svc)
        latest = await repo.get_latest_version(wf_id)
        inputs = {"service_name": "my-svc"}
        run_id = await repo.create_run(
            workflow_version_id=latest["id"],
            inputs_json=json.dumps(inputs),
            idempotency_key=None,
        )
        data = await svc.get_rerun_data(run_id)
        assert data["workflow_version_id"] == latest["id"]
        assert data["inputs"] == inputs

    _run(go())

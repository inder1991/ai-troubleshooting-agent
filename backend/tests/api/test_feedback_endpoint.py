"""Task 2.5 — POST /api/v4/investigations/{run_id}/feedback."""
from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.agents.confidence_calibrator import DEFAULT_PRIOR, ConfidenceCalibrator
from src.api.routes_feedback import feedback_router
from src.database.engine import get_engine, get_session


_RUN_ID = "test_run_feedback_r1"
_RUN_ID_NO_WINNERS = "test_run_feedback_r2"
_TEST_AGENTS = ("test_metrics_agent",)


@pytest_asyncio.fixture(autouse=True)
async def _isolate_feedback_tables():
    await get_engine().dispose(close=False)
    await _purge()
    yield
    await _purge()
    await get_engine().dispose(close=False)


async def _purge() -> None:
    async with get_session() as session:
        async with session.begin():
            await session.execute(
                text(
                    "DELETE FROM incident_feedback WHERE run_id = ANY(:ids)"
                ),
                {"ids": [_RUN_ID, _RUN_ID_NO_WINNERS]},
            )
            await session.execute(
                text(
                    "DELETE FROM investigation_dag_snapshot WHERE run_id = ANY(:ids)"
                ),
                {"ids": [_RUN_ID, _RUN_ID_NO_WINNERS]},
            )
            await session.execute(
                text("DELETE FROM agent_priors WHERE agent_name = ANY(:names)"),
                {"names": list(_TEST_AGENTS)},
            )


async def _seed_dag_snapshot(run_id: str, winning_agents: list[str] | None) -> None:
    payload: dict = {"schema_version": 1, "run_id": run_id, "steps": []}
    if winning_agents is not None:
        payload["winning_agents"] = winning_agents
    async with get_session() as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO investigation_dag_snapshot (run_id, payload, schema_version) "
                    "VALUES (:run_id, CAST(:payload AS JSON), 1)"
                ),
                {"run_id": run_id, "payload": _json(payload)},
            )


def _json(p: dict) -> str:
    import json as _j
    return _j.dumps(p)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(feedback_router)
    return app


@pytest.fixture
def client():
    app = _make_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_feedback_updates_priors_for_winning_agent(client):
    await _seed_dag_snapshot(_RUN_ID, winning_agents=["test_metrics_agent"])
    async with client as c:
        resp = await c.post(
            f"/api/v4/investigations/{_RUN_ID}/feedback",
            json={
                "was_correct": True,
                "actual_root_cause": "deploy regression",
                "submitter": "alice",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "recorded"
    assert body["priors_updated"] == ["test_metrics_agent"]
    assert body["idempotent_replay"] is False
    cal = ConfidenceCalibrator()
    assert (await cal.get_prior("test_metrics_agent")) > DEFAULT_PRIOR


@pytest.mark.asyncio
async def test_feedback_is_idempotent_on_run_submitter(client):
    await _seed_dag_snapshot(_RUN_ID, winning_agents=["test_metrics_agent"])
    async with client as c:
        for _ in range(3):
            resp = await c.post(
                f"/api/v4/investigations/{_RUN_ID}/feedback",
                json={"was_correct": True, "submitter": "alice"},
            )
            assert resp.status_code == 200
    # Only the first call should have nudged priors, so the total movement
    # equals a single EMA step — not three.
    cal = ConfidenceCalibrator()
    prior_one_step = await cal.get_prior("test_metrics_agent")
    # If it had applied three times, we'd see prior > DEFAULT_PRIOR + 0.03+;
    # a single EMA alpha=0.1 toward 1.0 from 0.65 adds ~0.035.
    assert DEFAULT_PRIOR < prior_one_step < DEFAULT_PRIOR + 0.05


@pytest.mark.asyncio
async def test_feedback_without_winning_agents_records_but_skips_priors(client):
    await _seed_dag_snapshot(_RUN_ID_NO_WINNERS, winning_agents=None)
    async with client as c:
        resp = await c.post(
            f"/api/v4/investigations/{_RUN_ID_NO_WINNERS}/feedback",
            json={"was_correct": False, "submitter": "bob"},
        )
    assert resp.status_code == 200
    assert resp.json()["priors_updated"] == []


@pytest.mark.asyncio
async def test_negative_feedback_pushes_prior_down(client):
    await _seed_dag_snapshot(_RUN_ID, winning_agents=["test_metrics_agent"])
    async with client as c:
        resp = await c.post(
            f"/api/v4/investigations/{_RUN_ID}/feedback",
            json={"was_correct": False, "submitter": "carol"},
        )
    assert resp.status_code == 200
    cal = ConfidenceCalibrator()
    assert (await cal.get_prior("test_metrics_agent")) < DEFAULT_PRIOR


@pytest.mark.asyncio
async def test_feedback_rejects_overlong_run_id(client):
    long_id = "x" * 65
    async with client as c:
        resp = await c.post(
            f"/api/v4/investigations/{long_id}/feedback",
            json={"was_correct": True, "submitter": "alice"},
        )
    assert resp.status_code == 400

"""Executor → OutboxWriter atomicity contract.

Spec test for Task 1.5: every ``run_step`` (and ``cancel``) commits the DAG
snapshot AND the outbox event in the same Postgres transaction. If the writer
raises mid-tx, neither row exists; sink-side failures during relay don't
affect the writer's commit (the relay re-drains).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.database.engine import get_engine, get_session
from src.workflows.event_schema import StepStatus
from src.workflows.investigation_executor import InvestigationExecutor
from src.workflows.investigation_types import InvestigationStepSpec
from src.workflows.outbox import OutboxWriter


_RUN_ATOMIC = f"executor-atomic-{uuid4().hex}"
_RUN_ROLLBACK = f"executor-rollback-{uuid4().hex}"
_RUN_CANCEL = f"executor-cancel-{uuid4().hex}"
_ALL_RUN_IDS = [_RUN_ATOMIC, _RUN_ROLLBACK, _RUN_CANCEL]


@pytest_asyncio.fixture(autouse=True)
async def _isolate_db():
    await get_engine().dispose(close=False)
    await _purge()
    yield
    await _purge()
    await get_engine().dispose(close=False)


async def _purge() -> None:
    async with get_session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM investigation_outbox WHERE run_id = ANY(:ids)"),
                {"ids": _ALL_RUN_IDS},
            )
            await session.execute(
                text("DELETE FROM investigation_dag_snapshot WHERE run_id = ANY(:ids)"),
                {"ids": _ALL_RUN_IDS},
            )


async def _fetch_outbox(run_id: str) -> list[dict]:
    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT run_id, seq, kind, payload, relayed_at "
                "FROM investigation_outbox WHERE run_id = :rid ORDER BY seq"
            ),
            {"rid": run_id},
        )
        return [dict(row._mapping) for row in result]


async def _fetch_snapshot(run_id: str) -> dict | None:
    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT run_id, payload, schema_version "
                "FROM investigation_dag_snapshot WHERE run_id = :rid"
            ),
            {"rid": run_id},
        )
        row = result.first()
        return dict(row._mapping) if row else None


class _StubWorkflowExecutor:
    def __init__(self, output: dict | None = None) -> None:
        self._output = output or {"findings": [{"msg": "ok"}]}
        self.calls = 0

    async def run(self, compiled, inputs, env=None, cancel_event=None, contracts=None):
        self.calls += 1
        step_id = compiled.topo_order[0]

        @dataclass
        class NodeState:
            status: str = "COMPLETED"
            output: dict | None = None
            error: dict | None = None
            started_at: str = "2026-04-17T00:00:00Z"
            ended_at: str = "2026-04-17T00:00:01Z"
            attempt: int = 1

        @dataclass
        class RunResult:
            status: str = "COMPLETED"
            node_states: dict = None
            error: dict | None = None

        return RunResult(
            status="COMPLETED",
            node_states={step_id: NodeState(output=self._output)},
        )


def _spec(step_id: str = "round-1-log_agent", agent: str = "log_agent") -> InvestigationStepSpec:
    return InvestigationStepSpec(
        step_id=step_id,
        agent=agent,
        idempotency_key=f"key-{step_id}",
    )


@pytest.mark.asyncio
async def test_step_completion_writes_event_and_state_atomically():
    """Each transition commits both an outbox row and the DAG snapshot.

    Two transitions per step (RUNNING + final) ⇒ two outbox rows with
    monotonic seq, plus one snapshot row whose ``last_sequence_number``
    matches the highest emitted seq.
    """
    writer = OutboxWriter()
    executor = InvestigationExecutor(
        run_id=_RUN_ATOMIC,
        writer=writer,
        workflow_executor=_StubWorkflowExecutor(),
    )

    result = await executor.run_step(_spec())
    assert result.status == StepStatus.SUCCESS

    rows = await _fetch_outbox(_RUN_ATOMIC)
    assert [r["seq"] for r in rows] == [1, 2]
    assert [r["kind"] for r in rows] == ["step_update", "step_update"]
    statuses = [r["payload"]["payload"]["status"] for r in rows]
    assert statuses == ["running", "success"]
    # Sinks haven't run in this test — rows are unrelayed.
    assert all(r["relayed_at"] is None for r in rows)

    snap = await _fetch_snapshot(_RUN_ATOMIC)
    assert snap is not None
    assert snap["payload"]["last_sequence_number"] == 2
    assert snap["payload"]["steps"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_writer_rollback_leaves_no_partial_state(monkeypatch):
    """If the outbox INSERT raises mid-tx, the snapshot is rolled back too.

    Simulates the audit's split-brain failure mode: the executor must never
    leave a snapshot row referencing a seq that has no outbox event.
    """
    writer = OutboxWriter()
    executor = InvestigationExecutor(
        run_id=_RUN_ROLLBACK,
        writer=writer,
        workflow_executor=_StubWorkflowExecutor(),
    )

    # Patch the writer's append_event so the first call inside any tx raises
    # AFTER update_dag has staged its UPSERT — exercises the atomic-commit
    # guarantee end-to-end (through executor → writer).
    from src.workflows import outbox as outbox_module

    original = outbox_module._Tx.append_event

    async def _boom(self, seq, kind, payload):
        raise RuntimeError("simulated outbox insert failure")

    monkeypatch.setattr(outbox_module._Tx, "append_event", _boom)

    with pytest.raises(RuntimeError, match="simulated outbox insert failure"):
        await executor.run_step(_spec())

    # Restore and verify nothing leaked.
    monkeypatch.setattr(outbox_module._Tx, "append_event", original)
    assert await _fetch_outbox(_RUN_ROLLBACK) == []
    assert await _fetch_snapshot(_RUN_ROLLBACK) is None


@pytest.mark.asyncio
async def test_cancel_writes_run_update_outbox_row():
    """cancel() commits a single ``run_update`` row with status=cancelled."""
    writer = OutboxWriter()
    executor = InvestigationExecutor(
        run_id=_RUN_CANCEL,
        writer=writer,
        workflow_executor=_StubWorkflowExecutor(),
    )

    await executor.cancel()

    rows = await _fetch_outbox(_RUN_CANCEL)
    assert len(rows) == 1
    assert rows[0]["kind"] == "run_update"
    assert rows[0]["seq"] == 1
    assert rows[0]["payload"]["payload"]["status"] == "cancelled"

    snap = await _fetch_snapshot(_RUN_CANCEL)
    assert snap is not None
    assert snap["payload"]["status"] == "cancelled"

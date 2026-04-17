"""InvestigationStore is now a thin Postgres reader for the DAG snapshot.

The in-memory + Redis fallback (audit P0 #5) was removed in Task 1.5; writes
go through OutboxWriter. These tests cover the read path only.
"""
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.database.engine import get_engine, get_session
from src.workflows.event_schema import StepStatus
from src.workflows.investigation_store import InvestigationStore
from src.workflows.investigation_types import VirtualDag, VirtualStep
from src.workflows.outbox import OutboxWriter


_RUN_RT = f"store-rt-{uuid4().hex}"
_RUN_DELETE = f"store-del-{uuid4().hex}"
_ALL_RUN_IDS = [_RUN_RT, _RUN_DELETE]


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


def _sample_dag(run_id: str) -> VirtualDag:
    dag = VirtualDag(run_id=run_id)
    dag.append_step(
        VirtualStep(
            step_id="round-1-log-agent",
            agent="log_agent",
            depends_on=[],
            status=StepStatus.SUCCESS,
            round=1,
        )
    )
    dag.last_sequence_number = 3
    dag.current_round = 1
    return dag


async def _seed_via_writer(dag: VirtualDag, seq: int = 1) -> None:
    writer = OutboxWriter()
    async with writer.transaction(run_id=dag.run_id) as tx:
        await tx.update_dag(dag.to_dict())
        await tx.append_event(seq=seq, kind="step_update", payload={"step_id": "x"})


@pytest.mark.asyncio
async def test_load_returns_persisted_dag():
    dag = _sample_dag(_RUN_RT)
    await _seed_via_writer(dag)

    store = InvestigationStore()
    loaded = await store.load_dag(_RUN_RT)
    assert loaded is not None
    assert loaded.run_id == _RUN_RT
    assert len(loaded.steps) == 1
    assert loaded.steps[0].step_id == "round-1-log-agent"
    assert loaded.last_sequence_number == 3


@pytest.mark.asyncio
async def test_load_nonexistent_returns_none():
    store = InvestigationStore()
    assert await store.load_dag(f"missing-{uuid4().hex}") is None


@pytest.mark.asyncio
async def test_delete_removes_snapshot():
    dag = _sample_dag(_RUN_DELETE)
    await _seed_via_writer(dag)

    store = InvestigationStore()
    assert await store.load_dag(_RUN_DELETE) is not None

    await store.delete_dag(_RUN_DELETE)
    assert await store.load_dag(_RUN_DELETE) is None

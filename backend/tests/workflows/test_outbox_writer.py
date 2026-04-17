"""OutboxWriter atomicity contract.

Both the DAG snapshot UPSERT and the outbox INSERT must commit (or roll back)
together. Closes audit finding #6 — "emit succeeds but save fails."
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.database.engine import get_engine, get_session
from src.workflows.outbox import OutboxWriter


_TEST_RUN_IDS = ("r1", "r2")


@pytest_asyncio.fixture(autouse=True)
async def _isolate_db():
    """Dispose engine + scrub the two run_ids this module writes to.

    Local-scope fixture (rather than promoting the database/conftest.py
    engine-disposal fixture to all workflow tests) keeps blast radius small —
    most workflow tests don't touch Postgres.
    """
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
                {"ids": list(_TEST_RUN_IDS)},
            )
            await session.execute(
                text("DELETE FROM investigation_dag_snapshot WHERE run_id = ANY(:ids)"),
                {"ids": list(_TEST_RUN_IDS)},
            )


async def fetch_outbox(run_id: str) -> list[dict]:
    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT run_id, seq, kind, payload "
                "FROM investigation_outbox WHERE run_id = :rid ORDER BY seq"
            ),
            {"rid": run_id},
        )
        return [dict(row._mapping) for row in result]


async def fetch_dag_snapshot(run_id: str) -> dict | None:
    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT run_id, payload, schema_version "
                "FROM investigation_dag_snapshot WHERE run_id = :rid"
            ),
            {"rid": run_id},
        )
        row = result.first()
        if row is None:
            return None
        mapping = dict(row._mapping)
        payload = mapping["payload"]
        if isinstance(payload, dict) and "last_sequence_number" in payload:
            mapping["last_sequence_number"] = payload["last_sequence_number"]
        return mapping


@pytest.mark.asyncio
async def test_writer_atomically_persists_event_and_state():
    dag_dict = {
        "schema_version": 1,
        "run_id": "r1",
        "steps": [{"step_id": "s1", "status": "RUNNING"}],
        "last_sequence_number": 5,
    }

    writer = OutboxWriter()
    async with writer.transaction(run_id="r1") as tx:
        await tx.update_dag(dag_dict)
        await tx.append_event(
            seq=5, kind="step_update", payload={"step_id": "s1"}
        )

    rows = await fetch_outbox("r1")
    assert len(rows) == 1
    assert rows[0]["seq"] == 5
    assert rows[0]["kind"] == "step_update"
    assert rows[0]["payload"] == {"step_id": "s1"}

    snap = await fetch_dag_snapshot("r1")
    assert snap is not None
    assert snap["last_sequence_number"] == 5
    assert snap["schema_version"] == 1


@pytest.mark.asyncio
async def test_writer_rolls_back_on_event_failure():
    dag_dict = {
        "schema_version": 1,
        "run_id": "r2",
        "steps": [],
        "last_sequence_number": 0,
    }

    writer = OutboxWriter()
    with pytest.raises(RuntimeError):
        async with writer.transaction(run_id="r2") as tx:
            await tx.update_dag(dag_dict)
            raise RuntimeError("simulated emit prep failure")

    assert await fetch_dag_snapshot("r2") is None
    assert await fetch_outbox("r2") == []


@pytest.mark.asyncio
async def test_writer_upserts_dag_on_repeated_writes():
    """update_dag called twice in the same tx ends up as a single row."""
    writer = OutboxWriter()
    async with writer.transaction(run_id="r1") as tx:
        await tx.update_dag({"schema_version": 1, "last_sequence_number": 1})
        await tx.update_dag({"schema_version": 1, "last_sequence_number": 2})
        await tx.append_event(seq=2, kind="step_update", payload={"x": 1})

    snap = await fetch_dag_snapshot("r1")
    assert snap is not None
    assert snap["last_sequence_number"] == 2

    async with writer.transaction(run_id="r1") as tx:
        await tx.update_dag({"schema_version": 1, "last_sequence_number": 3})
        await tx.append_event(seq=3, kind="step_update", payload={"x": 2})

    snap = await fetch_dag_snapshot("r1")
    assert snap is not None
    assert snap["last_sequence_number"] == 3
    assert len(await fetch_outbox("r1")) == 2


@pytest.mark.asyncio
async def test_duplicate_seq_raises_integrity_error():
    """Outbox uniqueness on (run_id, seq) — caller bug surfaces as an error."""
    from sqlalchemy.exc import IntegrityError

    writer = OutboxWriter()
    async with writer.transaction(run_id="r1") as tx:
        await tx.update_dag({"schema_version": 1, "last_sequence_number": 1})
        await tx.append_event(seq=1, kind="step_update", payload={})

    with pytest.raises(IntegrityError):
        async with writer.transaction(run_id="r1") as tx:
            await tx.update_dag({"schema_version": 1, "last_sequence_number": 1})
            await tx.append_event(seq=1, kind="step_update", payload={})

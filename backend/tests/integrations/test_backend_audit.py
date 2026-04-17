"""Task 3.15 — backend call audit."""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.database.engine import get_engine, get_session
from src.integrations.backend_audit import BackendAudit, hash_query, timed_call


_TEST_RUN_IDS = ("audit_test_r1", "audit_test_r2")


@pytest_asyncio.fixture(autouse=True)
async def _isolate():
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
                    "DELETE FROM backend_call_audit WHERE run_id = ANY(:ids)"
                ),
                {"ids": list(_TEST_RUN_IDS)},
            )


async def _fetch(run_id: str) -> list[dict]:
    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT run_id, agent, tool, backend, query_hash, "
                "response_code, duration_ms, bytes, error "
                "FROM backend_call_audit WHERE run_id = :rid ORDER BY id"
            ),
            {"rid": run_id},
        )
        return [dict(row._mapping) for row in result]


class TestWriting:
    @pytest.mark.asyncio
    async def test_every_tool_call_writes_audit_row(self):
        audit = BackendAudit()
        audit.record(
            run_id="audit_test_r1",
            agent="metrics_agent",
            tool="prometheus.query_instant",
            backend="prometheus",
            params={"q": "up{namespace=\"x\"}"},
            response_code=200,
            duration_ms=42,
            bytes_=1234,
        )
        await audit.flush()
        rows = await _fetch("audit_test_r1")
        assert len(rows) == 1
        assert rows[0]["backend"] == "prometheus"
        assert rows[0]["duration_ms"] == 42
        assert rows[0]["bytes"] == 1234

    @pytest.mark.asyncio
    async def test_error_string_is_truncated(self):
        audit = BackendAudit()
        audit.record(
            run_id="audit_test_r1",
            agent="log_agent",
            tool="elk.search",
            backend="elasticsearch",
            params={"q": "foo"},
            response_code=500,
            duration_ms=10,
            error="x" * 2000,
        )
        await audit.flush()
        rows = await _fetch("audit_test_r1")
        assert len(rows[0]["error"]) <= 1024


class TestHashStable:
    def test_same_params_same_hash(self):
        assert hash_query("elk.search", {"q": "a"}) == hash_query("elk.search", {"q": "a"})

    def test_dict_ordering_doesnt_affect_hash(self):
        assert hash_query("elk.search", {"a": 1, "b": 2}) == hash_query("elk.search", {"b": 2, "a": 1})


class TestBoundedQueue:
    @pytest.mark.asyncio
    async def test_queue_full_drops_oldest_counts_drop(self):
        audit = BackendAudit(queue_max=3)
        for i in range(10):
            audit.record(
                run_id="audit_test_r1",
                agent="a",
                tool="t",
                backend="b",
                params={"i": i},
                response_code=200,
                duration_ms=1,
            )
        snap = audit.snapshot()
        assert snap["queued"] <= 3
        assert snap["drops"] >= 1


class TestTimedContext:
    @pytest.mark.asyncio
    async def test_timed_call_records_on_success(self):
        audit = BackendAudit()
        async with timed_call(
            audit,
            run_id="audit_test_r1",
            agent="metrics_agent",
            tool="prometheus.query_instant",
            backend="prometheus",
            params={"q": "up"},
        ) as ctx:
            await asyncio.sleep(0.01)
            ctx["response_code"] = 200
            ctx["bytes"] = 42
        await audit.flush()
        rows = await _fetch("audit_test_r1")
        assert len(rows) == 1
        assert rows[0]["response_code"] == 200
        assert rows[0]["duration_ms"] >= 10

    @pytest.mark.asyncio
    async def test_timed_call_records_on_exception(self):
        audit = BackendAudit()
        with pytest.raises(RuntimeError):
            async with timed_call(
                audit,
                run_id="audit_test_r1",
                agent="metrics_agent",
                tool="prometheus.query_instant",
                backend="prometheus",
                params={"q": "up"},
            ) as ctx:
                raise RuntimeError("boom")
        await audit.flush()
        rows = await _fetch("audit_test_r1")
        assert len(rows) == 1
        assert "RuntimeError" in rows[0]["error"]

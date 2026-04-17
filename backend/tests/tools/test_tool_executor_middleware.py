"""Stage K.2/K.3/K.4 — tool_executor middleware integration.

Verifies that when ``ToolExecutor`` is constructed with run_id + agent_name
+ audit + budget + cache, every execute() invocation flows through the
full middleware stack: budget charge -> cache lookup -> audit-wrapped
handler. When the optional args are omitted, behaviour is identical to
pre-Phase-3.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.agents.budget import BudgetExceeded, InvestigationBudget
from src.database.engine import get_engine, get_session
from src.integrations.backend_audit import BackendAudit
from src.tools.result_cache import ResultCache
from src.tools.tool_executor import ToolExecutor
from src.tools.tool_result import ToolResult


_TEST_RUN_ID = "tool_executor_middleware_test_r1"


@pytest_asyncio.fixture(autouse=True)
async def _isolate():
    await get_engine().dispose(close=False)
    await _purge()
    yield
    await _purge()
    await get_engine().dispose(close=False)


async def _purge():
    async with get_session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM backend_call_audit WHERE run_id = :r"),
                {"r": _TEST_RUN_ID},
            )


async def _fetch_audit():
    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT tool, backend, response_code, duration_ms, error "
                "FROM backend_call_audit WHERE run_id = :r ORDER BY id"
            ),
            {"r": _TEST_RUN_ID},
        )
        return [dict(row._mapping) for row in result]


class _StubExecutor(ToolExecutor):
    """Override HANDLERS + a single handler so we don't need real backends."""

    HANDLERS = {"_stub_tool": "_stub_handler"}  # type: ignore[assignment]

    def __init__(self, *args, **kwargs):
        super().__init__({}, *args, **kwargs)
        self.stub_calls = 0

    def _validate_params(self, intent, params):  # type: ignore[override]
        return None

    async def _stub_handler(self, params):
        self.stub_calls += 1
        return ToolResult(
            success=True,
            intent="_stub_tool",
            raw_output='{"value": 42}',
            summary="stub ok",
            evidence_snippets=[],
            evidence_type="log",
            domain="logs",
        )


# Ensure the stub is in the per-handler backend map so audit gets 'unknown'
# which is fine — assertions below use tool (intent) rather than backend.


class TestMiddlewareOffByDefault:
    @pytest.mark.asyncio
    async def test_no_middleware_when_constructor_args_omitted(self):
        ex = _StubExecutor()
        result = await ex.execute("_stub_tool", {"q": "test"})
        assert result.success is True
        assert ex.stub_calls == 1
        # No audit rows written
        assert await _fetch_audit() == []


class TestAuditFires:
    @pytest.mark.asyncio
    async def test_every_call_writes_audit_row(self):
        audit = BackendAudit()
        ex = _StubExecutor(
            run_id=_TEST_RUN_ID,
            agent_name="stub_agent",
            audit=audit,
        )
        await ex.execute("_stub_tool", {"q": "test"})
        await audit.flush()
        rows = await _fetch_audit()
        assert len(rows) == 1
        assert rows[0]["tool"] == "_stub_tool"
        assert rows[0]["response_code"] == 200
        assert rows[0]["duration_ms"] >= 0


class TestBudgetEnforced:
    @pytest.mark.asyncio
    async def test_budget_exceeded_raises(self):
        budget = InvestigationBudget(max_tool_calls=2)
        ex = _StubExecutor(
            run_id=_TEST_RUN_ID,
            agent_name="stub_agent",
            budget=budget,
        )
        await ex.execute("_stub_tool", {"q": "1"})
        await ex.execute("_stub_tool", {"q": "2"})
        with pytest.raises(BudgetExceeded):
            await ex.execute("_stub_tool", {"q": "3"})
        # Third call should NOT have hit the handler
        assert ex.stub_calls == 2


class TestCacheShortCircuits:
    @pytest.mark.asyncio
    async def test_duplicate_call_is_served_from_cache(self):
        cache = ResultCache()
        budget = InvestigationBudget(max_tool_calls=10)
        ex = _StubExecutor(
            run_id=_TEST_RUN_ID,
            agent_name="stub_agent",
            cache=cache,
            budget=budget,
        )
        r1 = await ex.execute("_stub_tool", {"q": "same"})
        r2 = await ex.execute("_stub_tool", {"q": "same"})
        assert r1.raw_output == r2.raw_output
        # Handler ran once; the second call was a cache HIT.
        assert ex.stub_calls == 1
        # But budget charges both — cache HIT doesn't refund (policy
        # choice: budget tracks 'tool-call intents', not 'backend hits').
        snap = budget.snapshot()
        assert snap["tool_calls"] == 2

    @pytest.mark.asyncio
    async def test_different_params_miss_cache(self):
        cache = ResultCache()
        ex = _StubExecutor(run_id=_TEST_RUN_ID, cache=cache)
        await ex.execute("_stub_tool", {"q": "a"})
        await ex.execute("_stub_tool", {"q": "b"})
        assert ex.stub_calls == 2


class TestAllTogether:
    @pytest.mark.asyncio
    async def test_budget_cache_audit_compose_cleanly(self):
        audit = BackendAudit()
        budget = InvestigationBudget(max_tool_calls=10)
        cache = ResultCache()
        ex = _StubExecutor(
            run_id=_TEST_RUN_ID,
            agent_name="stub_agent",
            audit=audit,
            budget=budget,
            cache=cache,
        )
        await ex.execute("_stub_tool", {"q": "x"})
        await ex.execute("_stub_tool", {"q": "x"})  # cache HIT
        await ex.execute("_stub_tool", {"q": "y"})  # cache MISS
        await audit.flush()
        rows = await _fetch_audit()
        # Only MISSes produce audit rows (cache HIT short-circuits).
        assert len(rows) == 2
        # Handler ran twice (once per unique param).
        assert ex.stub_calls == 2

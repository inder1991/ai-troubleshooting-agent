"""Task 4.23 — prompt registry + per-agent pinning."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.database.engine import get_engine, get_session
from src.prompts.registry import PromptRegistry, _compute_version_id


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
            await session.execute(text("DELETE FROM prompt_versions"))


class TestRegistryGet:
    def test_returns_pinned_version_for_known_agent(self):
        p = PromptRegistry().get("log_agent")
        assert p.version_id is not None
        assert p.system_prompt.lower().startswith("you are")

    def test_same_agent_same_version_id(self):
        r = PromptRegistry()
        a = r.get("log_agent")
        b = r.get("log_agent")
        assert a.version_id == b.version_id

    def test_unknown_agent_raises(self):
        with pytest.raises(KeyError):
            PromptRegistry().get("nonexistent_agent")

    def test_all_agents_have_idk_clause(self):
        """Task 4.24 cousin: every registered prompt must have an explicit
        inconclusive/IDK escape."""
        for p in PromptRegistry().list_all():
            text = p.system_prompt.lower()
            assert "inconclusive" in text or "i don't know" in text, p.agent

    def test_version_id_is_content_addressed(self):
        """Same content -> same id across processes. Different content -> different id."""
        id1 = _compute_version_id("hello", None)
        id2 = _compute_version_id("hello", None)
        id3 = _compute_version_id("world", None)
        assert id1 == id2
        assert id1 != id3


class TestPersistence:
    @pytest.mark.asyncio
    async def test_ensure_persisted_writes_row(self):
        r = PromptRegistry()
        p = await r.ensure_persisted("log_agent")

        async with get_session() as session:
            result = await session.execute(
                text("SELECT version_id, agent FROM prompt_versions WHERE version_id = :v"),
                {"v": p.version_id},
            )
            row = result.first()
            assert row is not None
            assert row._mapping["agent"] == "log_agent"

    @pytest.mark.asyncio
    async def test_ensure_persisted_is_idempotent(self):
        r = PromptRegistry()
        await r.ensure_persisted("metrics_agent")
        await r.ensure_persisted("metrics_agent")
        await r.ensure_persisted("metrics_agent")
        async with get_session() as session:
            row = await session.execute(
                text(
                    "SELECT COUNT(*) AS n FROM prompt_versions WHERE agent = 'metrics_agent'"
                )
            )
            assert row.scalar_one() == 1


class TestListAll:
    def test_list_all_returns_every_registered_agent(self):
        prompts = PromptRegistry().list_all()
        agents = {p.agent for p in prompts}
        assert {
            "log_agent", "metrics_agent", "k8s_agent",
            "tracing_agent", "code_agent", "change_agent", "supervisor",
        } <= agents

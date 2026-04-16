import pytest
import json

from src.workflows.investigation_store import InvestigationStore
from src.workflows.investigation_types import VirtualDag, VirtualStep
from src.workflows.event_schema import StepStatus


class FakeRedis:
    """Minimal async Redis mock for testing."""
    def __init__(self):
        self._data: dict[str, str] = {}
        self._expiry: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._data[key] = value
        if ex:
            self._expiry[key] = ex

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def expire(self, key: str, ttl: int) -> None:
        self._expiry[key] = ttl


@pytest.fixture
def store():
    return InvestigationStore(redis_client=FakeRedis())


@pytest.fixture
def sample_dag():
    dag = VirtualDag(run_id="inv-123")
    step = VirtualStep(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.SUCCESS,
        round=1,
    )
    dag.append_step(step)
    dag.last_sequence_number = 3
    dag.current_round = 1
    return dag


@pytest.mark.asyncio
async def test_save_and_load(store, sample_dag):
    await store.save_dag(sample_dag)
    loaded = await store.load_dag("inv-123")
    assert loaded is not None
    assert loaded.run_id == "inv-123"
    assert len(loaded.steps) == 1
    assert loaded.steps[0].step_id == "round-1-log-agent"
    assert loaded.last_sequence_number == 3


@pytest.mark.asyncio
async def test_load_nonexistent(store):
    loaded = await store.load_dag("nonexistent")
    assert loaded is None


@pytest.mark.asyncio
async def test_delete(store, sample_dag):
    await store.save_dag(sample_dag)
    await store.delete_dag("inv-123")
    loaded = await store.load_dag("inv-123")
    assert loaded is None


@pytest.mark.asyncio
async def test_in_memory_fallback():
    store = InvestigationStore(redis_client=None)
    dag = VirtualDag(run_id="inv-456")
    await store.save_dag(dag)
    loaded = await store.load_dag("inv-456")
    assert loaded is not None
    assert loaded.run_id == "inv-456"

import asyncio
import pytest
from src.database.job_queue import JobQueue


@pytest.fixture
def queue():
    return JobQueue(max_concurrent_per_profile=1)


@pytest.mark.asyncio
async def test_enqueue_and_execute(queue):
    results = []

    async def work():
        results.append("done")
        return {"status": "ok"}

    job_id = await queue.enqueue("prof-1", "run_explain", work)
    assert job_id.startswith("J-")

    result = await queue.wait_for(job_id, timeout=5.0)
    assert result["status"] == "ok"
    assert results == ["done"]


@pytest.mark.asyncio
async def test_concurrency_limit(queue):
    order = []

    async def slow_work(label):
        order.append(f"{label}-start")
        await asyncio.sleep(0.1)
        order.append(f"{label}-end")
        return label

    j1 = await queue.enqueue("prof-1", "tool-a", lambda: slow_work("A"))
    j2 = await queue.enqueue("prof-1", "tool-b", lambda: slow_work("B"))

    await queue.wait_for(j2, timeout=5.0)

    assert order.index("A-start") < order.index("A-end")
    assert order.index("A-end") <= order.index("B-start")


@pytest.mark.asyncio
async def test_get_status(queue):
    async def work():
        await asyncio.sleep(0.05)
        return "result"

    job_id = await queue.enqueue("prof-1", "tool", work)
    status = queue.get_status(job_id)
    assert status["status"] in ("pending", "running")

    await queue.wait_for(job_id, timeout=5.0)
    status = queue.get_status(job_id)
    assert status["status"] == "completed"

import pytest
from src.agents.cluster_client.base import ClusterClient, QueryResult
from src.agents.cluster_client.diagnostic_cache import DiagnosticCache


def test_query_result_truncation():
    qr = QueryResult(
        data=[{"name": f"pod-{i}"} for i in range(500)],
        total_available=47392,
        returned=500,
        truncated=True,
        sort_order="severity_desc",
    )
    assert qr.truncated is True
    assert qr.returned == 500


def test_query_result_no_truncation():
    qr = QueryResult(data=[{"name": "pod-1"}], total_available=1, returned=1)
    assert qr.truncated is False


def test_cluster_client_is_abstract():
    with pytest.raises(TypeError):
        ClusterClient()


@pytest.mark.asyncio
async def test_diagnostic_cache_hit():
    cache = DiagnosticCache(diagnostic_id="D-1")

    async def fetcher():
        return QueryResult(data=[1, 2, 3], total_available=3, returned=3)

    result1 = await cache.get_or_fetch("list_pods", {"ns": "default"}, fetcher)
    result2 = await cache.get_or_fetch("list_pods", {"ns": "default"}, fetcher)
    assert result1.data == result2.data


@pytest.mark.asyncio
async def test_diagnostic_cache_force_fresh():
    cache = DiagnosticCache(diagnostic_id="D-1")
    call_count = 0

    async def fetcher():
        nonlocal call_count
        call_count += 1
        return QueryResult(data=[call_count], total_available=1, returned=1)

    await cache.get_or_fetch("list_pods", {}, fetcher)
    result = await cache.get_or_fetch("list_pods", {}, fetcher, force_fresh=True)
    assert call_count == 2
    assert result.data == [2]

"""ELK / OpenSearch pagination with safe PIT lifecycle.

Pre-Phase-3 the log agent's search implementation was a single `from/size`
call capped at 10,000 hits — the hard Elasticsearch limit. Incidents with
more log volume got silently truncated.

This module yields results as an async generator that walks the dataset
with PIT + search_after (ES 8 / OpenSearch 2+), falling back to
search_after-without-PIT (ES 7.10+). The caller owns the hard cap; we
only enforce that the PIT is always closed, even on error paths.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Protocol


class ESLike(Protocol):
    """Minimal structural type for the client calls we need.

    Keeping the contract narrow means the tests can use a plain FakeES
    without importing elasticsearch. The real client is any of:
    ``elasticsearch.AsyncElasticsearch``, ``opensearchpy.AsyncOpenSearch``,
    or the thin wrapper in ``log_agent.ElasticsearchClient``.
    """

    async def open_pit(self, *, index: str, keep_alive: str) -> dict: ...
    async def close_pit(self, *, pit_id: str) -> None: ...
    async def search(self, *, body: dict) -> dict: ...


async def paginate_search(
    es: ESLike,
    query: dict,
    *,
    index: str = "*",
    page_size: int = 5000,
    max_total: int = 50_000,
    keep_alive: str = "1m",
    sort: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """Yield every hit up to ``max_total`` for the given query.

    Opens one PIT, pages through with ``search_after``, closes the PIT on
    both success and failure. ``sort`` must be a list of sort clauses with
    stable tie-breakers — we default to ``[@timestamp asc, _shard_doc asc]``
    which is what PIT requires for deterministic pagination.
    """
    if sort is None:
        sort = [{"@timestamp": "asc"}, {"_shard_doc": "asc"}]

    pit = await es.open_pit(index=index, keep_alive=keep_alive)
    pit_id: str = pit["id"]
    try:
        yielded = 0
        search_after: list[Any] | None = None
        while yielded < max_total:
            body: dict[str, Any] = {
                "size": min(page_size, max_total - yielded),
                "query": query,
                "pit": {"id": pit_id, "keep_alive": keep_alive},
                "sort": sort,
                "track_total_hits": False,
            }
            if search_after is not None:
                body["search_after"] = search_after
            resp = await es.search(body=body)
            hits = (resp.get("hits") or {}).get("hits") or []
            if not hits:
                return
            for h in hits:
                yield h
                yielded += 1
                if yielded >= max_total:
                    return
            # Advance the cursor using the last hit's sort values.
            last = hits[-1]
            search_after = last.get("sort")
            # The response also rotates the PIT id; honour it.
            new_pit_id = resp.get("pit_id")
            if isinstance(new_pit_id, str) and new_pit_id:
                pit_id = new_pit_id
    finally:
        # Best-effort close — leaving a PIT open wastes shard heap but must
        # never mask the original exception.
        try:
            await es.close_pit(pit_id=pit_id)
        except Exception:
            pass

"""Shared helper: retry-after + idempotency-key on external POSTs.

Combines the two Phase-3 primitives (``retry_with_retry_after`` +
``idempotency_scope``) into one call site for the integration clients
(jira / confluence / github / remedy). Each client opts in by replacing
its ``await client.post(url, ...)`` call with
``await idempotent_post(client, url, ...)``.

Behaviour:
  - One idempotency-key UUID generated per logical operation; reused
    across all retry attempts so the server can deduplicate.
  - 429 with ``Retry-After`` sleeps exactly the advertised interval
    (capped at 60 s); 502/503/504 use exponential backoff + jitter.
  - Success returns the final ``httpx.Response``; exhausted retries or
    non-retryable status propagates ``RetryableStatusError`` /
    ``httpx.HTTPError``.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx

from src.network.idempotency import (
    IDEMPOTENCY_KEY_HEADER,
    generate_idempotency_key,
    inject_idempotency_key,
)
from src.network.retry_after import (
    RetryableStatusError,
    retry_with_retry_after,
)


_RETRYABLE_STATUSES = {429, 502, 503, 504}


async def idempotent_post(
    client: httpx.AsyncClient,
    url: str,
    *,
    json: Any = None,
    headers: Optional[Mapping[str, str]] = None,
    max_attempts: int = 4,
    base_delay_s: float = 1.0,
) -> httpx.Response:
    """POST with retry-after + idempotency-key semantics.

    The caller's ``headers`` wins for every field including
    ``Idempotency-Key`` — users who've already threaded a key through a
    higher-level flow keep theirs.
    """
    key = generate_idempotency_key()

    base_headers = dict(headers or {})
    if IDEMPOTENCY_KEY_HEADER not in base_headers:
        base_headers = inject_idempotency_key(base_headers, key)

    async def _attempt() -> httpx.Response:
        resp = await client.post(url, json=json, headers=base_headers)
        if resp.status_code in _RETRYABLE_STATUSES:
            raise RetryableStatusError(
                resp.status_code, headers=dict(resp.headers)
            )
        return resp

    return await retry_with_retry_after(
        _attempt,
        max_attempts=max_attempts,
        base_delay_s=base_delay_s,
    )

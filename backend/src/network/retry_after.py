"""Retry-After-aware async retry helper.

Usage:
    async def call():
        return await http_client.get(...)

    result = await retry_with_retry_after(call, max_attempts=4)

A 429 with ``Retry-After`` skips the usual exponential backoff for that
attempt and sleeps exactly the advertised interval (capped at 60 s so a
malicious upstream can't wedge us). Other retryable statuses (502/503/504)
keep exponential backoff + jitter.

This is a peer to ``src/agents/retry.py``. That module is widely wired;
rather than surgery on every call-site, new code calls this helper
directly and the existing decorator becomes a legacy path to migrate off.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class RetryableStatusError(RuntimeError):
    """Raised by a caller-supplied shim when the HTTP status warrants retry.

    Carries the response status + headers so the helper can read
    ``Retry-After``. Callers that want Retry-After honouring must raise
    this from their callable on 429/502/503/504 (instead of returning the
    response).
    """

    def __init__(self, status: int, headers: dict[str, str] | None = None):
        super().__init__(f"retryable http {status}")
        self.status = status
        self.headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}


_RETRY_AFTER_MAX_S: float = 60.0
_RETRYABLE_STATUSES = {429, 502, 503, 504}


def parse_retry_after(value: str | None) -> Optional[float]:
    """Parse a Retry-After header value into seconds.

    Accepts either an integer seconds form ("2") or an HTTP-date form
    ("Wed, 21 Oct 2015 07:28:00 GMT"). Returns ``None`` for unparseable
    values — caller should then fall back to exponential backoff.
    """
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", v):
        try:
            return max(0.0, float(v))
        except ValueError:
            return None
    try:
        when = parsedate_to_datetime(v)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = (when - datetime.now(timezone.utc)).total_seconds()
    return max(0.0, delta)


async def retry_with_retry_after(
    call: Callable[[], Awaitable[Any]],
    *,
    max_attempts: int = 4,
    base_delay_s: float = 1.0,
    max_retry_after_s: float = _RETRY_AFTER_MAX_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Any:
    """Invoke ``call`` up to ``max_attempts`` times, honouring Retry-After.

    ``call`` must raise ``RetryableStatusError`` for HTTP 429/502/503/504
    (attaching the response headers so we can read Retry-After). Other
    exceptions propagate unchanged on the first failure — this helper
    doesn't retry on connection errors; the lower-level retry helper in
    ``agents/retry.py`` handles that class of failure.
    """
    last_error: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await call()
        except RetryableStatusError as e:
            last_error = e
            if e.status not in _RETRYABLE_STATUSES:
                # Shouldn't happen if the caller follows the contract, but
                # don't retry a status we didn't opt in to.
                raise
            if attempt >= max_attempts:
                raise
            ra = parse_retry_after(e.headers.get("retry-after"))
            if ra is not None and e.status == 429:
                # 429 with Retry-After: sleep exactly the advertised value
                # (capped). Skip exponential backoff — the server told us.
                delay = min(ra, max_retry_after_s)
                logger.info(
                    "Retry-After honoured: sleeping %.2fs before attempt %d/%d",
                    delay, attempt + 1, max_attempts,
                )
            else:
                # Exponential backoff + jitter for other retryable statuses
                # (or 429 without a Retry-After header).
                delay = base_delay_s * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.info(
                    "Backoff %.2fs before attempt %d/%d after HTTP %d",
                    delay, attempt + 1, max_attempts, e.status,
                )
            await sleep(delay)
    # Exhausted without success — re-raise the last recorded error.
    assert last_error is not None
    raise last_error

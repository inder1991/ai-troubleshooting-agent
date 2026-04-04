"""Retry wrapper for cluster client calls."""
from __future__ import annotations

import asyncio
import functools
import logging

logger = logging.getLogger(__name__)


def with_retry(retries: int = 2, backoff: float = 1.5):
    """
    Decorator: retry an async function on exception with exponential backoff.

    Args:
        retries: Number of retry attempts after the first failure (total attempts = retries + 1).
        backoff: Base wait time in seconds; wait = backoff ** attempt_number.
    """
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < retries:
                        wait = backoff ** attempt
                        logger.warning(
                            "Cluster call %s failed (attempt %d/%d), retrying in %.2fs: %s",
                            fn.__name__, attempt + 1, retries + 1, wait, exc,
                        )
                        await asyncio.sleep(wait)
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator

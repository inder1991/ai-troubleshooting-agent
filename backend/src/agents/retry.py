"""
Retry logic with exponential backoff for agent HTTP calls.
"""

import asyncio
import functools
import logging
import random

import requests

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {502, 503, 504}
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator that retries a function on transient failures.

    Retries on ConnectionError, Timeout, and HTTP 502/503/504.
    Does NOT retry on 401/403 (auth failures).
    Uses exponential backoff with jitter.
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    return result
                except RETRYABLE_EXCEPTIONS as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                        logger.warning(
                            "Retry %d/%d for %s after %s (delay %.1fs)",
                            attempt + 1, max_retries, func.__name__, type(e).__name__, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise
                except requests.exceptions.HTTPError as e:
                    if e.response is not None and e.response.status_code in RETRYABLE_STATUS_CODES:
                        last_exception = e
                        if attempt < max_retries:
                            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                            logger.warning(
                                "Retry %d/%d for %s after HTTP %d (delay %.1fs)",
                                attempt + 1, max_retries, func.__name__,
                                e.response.status_code, delay,
                            )
                            await asyncio.sleep(delay)
                        else:
                            raise
                    else:
                        # Non-retryable HTTP error (e.g. 401, 403, 404)
                        raise

            raise last_exception  # type: ignore

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator

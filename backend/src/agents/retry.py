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


def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0, service_name: str | None = None):
    """Decorator that retries a function on transient failures.

    Retries on ConnectionError, Timeout, and HTTP 502/503/504.
    Does NOT retry on 401/403 (auth failures).
    Uses exponential backoff with jitter.

    If ``service_name`` is set, callers may pass ``_circuit_breaker``
    (a :class:`RedisCircuitBreaker`) as a kwarg.  When present the
    decorator will short-circuit when the breaker is open and will
    record successes / failures automatically.
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            cb = kwargs.pop("_circuit_breaker", None)

            # --- circuit-breaker pre-check ---
            if cb and service_name and await cb.is_open(service_name):
                retry_after = await cb.get_retry_after(service_name)
                return f'{{"error": "circuit_open", "service": "{service_name}", "retry_after_s": {retry_after or 0}}}'

            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    if cb and service_name:
                        await cb.record_success(service_name)
                    return result
                except RETRYABLE_EXCEPTIONS as e:
                    if cb and service_name:
                        await cb.record_failure(service_name)
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
                        if cb and service_name:
                            await cb.record_failure(service_name)
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

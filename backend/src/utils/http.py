"""Q17 P — mandatory retry + timeout on outbound httpx.

Every outbound call goes through a `with_retry`-decorated helper.
Bare httpx.AsyncClient().get() is banned (the dependency_policy check
in Sprint H.1a enforces). This module provides the canonical decorator
and a couple of pre-wrapped helpers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

T = TypeVar("T")

DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_ATTEMPTS = 3
RETRYABLE_STATUSES = {502, 503, 504, 408, 429}


def with_retry(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    initial_delay: float = 0.5,
    max_delay: float = 8.0,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator. Wraps an async function in tenacity retry with
    exponential jitter. Retries on httpx.NetworkError + httpx.TimeoutException
    by default."""

    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def wrapped(*args: Any, **kwargs: Any) -> T:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential_jitter(initial=initial_delay, max=max_delay),
                retry=retry_if_exception_type((
                    httpx.NetworkError, httpx.TimeoutException,
                )),
                reraise=True,
            ):
                with attempt:
                    return await fn(*args, **kwargs)
            raise RuntimeError("unreachable")  # safety net for type-checkers

        return wrapped

    return deco


# Pre-wrapped helpers — the canonical safe outbound primitives.

@with_retry()
async def http_get(url: str, *, timeout: float = DEFAULT_TIMEOUT_S, **kwargs: Any) -> httpx.Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        response = await client.get(url, **kwargs)
        response.raise_for_status()
        return response


@with_retry()
async def http_post(
    url: str, *, json: Any = None, timeout: float = DEFAULT_TIMEOUT_S, **kwargs: Any
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        response = await client.post(url, json=json, **kwargs)
        response.raise_for_status()
        return response

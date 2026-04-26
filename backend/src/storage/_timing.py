"""Q12 hard gate: every StorageGateway method must complete in
<= single_query_max_ms (default 100ms in test fixtures)."""

from __future__ import annotations

import functools
import time
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class QueryBudgetExceeded(Exception):
    """Raised when a @timed_query exceeds its declared budget."""


def timed_query(max_ms: int = 100) -> Callable[
    [Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]
]:
    """Decorator. Wraps an async gateway method; raises QueryBudgetExceeded
    if elapsed exceeds max_ms.

    H-25: works on async-only methods (gateway is async per Q7); calling
    on a sync function is a programmer error and surfaces immediately
    via TypeError when the decorated function is awaited.
    """

    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapped(*args: Any, **kwargs: Any) -> T:
            start = time.perf_counter()
            result = await fn(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            if elapsed_ms > max_ms:
                raise QueryBudgetExceeded(
                    f"{fn.__qualname__} took {elapsed_ms:.1f}ms "
                    f"(budget: {max_ms}ms)"
                )
            return result

        return wrapped

    return deco

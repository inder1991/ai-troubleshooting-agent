"""Cancellation propagation — let asyncio.CancelledError reach the bottom.

Python 3.8+ made ``asyncio.CancelledError`` a ``BaseException`` so it
doesn't slip through bare ``except Exception`` blocks. But we still have
``except Exception`` sites that manually re-raise CancelledError or
swallow it outright. This module provides the utility that the react loop
and the streaming LLM clients use to shape cancellation + an awaiter
that honours external cancel tokens alongside asyncio cancellation.

Contract:
  - ``ensure_cancel_reraised(exc)`` — call this inside any ``except
    Exception`` block; if the exception is actually a CancelledError,
    it re-raises it. No-op otherwise.
  - ``CancelGuard`` — context manager that converts an external cancel
    flag (threading.Event or similar) to a ``CancelledError`` on await.
  - ``cancellable_call(awaitable, token)`` — wait on an awaitable but
    cancel it if ``token.is_set()`` trips first.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable


def ensure_cancel_reraised(exc: BaseException) -> None:
    """If ``exc`` is a CancelledError, re-raise it; otherwise do nothing.

    Use inside broad ``except Exception`` handlers to avoid accidentally
    swallowing cancellation. Example:

        try:
            await some_llm_call()
        except Exception as e:
            ensure_cancel_reraised(e)
            log_and_continue(e)
    """
    if isinstance(exc, asyncio.CancelledError):
        raise exc


class CancelToken:
    """Thread-safe cancel flag (not tied to any single loop).

    The supervisor writes ``token.set()`` when a user cancels the
    investigation; the react loop reads ``token.is_set()`` between
    steps. It doesn't replace asyncio cancellation — the two layer.
    """

    def __init__(self) -> None:
        self._set: bool = False

    def set(self) -> None:
        self._set = True

    def is_set(self) -> bool:
        return self._set


class CancelledByToken(asyncio.CancelledError):
    """Raised when a CancelToken trips inside ``cancellable_call``."""


async def cancellable_call(awaitable: Awaitable[Any], token: CancelToken) -> Any:
    """Await ``awaitable`` but raise ``CancelledByToken`` if ``token`` trips.

    Checks the token every ~50ms so a user cancel doesn't wait on a
    long-running LLM call. The underlying task is cancelled properly so
    its ``finally`` blocks run (releasing the http client, etc.).
    """
    task = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            if token.is_set():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise CancelledByToken("investigation cancelled by user")
            try:
                return await asyncio.wait_for(asyncio.shield(task), timeout=0.05)
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        # Local cancellation — forward to the inner task.
        if not task.done():
            task.cancel()
        raise


@asynccontextmanager
async def cancel_guard(token: CancelToken) -> AsyncIterator[None]:
    """Context that raises ``CancelledByToken`` immediately on entry/exit if
    the token is set. Use to scope critical sections against cancel."""
    if token.is_set():
        raise CancelledByToken("investigation cancelled before section entry")
    try:
        yield
    finally:
        if token.is_set():
            raise CancelledByToken("investigation cancelled during section")

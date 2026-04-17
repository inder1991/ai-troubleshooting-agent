"""Idempotency-Key helpers for external POST/PUT/DELETE calls.

The failure mode this closes: a client issues ``POST /issues`` to Jira,
network hiccups mid-response, the retry creates a second issue. With an
Idempotency-Key, the server de-duplicates same-key requests so the retry
is a no-op.

Contract:
  1. Generate one key per LOGICAL operation (UUID4).
  2. Pass the SAME key on every retry of that operation (not a fresh one
     per attempt — the whole point is that the server sees the repeat).
  3. Keys are passed via the ``Idempotency-Key`` header; they're at least
     32 chars (UUID4 hex form is 32 chars, the UUID string form is 36).

This module owns key generation + an ``idempotent_post`` context manager
that wraps retryable POSTs. The integration clients (jira/github/…) adopt
it once this lands.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


IDEMPOTENCY_KEY_HEADER: str = "Idempotency-Key"
MIN_KEY_LENGTH: int = 32


def generate_idempotency_key() -> str:
    """Return a fresh UUID4 hex string (32 chars).

    32-char minimum is deliberate: Jira + GitHub both recommend >= 32 so
    this matches the strictest upstream requirement.
    """
    return uuid.uuid4().hex


def inject_idempotency_key(headers: dict | None, key: str) -> dict:
    """Return a new headers dict with the key set. Does not mutate input.

    If the caller already set an Idempotency-Key, keep theirs — callers
    who've already threaded a key through a higher-level flow win.
    """
    if len(key) < MIN_KEY_LENGTH:
        raise ValueError(
            f"idempotency key must be >= {MIN_KEY_LENGTH} chars; got {len(key)}"
        )
    merged: dict[str, Any] = dict(headers or {})
    merged.setdefault(IDEMPOTENCY_KEY_HEADER, key)
    return merged


@asynccontextmanager
async def idempotency_scope() -> AsyncIterator[str]:
    """Yield a single idempotency key for the duration of a logical op.

    Usage:
        async with idempotency_scope() as key:
            for attempt in range(3):
                await retry_with_retry_after(
                    lambda: client.post(url, headers=inject_idempotency_key(None, key), ...)
                )
    """
    key = generate_idempotency_key()
    yield key

"""Per-account concurrency guard for cloud sync."""
from __future__ import annotations

import asyncio


class SyncConcurrencyGuard:
    """Ensures max 1 concurrent sync per account across all tiers."""

    def __init__(self) -> None:
        self._active: dict[str, asyncio.Lock] = {}

    def get_lock(self, account_id: str) -> asyncio.Lock:
        if account_id not in self._active:
            self._active[account_id] = asyncio.Lock()
        return self._active[account_id]

"""Async SQLAlchemy engine + session factory for the hardening Postgres store.

This is the single entry point for all *new* persistence (outbox, audit log,
agent priors, eval store, etc. — see the diagnostic-workflow-hardening plan).

Legacy SQLite paths (`data/debugduck.db`, `data/diagnostics.db`) are NOT
touched here; they remain wired through the existing modules in
`src/database/`.

Operating rules (from plan §"Operating rules"):
- No silent fallbacks: if Postgres is unreachable, callers get a real error.
- ``DATABASE_URL`` is the single source of truth and must be an asyncpg URL.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Default points at the dev docker-compose service so a fresh checkout works
# after `docker-compose -f docker-compose.dev.yml up -d postgres`.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://diagnostic:diagnostic@localhost:5432/diagnostic_dev",
)

_engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

_Session = async_sessionmaker(
    _engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine."""
    return _engine


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an ``AsyncSession`` bound to the process-wide engine.

    Usage::

        async with get_session() as session:
            result = await session.execute(text("SELECT 1"))
    """
    async with _Session() as session:
        yield session

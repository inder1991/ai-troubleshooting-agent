"""Tests for the async SQLAlchemy engine + session factory.

These tests require a running Postgres instance reachable via the
``DATABASE_URL`` environment variable (defaults to the local docker-compose
service in ``docker-compose.dev.yml``).
"""
import pytest
from sqlalchemy import text

from src.database.engine import get_engine, get_session


@pytest.mark.asyncio
async def test_get_session_yields_working_session():
    async with get_session() as s:
        result = await s.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_get_engine_returns_async_engine():
    from sqlalchemy.ext.asyncio import AsyncEngine

    engine = get_engine()
    assert isinstance(engine, AsyncEngine)

import pytest_asyncio

from src.database.engine import get_engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_between_tests():
    await get_engine().dispose(close=False)
    yield
    await get_engine().dispose(close=False)

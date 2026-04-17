import pytest
from sqlalchemy import inspect
from src.database.engine import get_engine

@pytest.mark.asyncio
async def test_outbox_table_exists():
    async with get_engine().begin() as conn:
        def check(sync):
            insp = inspect(sync)
            assert "investigation_outbox" in insp.get_table_names()
            cols = {c["name"] for c in insp.get_columns("investigation_outbox")}
            assert {"id","run_id","seq","kind","payload","created_at","relayed_at"} <= cols
        await conn.run_sync(check)

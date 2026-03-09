"""Tests for adapter write operations using MockDatabaseAdapter."""
import pytest
from src.database.adapters.mock_adapter import MockDatabaseAdapter


@pytest.fixture
def adapter():
    return MockDatabaseAdapter(engine="postgresql", host="localhost", port=5432, database="testdb")


@pytest.mark.asyncio
async def test_kill_query(adapter):
    await adapter.connect()
    result = await adapter.kill_query(pid=12345)
    assert result["success"] is True
    assert result["pid"] == 12345


@pytest.mark.asyncio
async def test_vacuum_table(adapter):
    await adapter.connect()
    result = await adapter.vacuum_table("orders")
    assert result["success"] is True
    assert result["table"] == "orders"


@pytest.mark.asyncio
async def test_vacuum_table_full(adapter):
    await adapter.connect()
    result = await adapter.vacuum_table("orders", full=True, analyze=True)
    assert result["full"] is True
    assert result["analyze"] is True


@pytest.mark.asyncio
async def test_reindex_table(adapter):
    await adapter.connect()
    result = await adapter.reindex_table("orders")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_create_index(adapter):
    await adapter.connect()
    result = await adapter.create_index("orders", ["customer_id"], name="idx_orders_cust")
    assert result["success"] is True
    assert result["index_name"] == "idx_orders_cust"


@pytest.mark.asyncio
async def test_drop_index(adapter):
    await adapter.connect()
    result = await adapter.drop_index("idx_orders_cust")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_alter_config(adapter):
    await adapter.connect()
    result = await adapter.alter_config("work_mem", "64MB")
    assert result["success"] is True
    assert result["param"] == "work_mem"


@pytest.mark.asyncio
async def test_alter_config_blocked_param(adapter):
    await adapter.connect()
    with pytest.raises(ValueError, match="not in allowlist"):
        await adapter.alter_config("data_directory", "/tmp")


@pytest.mark.asyncio
async def test_get_config_recommendations(adapter):
    await adapter.connect()
    recs = await adapter.get_config_recommendations()
    assert isinstance(recs, list)
    assert len(recs) > 0
    assert recs[0]["param"]


@pytest.mark.asyncio
async def test_generate_failover_runbook(adapter):
    await adapter.connect()
    runbook = await adapter.generate_failover_runbook()
    assert isinstance(runbook, dict)
    assert "steps" in runbook
    assert len(runbook["steps"]) > 0

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from src.api.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_start_db_session(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v4/session/start", json={
            "capability": "database_diagnostics",
            "serviceName": "orders-db-primary",
            "profile_id": "prof-1",
            "extra": {
                "time_window": "1h",
                "focus": ["queries", "connections"],
                "database_type": "postgres",
                "sampling_mode": "standard",
                "include_explain_plans": False,
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data.get("capability") == "database_diagnostics"

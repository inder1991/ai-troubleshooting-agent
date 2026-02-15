import pytest
from httpx import AsyncClient, ASGITransport
from src.api.main import create_app


@pytest.mark.asyncio
async def test_start_session():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v4/session/start", json={
            "serviceName": "order-service",
            "elkIndex": "app-logs-*",
            "timeframe": "1h"
        })
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "started"


@pytest.mark.asyncio
async def test_list_sessions():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v4/sessions")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_session_not_found():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v4/session/nonexistent/status")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_health_endpoint():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_health_returns_status():
    from src.api.routes_v4 import health_check
    with patch("src.api.routes_v4.check_redis", new_callable=AsyncMock, return_value={"status": "up", "latency_ms": 2}), \
         patch("src.api.routes_v4.check_circuit_breakers", return_value={}):
        result = await health_check()
    assert result["status"] in ("healthy", "degraded", "unhealthy")
    assert "checks" in result

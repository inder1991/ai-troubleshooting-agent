import pytest
from unittest.mock import AsyncMock, patch
from src.agents.discovery_fallback import DiscoveryFallback


@pytest.fixture
def fallback():
    return DiscoveryFallback(
        cli_tool="kubectl",
        cluster_url="https://k8s.example.com:6443",
        token="test-token-123",
    )


class TestDiscoveryFallback:
    @pytest.mark.asyncio
    async def test_discover_namespaces(self, fallback):
        with patch("src.agents.discovery_fallback.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = (0, "default kube-system monitoring app-prod", "")
            namespaces = await fallback.discover_namespaces()
            assert namespaces == ["default", "kube-system", "monitoring", "app-prod"]
            mock_cmd.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_error_pods(self, fallback):
        with patch("src.agents.discovery_fallback.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = (0, "api-server-1   Failed\npayment-svc-3   CrashLoopBackOff", "")
            pods = await fallback.discover_error_pods("app-prod")
            assert len(pods) == 2
            assert pods[0] == {"name": "api-server-1", "status": "Failed"}
            assert pods[1] == {"name": "payment-svc-3", "status": "CrashLoopBackOff"}

    @pytest.mark.asyncio
    async def test_get_pod_logs(self, fallback):
        with patch("src.agents.discovery_fallback.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = (0, "ERROR: connection refused\nFATAL: shutting down", "")
            logs = await fallback.get_pod_logs("api-server-1", "app-prod")
            assert "connection refused" in logs
            assert "shutting down" in logs

    @pytest.mark.asyncio
    async def test_fallback_handles_failure(self, fallback):
        with patch("src.agents.discovery_fallback.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = (1, "", "Unable to connect to the server")
            namespaces = await fallback.discover_namespaces()
            assert namespaces == []

            pods = await fallback.discover_error_pods("default")
            assert pods == []

            logs = await fallback.get_pod_logs("pod-1", "default")
            assert logs == ""

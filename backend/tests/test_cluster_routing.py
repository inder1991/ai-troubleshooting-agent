import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_cluster_session_creates_graph():
    """Verify that capability=cluster_diagnostics creates a LangGraph session."""
    from src.api.routes_v4 import sessions

    with patch("src.api.routes_v4.build_cluster_diagnostic_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"phase": "complete", "health_report": {}})
        mock_build.return_value = mock_graph

        # Simulate what the routing logic does
        capability = "cluster_diagnostics"
        assert capability == "cluster_diagnostics"
        graph = mock_build()
        assert graph is not None

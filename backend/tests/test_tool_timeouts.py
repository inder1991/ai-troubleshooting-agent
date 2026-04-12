import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from src.tools.tool_executor import TOOL_TIMEOUTS


def test_tool_timeouts_defined():
    assert "fetch_pod_logs" in TOOL_TIMEOUTS
    assert "query_prometheus_range" in TOOL_TIMEOUTS
    assert "default" in TOOL_TIMEOUTS
    assert all(isinstance(v, int) for v in TOOL_TIMEOUTS.values())

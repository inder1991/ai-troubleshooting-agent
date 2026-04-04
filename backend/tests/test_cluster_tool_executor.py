import json
import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_client(data: list):
    result = MagicMock()
    result.data = data
    result.permission_denied = False
    result.truncated = False
    result.total_available = len(data)
    result.returned = len(data)
    client = MagicMock()
    client.list_pods = AsyncMock(return_value=result)
    client.list_events = AsyncMock(return_value=result)
    client.list_nodes = AsyncMock(return_value=result)
    return client


@pytest.mark.asyncio
async def test_truncated_result_is_valid_json():
    """When result exceeds MAX_RESULT_SIZE, returned JSON must be valid and complete."""
    from src.agents.cluster.tool_executor import execute_tool_call
    # Generate 100 large pod dicts to force truncation
    large_pods = [{"name": f"pod-{i}", "status": "x" * 200} for i in range(100)]
    client = _make_client(large_pods)

    result_str = await execute_tool_call("list_pods", {"namespace": "default"}, client)
    parsed = json.loads(result_str)  # Must not raise

    assert "data" in parsed
    assert "truncated" in parsed
    assert "total_available" in parsed
    assert "returned" in parsed
    assert isinstance(parsed["data"], list)
    # All items in data must be complete dicts (not truncated mid-item)
    for item in parsed["data"]:
        assert isinstance(item, dict)
        assert "name" in item


@pytest.mark.asyncio
async def test_non_truncated_result_has_envelope():
    """Even small results use the envelope format."""
    from src.agents.cluster.tool_executor import execute_tool_call
    small_pods = [{"name": "pod-1", "status": "Running"}]
    client = _make_client(small_pods)

    result_str = await execute_tool_call("list_pods", {"namespace": "default"}, client)
    parsed = json.loads(result_str)

    assert parsed["truncated"] is False
    assert parsed["returned"] == 1
    assert parsed["data"][0]["name"] == "pod-1"


@pytest.mark.asyncio
async def test_truncated_flag_set_when_data_dropped():
    """When items are dropped, truncated=True and returned < total_available."""
    from src.agents.cluster.tool_executor import execute_tool_call, MAX_RESULT_SIZE
    # Create items that will definitely exceed MAX_RESULT_SIZE
    big_pods = [{"name": f"pod-{i}", "payload": "z" * 500} for i in range(50)]
    client = _make_client(big_pods)

    result_str = await execute_tool_call("list_pods", {"namespace": "default"}, client)
    parsed = json.loads(result_str)

    assert parsed["truncated"] is True, "Expected truncation with 50 large items"
    assert parsed["returned"] < parsed["total_available"]
    assert parsed["truncation_reason"] == "SIZE_LIMIT"


def test_truncation_flags_have_drop_counts():
    """TruncationFlags must have dropped-count fields for each flag."""
    from src.agents.cluster.state import TruncationFlags
    flags = TruncationFlags(events=True, events_dropped=80, pods=True, pods_dropped=200)
    assert flags.events_dropped == 80
    assert flags.pods_dropped == 200
    assert flags.nodes_dropped == 0  # default

"""Tests for tool executor truncation of dict results."""
import json
from src.agents.cluster.tool_executor import _serialize_with_envelope, MAX_RESULT_SIZE


def test_dict_results_are_size_capped():
    """Dict results must be capped at MAX_RESULT_SIZE."""
    large_dict = {"key": "x" * (MAX_RESULT_SIZE + 1000)}
    result = _serialize_with_envelope(large_dict)
    assert len(result) <= MAX_RESULT_SIZE + 500  # Allow some envelope overhead


def test_list_truncation_is_visible():
    """List truncation must include total_available and returned counts."""
    items = [{"id": i, "data": "x" * 500} for i in range(50)]
    result = json.loads(_serialize_with_envelope(items))
    if result.get("truncated"):
        assert result["total_available"] == 50
        assert result["returned"] < 50

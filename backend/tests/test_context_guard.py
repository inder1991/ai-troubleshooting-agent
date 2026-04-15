import pytest
from src.utils.context_guard import ContextWindowGuard


@pytest.fixture
def guard():
    return ContextWindowGuard(model_name="claude-haiku-4-5-20251001")


def test_estimate_tokens(guard):
    messages = [{"role": "user", "content": "Hello world"}]
    count = guard.estimate_tokens(messages)
    assert count > 0
    assert isinstance(count, int)


def test_model_limit_haiku(guard):
    limit = guard.model_limit("claude-haiku-4-5-20251001")
    assert limit == 128000


def test_model_limit_sonnet():
    guard = ContextWindowGuard(model_name="claude-sonnet-4-20250514")
    limit = guard.model_limit("claude-sonnet-4-20250514")
    assert limit == 200000


def test_no_truncation_under_threshold(guard):
    messages = [{"role": "user", "content": "Short message"}]
    result = guard.truncate_if_needed(messages)
    assert len(result) == len(messages)


def test_truncation_drops_old_tool_results(guard):
    messages = [{"role": "user", "content": "initial"}]
    # Each "x" * 100000 is ~12500 tokens; 20 pairs = ~250k tokens, well over 102k threshold
    for i in range(20):
        messages.append({"role": "assistant", "content": f"tool_call_{i}"})
        messages.append({"role": "user", "content": "x" * 100000})
    result = guard.truncate_if_needed(messages)
    assert len(result) < len(messages)


def test_single_large_tool_result_tailed(guard):
    messages = [
        {"role": "user", "content": "initial"},
        {"role": "user", "content": "x\n" * 60000},
    ]
    result = guard.truncate_if_needed(messages)
    total_content = sum(len(m.get("content", "")) for m in result)
    assert total_content < 60000 * 2

import pytest
from src.models.schemas import ReActBudget


class TestReActBudget:
    def test_default_budget(self):
        budget = ReActBudget()
        assert budget.max_llm_calls == 10
        assert not budget.is_exhausted()

    def test_exhausted_on_llm_calls(self):
        budget = ReActBudget(max_llm_calls=2, current_llm_calls=2)
        assert budget.is_exhausted()

    def test_exhausted_on_tokens(self):
        budget = ReActBudget(max_tokens=100, current_tokens=150)
        assert budget.is_exhausted()

    def test_record_llm_call(self):
        budget = ReActBudget()
        budget.record_llm_call(tokens=500)
        assert budget.current_llm_calls == 1
        assert budget.current_tokens == 500

    def test_record_tool_call(self):
        budget = ReActBudget()
        budget.record_tool_call()
        assert budget.current_tool_calls == 1

    def test_not_exhausted_when_below_limits(self):
        budget = ReActBudget(max_llm_calls=10)
        budget.record_llm_call(100)
        assert not budget.is_exhausted()

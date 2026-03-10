import pytest
from src.utils.token_budget import estimate_tokens, enforce_budget

class TestTokenBudget:
    def test_estimate_tokens_basic(self):
        text = "Hello world this is a test"
        tokens = estimate_tokens(text)
        assert 5 <= tokens <= 10

    def test_estimate_tokens_empty(self):
        assert estimate_tokens("") == 0

    def test_enforce_budget_no_truncation_needed(self):
        system = "You are a helper."
        conversation = [{"role": "user", "content": "Hi"}]
        context = "Short context."
        s, c, ctx = enforce_budget(system, conversation, context, model_max=200_000)
        assert s == system
        assert c == conversation
        assert ctx == context

    def test_enforce_budget_truncates_conversation(self):
        system = "System prompt."
        conversation = [{"role": "user", "content": f"Message {i}"} for i in range(100)]
        context = "A" * 800_000
        s, c, ctx = enforce_budget(system, conversation, context, model_max=200_000)
        assert len(c) <= 10

    def test_enforce_budget_respects_target_ratio(self):
        system = "System prompt."
        conversation = [{"role": "user", "content": "Hi"}]
        context = "A" * 800_000
        s, c, ctx = enforce_budget(system, conversation, context, model_max=200_000, target_ratio=0.7)
        total = estimate_tokens(s) + estimate_tokens(str(c)) + estimate_tokens(ctx)
        assert total <= 200_000

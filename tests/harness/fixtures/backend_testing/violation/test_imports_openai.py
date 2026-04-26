"""Q9 violation — test file imports anthropic (real LLM call risk)."""
import anthropic

def test_call() -> None:
    anthropic.Anthropic().messages.create(model="claude-3", messages=[])

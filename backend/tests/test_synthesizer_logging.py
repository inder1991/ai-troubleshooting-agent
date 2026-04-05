"""Tests for synthesizer debug logging."""
import inspect


def test_causal_reasoning_logs_prompt():
    from src.agents.cluster import synthesizer
    source = inspect.getsource(synthesizer._llm_causal_reasoning)
    assert "logger.debug" in source, "No DEBUG logging in _llm_causal_reasoning"


def test_verdict_logs_prompt():
    from src.agents.cluster import synthesizer
    source = inspect.getsource(synthesizer._llm_verdict)
    assert "logger.debug" in source, "No DEBUG logging in _llm_verdict"

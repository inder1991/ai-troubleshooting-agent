"""Q9 violation — test file imports openai (real LLM call risk).

Pretend-path: backend/tests/test_routes.py
"""
import openai

def test_completion() -> None:
    openai.ChatCompletion.create(model="gpt-4", messages=[])

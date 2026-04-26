"""Q9 violation — `extract_*` function without paired Hypothesis test.

Pretend-path: backend/src/agents/log_agent.py
"""
def extract_severity(line: str) -> str:
    return "ERROR" if "error" in line.lower() else "INFO"

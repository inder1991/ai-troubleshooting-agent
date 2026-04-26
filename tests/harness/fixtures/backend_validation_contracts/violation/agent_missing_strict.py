"""Q10 violation — agent schema missing both forbid and frozen.

Pretend-path: backend/src/models/agent/log_finding.py
"""
from pydantic import BaseModel, Field

class LogFinding(BaseModel):
    severity: str = Field(..., max_length=16)

"""Q10 compliant — agent schema with both forbid and frozen.

Pretend-path: backend/src/models/agent/log_finding.py
"""
from pydantic import BaseModel, ConfigDict, Field

class LogFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    severity: str = Field(..., min_length=1, max_length=16)
    confidence: float = Field(..., ge=0.0, le=1.0)

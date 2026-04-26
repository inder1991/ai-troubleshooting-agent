"""Q10 violation — confidence field without ge/le bounds.

Pretend-path: backend/src/models/agent/score.py
"""
from pydantic import BaseModel, ConfigDict, Field

class Score(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    confidence: float = Field(...)

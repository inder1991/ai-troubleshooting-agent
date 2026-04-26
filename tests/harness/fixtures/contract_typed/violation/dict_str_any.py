"""SL violation — dict[str, Any] field in agent schema.

Pretend-path: backend/src/models/agent/finding.py
"""
from typing import Any
from pydantic import BaseModel, ConfigDict

class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metadata: dict[str, Any]

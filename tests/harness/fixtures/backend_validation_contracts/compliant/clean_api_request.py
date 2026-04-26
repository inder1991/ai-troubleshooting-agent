"""Q10 compliant — request with extra='forbid', bounds, max_length.

Pretend-path: backend/src/models/api/incident_request.py
"""
from pydantic import BaseModel, ConfigDict, Field

class IncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str = Field(..., min_length=1, max_length=64)
    confidence: float = Field(..., ge=0.0, le=1.0)

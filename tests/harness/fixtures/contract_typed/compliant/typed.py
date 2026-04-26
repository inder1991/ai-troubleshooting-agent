"""SL compliant — every field has a concrete type.

Pretend-path: backend/src/models/api/incident_response.py
"""
from pydantic import BaseModel, ConfigDict, Field

class IncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    incident_id: str = Field(..., min_length=1, max_length=64)
    severity: str = Field(..., min_length=1, max_length=16)

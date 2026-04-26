"""Q10 violation — response model not frozen.

Pretend-path: backend/src/models/api/incident_response.py
"""
from pydantic import BaseModel, ConfigDict, Field

class IncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str = Field(..., max_length=64)

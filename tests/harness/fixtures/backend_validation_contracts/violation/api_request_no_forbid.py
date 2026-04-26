"""Q10 violation — request model missing extra='forbid'.

Pretend-path: backend/src/models/api/incident_request.py
"""
from pydantic import BaseModel, Field

class IncidentRequest(BaseModel):
    incident_id: str = Field(..., max_length=64)

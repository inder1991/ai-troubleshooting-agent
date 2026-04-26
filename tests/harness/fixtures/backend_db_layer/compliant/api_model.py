"""Q8 compliant — pure API model, no table=True, no SQLModel inheritance.

Pretend-path: backend/src/models/api/incident_response.py
"""
from pydantic import BaseModel, Field

class IncidentResponse(BaseModel):
    incident_id: str = Field(..., min_length=1, max_length=64)

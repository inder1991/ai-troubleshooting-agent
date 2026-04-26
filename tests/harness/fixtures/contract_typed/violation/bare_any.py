"""SL violation — bare Any annotation on an api field.

Pretend-path: backend/src/models/api/incident_response.py
"""
from typing import Any
from pydantic import BaseModel, ConfigDict

class IncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    extra: Any

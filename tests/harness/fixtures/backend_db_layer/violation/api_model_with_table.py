"""Q8 violation — api boundary model accidentally declared table=True.

Pretend-path: backend/src/models/api/incident_response.py
"""
from sqlmodel import SQLModel

class IncidentResponse(SQLModel, table=True):
    id: int

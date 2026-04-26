"""Q10 violation — extra='allow' inside api boundary.

Pretend-path: backend/src/models/api/loose_request.py
"""
from pydantic import BaseModel, ConfigDict

class LooseRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    foo: str

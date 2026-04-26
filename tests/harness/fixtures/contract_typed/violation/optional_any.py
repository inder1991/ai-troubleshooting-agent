"""SL violation — Optional[Any] in sidecar.

Pretend-path: backend/src/learning/sidecars/observation.py
"""
from typing import Any, Optional
from pydantic import BaseModel

class Observation(BaseModel):
    payload: Optional[Any] = None

"""Q8 violation — SQLModel imported outside storage/ or models/db/.

Pretend-path: backend/src/agents/learning/runner.py
"""
from sqlmodel import SQLModel

class Foo(SQLModel):
    name: str

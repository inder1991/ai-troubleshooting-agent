"""Synthetic SQLModel db model."""
from sqlmodel import SQLModel, Field


class Incident(SQLModel, table=True):
    __tablename__ = "incidents"

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=200)
    severity: str = Field(max_length=16)

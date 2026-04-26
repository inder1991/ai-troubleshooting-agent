"""Synthetic Pydantic API request model."""
from pydantic import BaseModel, ConfigDict, Field


class IncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=200)
    severity: int = Field(ge=1, le=5)

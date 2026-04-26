"""Synthetic Pydantic agent finding model."""
from pydantic import BaseModel, ConfigDict, Field


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)

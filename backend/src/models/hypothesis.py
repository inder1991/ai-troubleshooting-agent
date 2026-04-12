"""Core hypothesis models for multi-hypothesis diagnostic engine."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class EvidenceSignal(BaseModel):
    """A typed evidence signal from any agent."""

    signal_id: str
    signal_type: Literal["log", "metric", "k8s", "trace", "code", "change"]
    signal_name: str
    raw_data: dict = Field(default_factory=dict)
    source_agent: str
    timestamp: Optional[datetime] = None
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    freshness: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("strength", "freshness", mode="before")
    @classmethod
    def clamp_zero_one(cls, v: float) -> float:
        if v < 0.0:
            return 0.0
        if v > 1.0:
            return 1.0
        return v


class CausalLink(BaseModel):
    """A validated causal relationship between signals."""

    cause_signal: str
    effect_signal: str
    confidence: float = Field(ge=0.0, le=1.0)
    time_delta_seconds: float
    same_entity: bool = False
    validation: str = ""


class Hypothesis(BaseModel):
    """A diagnostic hypothesis being tested."""

    hypothesis_id: str
    category: str
    source_patterns: list = Field(default_factory=list)
    status: Literal["active", "eliminated", "winner"] = "active"
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    evidence_for: list[EvidenceSignal] = Field(default_factory=list)
    evidence_against: list[EvidenceSignal] = Field(default_factory=list)
    downstream_effects: list[str] = Field(default_factory=list)
    root_cause_of: Optional[str] = None
    elimination_reason: Optional[str] = None
    elimination_phase: Optional[str] = None


class HypothesisResult(BaseModel):
    """Final decision container."""

    hypotheses: list[Hypothesis] = Field(default_factory=list)
    winner: Optional[Hypothesis] = None
    status: Literal["resolved", "inconclusive"] = "resolved"
    elimination_log: list[dict] = Field(default_factory=list)
    evidence_timeline: list[EvidenceSignal] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

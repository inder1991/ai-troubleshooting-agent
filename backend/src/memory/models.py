from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class IncidentFingerprint(BaseModel):
    fingerprint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    created_at: datetime = Field(default_factory=datetime.now)

    # Signal fingerprint
    error_patterns: list[str] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    affected_namespaces: list[str] = Field(default_factory=list)
    symptom_categories: list[str] = Field(default_factory=list)  # "connection_timeout", "oom", etc.

    # Resolution fingerprint
    root_cause: str = ""
    root_cause_category: str = ""  # "deployment", "config", "resource", "dependency", "infrastructure"
    resolution_steps: list[str] = Field(default_factory=list)
    resolution_success: bool = False
    time_to_resolve: float = 0.0  # seconds

    # For similarity
    embedding_text: str = ""  # concatenated summary


class SimilarIncident(BaseModel):
    fingerprint: IncidentFingerprint
    similarity_score: float
    match_type: str  # "signal" or "semantic"

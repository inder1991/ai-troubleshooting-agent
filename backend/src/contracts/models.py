"""Agent manifest contract — Pydantic schema for YAML manifests under
``backend/src/agents/manifests/``. Phase 1 Task 2.

A manifest's ``inputs``/``outputs`` are plain JSON-Schema dicts. We validate
that the top-level schema is ``type: object`` (agents always take a struct)
but do not fully validate JSON-Schema shape here — that happens in the
registry loader via ``jsonschema`` (Task 4).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ManifestValidationError(ValueError):
    """Raised by registry callers when a manifest fails semantic validation."""


class CostHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_calls: int = 0
    typical_duration_s: float = 0.0


class AgentContract(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    version: int = Field(gt=0)
    deprecated_versions: list[int] = Field(default_factory=list)
    description: str
    category: str
    tags: list[str] = Field(default_factory=list)

    # JSON-Schema dicts. YAML key is ``inputs``/``outputs``; exposed on the
    # model as ``input_schema``/``output_schema`` to avoid shadowing the
    # Python word "input".
    input_schema: dict[str, Any] = Field(alias="inputs")
    output_schema: dict[str, Any] = Field(alias="outputs")

    trigger_examples: list[str]
    retry_on: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(gt=0)
    cost_hint: CostHint | None = None

    @field_validator("trigger_examples")
    @classmethod
    def _at_least_two_examples(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError("trigger_examples must contain at least 2 entries")
        return v

    @field_validator("input_schema", "output_schema")
    @classmethod
    def _must_be_object_schema(cls, v: dict[str, Any]) -> dict[str, Any]:
        if v.get("type") != "object":
            raise ValueError("schema must be of type 'object'")
        return v

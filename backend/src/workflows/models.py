from __future__ import annotations

import re
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FROZEN_OPS = frozenset({"coalesce", "concat", "eq", "in", "exists", "and", "or", "not"})
STEP_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class RefNode(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: Literal["node"] = Field(alias="from")
    node_id: str
    path: str


class RefInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: Literal["input"] = Field(alias="from")
    path: str


class RefEnv(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: Literal["env"] = Field(alias="from")
    path: str


Ref = Union[RefNode, RefInput, RefEnv]


class LiteralExpr(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    literal: Any


class Transform(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    op: str
    args: list[Any]

    @field_validator("op")
    @classmethod
    def _op_in_frozen(cls, v: str) -> str:
        if v not in FROZEN_OPS:
            raise ValueError(f"unknown op {v!r}; allowed: {sorted(FROZEN_OPS)}")
        return v


Expr = Union[dict, LiteralExpr, Transform]


class StepSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str
    agent: str
    agent_version: Union[int, Literal["latest"]] = "latest"
    inputs: dict[str, Any] = Field(default_factory=dict)
    when: dict | None = None
    on_failure: Literal["fail", "continue", "fallback"] = "fail"
    fallback_step_id: str | None = None
    parallel_group: str | None = None
    concurrency_group: str | None = None
    timeout_seconds_override: float | None = None
    retry_on_override: list[str] | None = None

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not STEP_ID_RE.match(v):
            raise ValueError(f"invalid step id {v!r}")
        return v

    @model_validator(mode="after")
    def _fallback_requires_id(self) -> "StepSpec":
        if self.on_failure == "fallback" and not self.fallback_step_id:
            raise ValueError("on_failure='fallback' requires fallback_step_id")
        return self


class WorkflowDag(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    inputs_schema: dict = Field(default_factory=lambda: {"type": "object"})
    steps: list[StepSpec]

    @model_validator(mode="after")
    def _unique_ids(self) -> "WorkflowDag":
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate step ids")
        return self

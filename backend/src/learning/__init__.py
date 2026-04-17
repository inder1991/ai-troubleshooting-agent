"""Active-learning pipeline interface — P2 stub.

See ``docs/design/active-learning.md`` for the full design. This file only
pins the public surface so callers can import the types; every method
raises ``NotImplementedError`` until the eval corpus + sign-off unblock
the live batch runner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PriorUpdate:
    agent_name: str
    before: float
    after: float
    sample_count_delta: int


@dataclass(frozen=True)
class SignatureFloorUpdate:
    pattern_name: str
    before: float
    after: float


@dataclass(frozen=True)
class LearningReport:
    since: datetime
    until: datetime
    prior_updates: tuple[PriorUpdate, ...] = ()
    floor_updates: tuple[SignatureFloorUpdate, ...] = ()
    skipped_reason: str | None = None
    dry_run: bool = True


class LearningPipeline:
    """Weekly batch runner — NOT YET ACTIVE.

    Intended use:
        pipeline = LearningPipeline()
        report = await pipeline.consume_feedback_batch(since=..., dry_run=True)
        # Review the report, then re-run with dry_run=False to commit.
    """

    async def consume_feedback_batch(
        self,
        *,
        since: datetime,
        until: datetime | None = None,
        dry_run: bool = True,
    ) -> LearningReport:
        raise NotImplementedError(
            "active-learning pipeline is P2 design-only; see "
            "docs/design/active-learning.md"
        )


__all__ = [
    "LearningPipeline",
    "LearningReport",
    "PriorUpdate",
    "SignatureFloorUpdate",
]

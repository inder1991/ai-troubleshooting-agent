"""POST /api/v4/investigations/{run_id}/feedback — user outcome labels.

Idempotent on (run_id, submitter). On each new feedback row, agents that
contributed to the winning hypothesis have their priors nudged (positive if
was_correct, negative otherwise). The list of contributing agents is read
from the DAG snapshot's ``winning_agents`` field; if it isn't populated yet
(the supervisor split in Tasks 2.8–2.10 will write it), the endpoint still
records the feedback but logs a warning and leaves priors untouched.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.agents.confidence_calibrator import ConfidenceCalibrator
from src.database.engine import get_session
from src.database.models import DagSnapshot, IncidentFeedback
from src.utils.logger import get_logger


logger = get_logger(__name__)

feedback_router = APIRouter(prefix="/api/v4/investigations", tags=["feedback"])


class FeedbackBody(BaseModel):
    was_correct: bool
    actual_root_cause: Optional[str] = None
    freeform: Optional[str] = None
    submitter: str = Field(default="anonymous", max_length=128)


async def _extract_winning_agents(run_id: str) -> list[str]:
    """Read contributing agents from the DAG snapshot for a run.

    The supervisor is expected to persist ``winning_agents: [...]`` inside
    the snapshot payload; until then this returns ``[]`` and the caller
    logs a warning.
    """
    async with get_session() as session:
        row = await session.execute(
            select(DagSnapshot.payload).where(DagSnapshot.run_id == run_id)
        )
        payload = row.scalar_one_or_none()
    if not isinstance(payload, dict):
        return []
    agents = payload.get("winning_agents") or []
    if not isinstance(agents, list):
        return []
    return [a for a in agents if isinstance(a, str)]


@feedback_router.post("/{run_id}/feedback")
async def submit_investigation_feedback(run_id: str, body: FeedbackBody) -> dict[str, Any]:
    if not run_id or len(run_id) > 64:
        raise HTTPException(status_code=400, detail="invalid run_id")

    # 1. Idempotent insert of the feedback row.
    async with get_session() as session:
        async with session.begin():
            stmt = pg_insert(IncidentFeedback).values(
                run_id=run_id,
                was_correct=body.was_correct,
                actual_root_cause=body.actual_root_cause,
                freeform=body.freeform,
                submitter=body.submitter,
            )
            # ON CONFLICT DO NOTHING: duplicate (run_id, submitter) is a no-op,
            # not an error. We still want to return 200 so retries are safe.
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[
                    IncidentFeedback.run_id,
                    IncidentFeedback.submitter,
                ]
            )
            result = await session.execute(stmt)
            first_time = result.rowcount == 1

    # 2. Prior updates — only when the feedback row is new. A re-submit from
    #    the same submitter must not double-apply the EMA nudge.
    updated_agents: list[str] = []
    if first_time:
        winning_agents = await _extract_winning_agents(run_id)
        if not winning_agents:
            logger.warning(
                "feedback: no winning_agents in DAG snapshot for run_id=%s; "
                "priors not updated",
                run_id,
            )
        else:
            cal = ConfidenceCalibrator()
            for agent in winning_agents:
                await cal.update_prior(agent, was_correct=body.was_correct)
                updated_agents.append(agent)

    return {
        "status": "recorded",
        "run_id": run_id,
        "idempotent_replay": not first_time,
        "priors_updated": updated_agents,
    }

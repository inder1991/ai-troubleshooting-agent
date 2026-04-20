"""Zepay demo — workflow-backend seed endpoint.

Strictly gated behind DEMO_MODE=on so production deployments can
never accept seeded state. The demo-controller (on the operator's
laptop) POSTs pre-baked incident payloads to this endpoint to hydrate:

  · The historical archive (Feb-2026 sibling incident) so the
    "third checkout incident this quarter" CXO beat works.
  · Future (post-PR-K7) scenarios can extend this with new names
    without changing the route.

Design:
  · Read-only intent: no DB migrations, no new tables. We write to
    the existing `sessions` in-memory dict (same path /status reads
    from) + Redis session store if available.
  · Idempotent per incident_id: a second POST with the same body is
    a no-op. Safe to re-run the demo-controller multiple times.
  · No auth beyond the feature flag — the API is itself unreachable
    in production if DEMO_MODE is off.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v4/demo", tags=["demo"])


class SeedIncidentRequest(BaseModel):
    """Fields mirror demo-controller/fixtures/historical-incident.json.

    Most are optional — the Zepay scenario only exercises the subset
    the /status response needs to answer "this is the third incident
    this quarter". Extra fields in the payload are ignored so the
    fixture file can grow without breaking the contract.
    """
    incident_id: str
    service_name: str
    title: str | None = None
    phase: str = "complete"
    confidence: int = Field(default=0, ge=0, le=100)
    created_at: str
    updated_at: str
    resolved_at: str | None = None
    duration_minutes: int | None = None
    winning_hypothesis: Dict[str, Any] | None = None
    fix_prs: list[Dict[str, Any]] | None = None
    affected_customers: int | None = None
    dollar_exposure_usd: float | None = None
    coverage_gaps: list[str] | None = None
    notes: str | None = None

    model_config = {"extra": "ignore"}


def _demo_mode_on() -> bool:
    return os.environ.get("DEMO_MODE", "off").strip().lower() in {"on", "true", "1", "yes"}


@router.post("/seed/{scenario}")
async def seed_scenario(scenario: str, payload: SeedIncidentRequest) -> dict:
    if not _demo_mode_on():
        # 404 not 403 — we don't want to hint at the endpoint's
        # existence in prod.
        raise HTTPException(status_code=404, detail="not found")

    # Lazy import so this module imports cleanly even if routes_v4
    # hasn't finished its own import graph yet (they're siblings).
    from src.api.routes_v4 import sessions, _persist_session

    # Map the pydantic model into the shape /status consumes.
    session_record = {
        "session_id":         payload.incident_id,
        "incident_id":        payload.incident_id,
        "service_name":       payload.service_name,
        "phase":              payload.phase,
        "confidence":         payload.confidence,
        "created_at":         payload.created_at,
        "updated_at":         payload.updated_at,
        "capability":         "troubleshoot_app",
        "investigation_mode": "seeded_demo",
        "related_sessions":   [],
        # Surfacing for the UI historical archive card.
        "demo_seed": {
            "scenario":          scenario,
            "title":             payload.title,
            "duration_minutes":  payload.duration_minutes,
            "winning_hypothesis": payload.winning_hypothesis,
            "fix_prs":            payload.fix_prs or [],
            "affected_customers": payload.affected_customers,
            "dollar_exposure_usd": payload.dollar_exposure_usd,
            "notes":              payload.notes,
        },
    }

    sessions[payload.incident_id] = session_record
    try:
        await _persist_session(payload.incident_id, session_record)
    except Exception as e:
        # Non-fatal — the in-memory entry is what /status reads first.
        logger.warning("demo seed: redis persist failed for %s: %s",
                       payload.incident_id, e)

    logger.info(
        "demo seed accepted",
        extra={
            "action": "demo_seed",
            "extra": {
                "scenario":    scenario,
                "incident_id": payload.incident_id,
                "phase":       payload.phase,
            },
        },
    )
    return {
        "seeded":      True,
        "scenario":    scenario,
        "incident_id": payload.incident_id,
    }

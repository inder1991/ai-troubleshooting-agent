"""Zepay scenario replayer — PR-K8.

A scripted, time-synchronized replay that drives the War Room UI
through a full ~100-second incident investigation without any real
cluster, agents, or LLM calls.

The replayer runs a single async task that:
  1. Advances through a JSON timeline of entries keyed on wall-clock
     offsets `t` (seconds from scenario start).
  2. Entries are one of two kinds:
       · "event"        — emits a WS task_event via the existing
                          EventEmitter (so the UI sees it live)
       · "state_patch"  — mutates the session's in-memory state
                          (so GET /findings and GET /status return
                          progressively richer payloads)
  3. Honors an AttestationGate pause: when the timeline declares
     `{kind:"await_approval"}`, the task sleeps until the operator
     POSTs /api/v4/demo/scenario/approve.

Strict gating:
  · All endpoints require DEMO_MODE=on (matching routes_demo_seed).
  · 404 in production so the surface is invisible.

Endpoints:
  POST /api/v4/demo/scenario/start     — create session + kick replay
  POST /api/v4/demo/scenario/approve   — release the attestation gate
  POST /api/v4/demo/scenario/cancel    — cancel the replay
  GET  /api/v4/demo/scenario/state     — current state for the operator UI
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v4/demo/scenario", tags=["demo"])

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Replay pacing multiplier. The raw timeline compresses a full multi-agent
# investigation into ~85 seconds — useful for unit tests, but on-screen it
# blazes past at flip-book speed and feels obviously mocked. Multiplying
# every `t` offset by this factor stretches the wall-clock without touching
# the fixture. Default 4× → ~5.5 minutes end-to-end, which matches the
# cadence of a real production SRE investigation the first few phases.
# Override with DEMO_SCENARIO_SPEED (float, clamped to [0.25, 20]).
_DEFAULT_SPEED = 4.0


def _replay_speed() -> float:
    raw = os.environ.get("DEMO_SCENARIO_SPEED", "").strip()
    if not raw:
        return _DEFAULT_SPEED
    try:
        val = float(raw)
    except ValueError:
        return _DEFAULT_SPEED
    return max(0.25, min(20.0, val))


# ── State ─────────────────────────────────────────────────────────────


@dataclass
class ScenarioRun:
    session_id: str
    incident_id: str
    task: Optional[asyncio.Task] = None
    approval_event: Optional[asyncio.Event] = None
    cancelled: bool = False
    started_at: Optional[str] = None
    last_t: float = 0.0
    awaiting_approval: bool = False


_RUNS: dict[str, ScenarioRun] = {}


def _demo_mode_on() -> bool:
    return os.environ.get("DEMO_MODE", "off").strip().lower() in {"on", "true", "1", "yes"}


# ── Requests ──────────────────────────────────────────────────────────


class StartRequest(BaseModel):
    scenario: str = "zepay-main-incident"
    service_name: str = "checkout-service"


# ── Replay engine ─────────────────────────────────────────────────────


def _deep_merge(dst: dict, patch: dict) -> dict:
    """Merge `patch` into `dst` in place; supports appending to lists.

    Convention:
      · patch["foo"] replaces dst["foo"] outright.
      · Special key suffix `"+"` appends: {"token_usage[+]": {...}} adds
        the element to the list at dst["token_usage"], creating it if
        absent. Used for per-agent token accrual in the timeline.
    """
    for k, v in patch.items():
        if k.endswith("[+]"):
            key = k[:-3]
            lst = dst.setdefault(key, [])
            if isinstance(lst, list):
                lst.append(v)
            continue
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


async def _replay(run: ScenarioRun, timeline: list[dict]) -> None:
    """Drive the UI through the timeline.

    The replayer runs entirely in-process. It uses routes_v4's session
    machinery:
      · `sessions[sid]` dict (what /status reads)
      · `sessions[sid]["state"]` for the full DiagnosticState-like blob
        (what /findings projects from)
      · EventEmitter for WS broadcasts
    """
    from src.api.routes_v4 import sessions
    from src.api.websocket import manager
    from src.utils.event_emitter import EventEmitter
    from src.observability.store import get_store

    emitter = EventEmitter(
        session_id=run.session_id,
        websocket_manager=manager,
        store=get_store(),
    )

    # Ensure the session record exists. routes_v4's /status endpoint
    # reads sessions[sid]; we seed a minimal record so early polls
    # return something coherent before the timeline fills it in.
    now = datetime.now(timezone.utc).isoformat()
    run.started_at = now
    # Seed the session with ONLY what a real intake system would know
    # instantly: incident id, operator-supplied target service + namespace,
    # the topology-cache dependency graph (legitimately zero-latency), and
    # the list of agents being dispatched. Everything else — patient zero,
    # service flow, metrics, blast radius, severity — must come from the
    # scripted timeline at its natural moment, so the pacing stays
    # consistent end-to-end.
    seed_inferred_deps = [
        {"source": "api-gateway", "target": "checkout-service", "kind": "http"},
        {"source": "checkout-service", "target": "payment-service", "kind": "http"},
        {"source": "payment-service", "target": "wallet-service", "kind": "http"},
        {"source": "payment-service", "target": "inventory-service", "kind": "http"},
        {"source": "payment-service", "target": "fraud-adapter", "kind": "http"},
        {"source": "payment-service", "target": "notification-service", "kind": "http"},
        {"source": "checkout-service", "target": "cart-service", "kind": "http"},
        {"source": "api-gateway", "target": "auth-service", "kind": "http"},
    ]

    sessions[run.session_id] = {
        "session_id": run.session_id,
        "incident_id": run.incident_id,
        "service_name": "checkout-service",
        "phase": "collecting_context",
        "confidence": 0,
        "created_at": now,
        "updated_at": now,
        "capability": "troubleshoot_app",
        "investigation_mode": "demo_scenario",
        "related_sessions": [],
        "budget": {
            "tool_calls_used": 0,
            "tool_calls_max": 40,
            "llm_usd_used": 0.0,
            "llm_usd_max": 1.00,
        },
        "state": {
            # The state dict shadows DiagnosticState's field shape so
            # /findings can project from it.
            "session_id": run.session_id,
            "incident_id": run.incident_id,
            "service_name": "checkout-service",
            # Target service comes from the intake form; namespace is
            # derived from the service catalog lookup (handshake event).
            "target_service": "checkout-service",
            "detected_namespace": "payments-prod",
            "phase": "collecting_context",
            "overall_confidence": 0,
            "all_findings": [],
            "all_breadcrumbs": [],
            "all_negative_findings": [],
            "critic_verdicts": [],
            "divergence_findings": [],
            "cross_checks_announced": [],
            "hypotheses": [],
            "hypothesis_result": None,
            "token_usage": [],
            "coverage_gaps": [],
            "metric_anomalies": [],
            "suggested_promql_queries": [],
            # Topology cache is the one thing we genuinely know at t=0.
            # Everything else emerges from agents.
            "inferred_dependencies": seed_inferred_deps,
            "service_flow": [],
            "agents_completed": [],
            "agents_pending": ["log_agent", "metric_agent", "tracing_agent", "k8s_agent"],
        },
    }

    t0 = asyncio.get_event_loop().time()
    speed = _replay_speed()
    logger.info("scenario replay starting session=%s speed=%.2fx", run.session_id, speed)

    for entry in timeline:
        if run.cancelled:
            logger.info("scenario cancelled session=%s", run.session_id)
            return

        # Wait until wall-clock reaches entry["t"] * speed. Every offset in
        # the fixture is scaled by the pacing multiplier, so stretching from
        # 85s to ~5.5 min only changes perceived cadence — not ordering.
        t_target = float(entry.get("t", 0)) * speed
        now_rel = asyncio.get_event_loop().time() - t0
        wait = t_target - now_rel
        if wait > 0:
            try:
                await asyncio.sleep(wait)
            except asyncio.CancelledError:
                return
        run.last_t = t_target

        kind = entry.get("kind")
        try:
            if kind == "event":
                ev = entry["event"]
                await emitter.emit(
                    agent_name=ev.get("agent_name", "supervisor"),
                    event_type=ev.get("event_type", "summary"),
                    message=ev.get("message", ""),
                    details=ev.get("details"),
                )
            elif kind == "state_patch":
                patch = entry["patch"]
                sess = sessions.get(run.session_id, {})
                # Two targets: top-level session fields (phase/confidence/
                # budget/signature_match/...) AND session["state"] (the
                # DiagnosticState-shaped blob /findings reads from).
                top = patch.get("session", {})
                state = patch.get("state", {})
                if top:
                    _deep_merge(sess, top)
                    sess["updated_at"] = datetime.now(timezone.utc).isoformat()
                if state:
                    sess_state = sess.setdefault("state", {})
                    _deep_merge(sess_state, state)
            elif kind == "phase_change":
                new_phase = entry["phase"]
                sess = sessions.get(run.session_id, {})
                sess["phase"] = new_phase
                sess.setdefault("state", {})["phase"] = new_phase
                sess["updated_at"] = datetime.now(timezone.utc).isoformat()
                await emitter.emit(
                    agent_name="supervisor",
                    event_type="phase_change",
                    message=f"phase → {new_phase}",
                    details={"phase": new_phase},
                )
            elif kind == "await_approval":
                run.awaiting_approval = True
                sess = sessions.get(run.session_id, {})
                pending = entry.get("pending_action", {
                    "type": "attestation",
                    "title": "Approve remediation",
                    "description": "Review the three fix PRs before merge.",
                })
                sess["pending_action"] = pending

                # Ledger-based approval only — the old modal popup was
                # removed. Two surfaces are responsible for showing the
                # gate to the operator:
                #   1. Chat drawer: render the pending_action as a pinned
                #      approval card. Push a one-line assistant message so
                #      there's prose context around the card, and the SRE
                #      sees a fresh chat bubble that nudges them to look.
                #   2. Ledger drawer: reads pending_action off /status.
                chat_history = sess.setdefault("chat_history", [])
                title = pending.get("title") or "Approval required"
                description = pending.get("description") or ""
                options = pending.get("options") or []
                option_lines = "\n".join(
                    f"  · **{o.get('value', '?')}** — {o.get('label', '')}"
                    for o in options
                )
                prompt = (
                    f"**{title}**\n\n{description}\n\n"
                    f"Reply with one of:\n{option_lines}" if option_lines
                    else f"**{title}**\n\n{description}"
                )
                chat_history.append({
                    "role": "assistant",
                    "content": prompt,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"kind": "approval_gate", "pending_action": pending},
                })

                await emitter.emit(
                    agent_name="supervisor",
                    event_type="summary",
                    message=entry.get("message", "Awaiting operator approval — ledger gate."),
                    details={"reason": "fix_approval", "channel": "ledger"},
                )
                # Sleep until the operator hits /approve or we cancel.
                assert run.approval_event is not None
                try:
                    await asyncio.wait_for(run.approval_event.wait(), timeout=600)
                except asyncio.TimeoutError:
                    logger.warning("approval timed out; auto-advancing session=%s", run.session_id)
                run.awaiting_approval = False
                sess["pending_action"] = None
                # Reset offsets for post-approval wall-clock so the next
                # `t` in the timeline is measured from the approval moment,
                # not from scenario start (prevents a huge immediate fast-
                # forward through the fix sequence).
                t0 = asyncio.get_event_loop().time() - t_target
            else:
                logger.warning("unknown timeline kind=%s; skipping", kind)
        except Exception as e:
            logger.exception("replay step failed at t=%.2f: %s", t_target, e)

    logger.info("scenario replay complete session=%s", run.session_id)


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/start")
async def start(req: StartRequest) -> dict:
    if not _demo_mode_on():
        raise HTTPException(status_code=404, detail="not found")

    fixture = FIXTURES_DIR / f"{req.scenario}.json"
    if not fixture.exists():
        raise HTTPException(status_code=404, detail=f"scenario not found: {req.scenario}")

    timeline = json.loads(fixture.read_text())

    session_id = str(uuid.uuid4())
    from src.agents.supervisor import generate_incident_id
    incident_id = generate_incident_id()

    run = ScenarioRun(
        session_id=session_id,
        incident_id=incident_id,
        approval_event=asyncio.Event(),
    )
    _RUNS[session_id] = run

    run.task = asyncio.create_task(_replay(run, timeline))

    logger.info(
        "demo scenario started",
        extra={
            "action": "demo_scenario_start",
            "extra": {
                "session_id": session_id,
                "incident_id": incident_id,
                "scenario": req.scenario,
                "timeline_entries": len(timeline),
            },
        },
    )

    return {
        "session_id": session_id,
        "incident_id": incident_id,
        "scenario": req.scenario,
        "timeline_entries": len(timeline),
    }


@router.post("/approve")
async def approve(session_id: str) -> dict:
    if not _demo_mode_on():
        raise HTTPException(status_code=404, detail="not found")
    run = _RUNS.get(session_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown session")
    if not run.awaiting_approval:
        return {"approved": False, "reason": "not currently awaiting approval"}
    assert run.approval_event is not None
    run.approval_event.set()
    return {"approved": True, "session_id": session_id}


@router.post("/cancel")
async def cancel(session_id: str) -> dict:
    if not _demo_mode_on():
        raise HTTPException(status_code=404, detail="not found")
    run = _RUNS.get(session_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown session")
    run.cancelled = True
    if run.approval_event is not None:
        run.approval_event.set()
    if run.task is not None and not run.task.done():
        run.task.cancel()
    return {"cancelled": True, "session_id": session_id}


@router.get("/state")
async def state(session_id: Optional[str] = None) -> dict:
    if not _demo_mode_on():
        raise HTTPException(status_code=404, detail="not found")
    if session_id:
        run = _RUNS.get(session_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown session")
        return {
            "session_id": run.session_id,
            "incident_id": run.incident_id,
            "started_at": run.started_at,
            "last_t": run.last_t,
            "awaiting_approval": run.awaiting_approval,
            "cancelled": run.cancelled,
            "task_done": run.task.done() if run.task else True,
        }
    # Summary of all runs — useful for operator UI.
    return {
        "runs": [
            {
                "session_id": r.session_id,
                "incident_id": r.incident_id,
                "started_at": r.started_at,
                "last_t": r.last_t,
                "awaiting_approval": r.awaiting_approval,
                "cancelled": r.cancelled,
                "task_done": r.task.done() if r.task else True,
            }
            for r in _RUNS.values()
        ],
    }

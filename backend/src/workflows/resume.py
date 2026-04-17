"""Graceful drain + checkpoint resume.

When a pod is terminated mid-investigation:
  - SIGTERM handler stops accepting new runs, waits up to GRACE_S for
    in-flight runs to checkpoint via the OutboxWriter, then forces a
    final snapshot.
  - On boot, ``resume_all_in_progress`` re-acquires the RunLock for any
    investigation whose DAG snapshot is 'running' with a stale
    heartbeat. The lock is exclusive, so only one replica picks up any
    given run.

State lives in ``investigation_dag_snapshot.payload`` — the same table
OutboxWriter already UPSERTs every step — so resume is a SELECT, not a
new persistence layer.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable, Optional

from sqlalchemy import text

from src.database.engine import get_session

logger = logging.getLogger(__name__)


# How long to wait for in-flight runs to checkpoint before forcing snapshots.
GRACE_S: int = 30

# A snapshot whose updated_at is older than this is considered orphaned —
# the previous owner is presumed dead.
_STALE_HEARTBEAT_S: int = 60


@dataclass(frozen=True)
class ResumableRun:
    run_id: str
    last_seen_at: datetime
    payload: dict


async def select_orphaned_running(
    *, stale_heartbeat_s: int = _STALE_HEARTBEAT_S
) -> list[ResumableRun]:
    """Return snapshots whose updated_at is older than the stale window.

    Uses payload's ``status`` field if present, falls back to snapshots
    with a finite ``last_sequence_number`` and no explicit completion
    marker. Deliberately permissive: re-acquiring the RunLock will fail
    fast if another replica already owns the run, so false positives are
    harmless.
    """
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT run_id, payload, updated_at
                FROM investigation_dag_snapshot
                WHERE updated_at < (NOW() - make_interval(secs => :s))
                ORDER BY run_id
                """
            ),
            {"s": stale_heartbeat_s},
        )
        rows = list(result.mappings())

    resumable: list[ResumableRun] = []
    for row in rows:
        payload = row["payload"] if isinstance(row["payload"], dict) else {}
        status = payload.get("status")
        if status == "completed" or status == "failed":
            continue
        resumable.append(
            ResumableRun(
                run_id=row["run_id"],
                last_seen_at=row["updated_at"],
                payload=payload,
            )
        )
    return resumable


async def resume_all_in_progress(
    *,
    acquire_lock: Callable[[str], Awaitable[bool]],
    dispatch_resume: Callable[[ResumableRun], Awaitable[None]],
    stale_heartbeat_s: int = _STALE_HEARTBEAT_S,
) -> list[str]:
    """Re-dispatch every orphaned run we can take ownership of.

    Injectable ``acquire_lock`` and ``dispatch_resume`` keep this module
    pure: tests stub them; production binds them to the real RunLock +
    supervisor factory when the orchestration swap into run_v5 lands.
    """
    taken: list[str] = []
    for run in await select_orphaned_running(stale_heartbeat_s=stale_heartbeat_s):
        try:
            got_lock = await acquire_lock(run.run_id)
        except Exception:
            logger.warning("resume: lock acquisition failed for %s", run.run_id)
            continue
        if not got_lock:
            # Another replica already holds it — that's fine, they'll run it.
            continue
        try:
            await dispatch_resume(run)
            taken.append(run.run_id)
        except Exception:
            logger.exception("resume: dispatch failed for %s", run.run_id)
    return taken


@dataclass
class DrainState:
    """Process-wide flag the supervisor consults before starting new runs."""

    _draining: bool = False

    def start_drain(self) -> None:
        self._draining = True

    def is_draining(self) -> bool:
        return self._draining


_drain_state = DrainState()


def get_drain_state() -> DrainState:
    return _drain_state


async def wait_for_drain(
    *,
    has_in_flight: Callable[[], bool],
    grace_s: int = GRACE_S,
    poll_s: float = 0.5,
) -> bool:
    """Block until in-flight runs finish or the grace window elapses.

    Returns True if all in-flight runs finished cleanly, False if we
    timed out and will exit with runs still mid-flight (their snapshots
    will be picked up by the next replica via resume_all_in_progress).
    """
    deadline = asyncio.get_event_loop().time() + grace_s
    while has_in_flight():
        if asyncio.get_event_loop().time() >= deadline:
            return False
        await asyncio.sleep(poll_s)
    return True

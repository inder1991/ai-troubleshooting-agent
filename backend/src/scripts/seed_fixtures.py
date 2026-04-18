"""Load demo fixtures into the running Postgres so the UI shows populated.

Idempotent — re-running deletes the seeded rows first (identified by a
fixed prefix) and re-inserts. Safe to run repeatedly.

Use:

    python -m src.scripts.seed_fixtures           # via compose: `make seed`
    python -m src.scripts.seed_fixtures --clear   # remove fixtures only

What it inserts:

  - 3 ``investigation_dag_snapshot`` rows representing finished
    investigations with deterministic synthetic findings (oom-cascade,
    deploy-regression, retry-storm — pulled from the Phase-4 signature
    library so the UI can demo each).
  - 1 ``agent_priors`` row per agent so the priors UI shows real data.

Does NOT touch:

  - ``backend_call_audit`` (would require fake LLM call records — adds noise).
  - ``incident_feedback`` (would have to fabricate user judgements — would
    pollute the priors-feedback loop in unintuitive ways for demos).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Repo-root sys.path setup so this works whether invoked from /app or anywhere.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND_ROOT.parent / ".env")
except Exception:  # noqa: BLE001
    pass


logger = logging.getLogger("seed_fixtures")

# All seeded run_ids share this prefix so --clear can find them precisely
# without touching real data.
SEED_RUN_ID_PREFIX = "seed-fixture-"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_snapshots() -> list[dict[str, Any]]:
    """Three deterministic finished investigations covering different signature
    patterns so the UI demonstrates the breadth of evidence types."""
    return [
        {
            "run_id": f"{SEED_RUN_ID_PREFIX}oom-cascade-001",
            "payload": {
                "session_id": f"{SEED_RUN_ID_PREFIX}oom-cascade-001",
                "service_name": "checkout-api",
                "phase": "completed",
                "patient_zero": {
                    "service": "checkout-api",
                    "evidence": "Pod OOMKilled 3× in last 5m; memory RSS spiked from 280 MiB to 1.8 GiB at 14:02 UTC",
                },
                "stop_reason": "high_confidence_finding",
                "winning_agents": ["log_agent", "metrics_agent", "k8s_agent"],
                "signature_match": {
                    "pattern_id": "oom_cascade",
                    "confidence": 0.92,
                },
                "self_consistency": {"n_runs": 3, "agreed_count": 3},
                "coverage_gaps": [],
            },
        },
        {
            "run_id": f"{SEED_RUN_ID_PREFIX}deploy-regression-002",
            "payload": {
                "session_id": f"{SEED_RUN_ID_PREFIX}deploy-regression-002",
                "service_name": "search-api",
                "phase": "completed",
                "patient_zero": {
                    "service": "search-api",
                    "evidence": "Error rate jumped 18× immediately after deploy at 09:14 UTC of commit a3f1e22",
                },
                "stop_reason": "high_confidence_finding",
                "winning_agents": ["code_agent", "log_agent"],
                "signature_match": {
                    "pattern_id": "deploy_regression",
                    "confidence": 0.88,
                },
                "self_consistency": {"n_runs": 3, "agreed_count": 2},
                "coverage_gaps": [],
            },
        },
        {
            "run_id": f"{SEED_RUN_ID_PREFIX}retry-storm-003",
            "payload": {
                "session_id": f"{SEED_RUN_ID_PREFIX}retry-storm-003",
                "service_name": "billing-api",
                "phase": "completed",
                "patient_zero": {
                    "service": "billing-api",
                    "evidence": "Outbound retry rate to payment-gateway climbed 12× in 90s with no success rate change",
                },
                "stop_reason": "evidence_budget_exhausted",
                "winning_agents": ["metrics_agent"],
                "signature_match": {
                    "pattern_id": "retry_storm",
                    "confidence": 0.71,
                },
                "self_consistency": None,
                "coverage_gaps": [
                    {"backend": "log_agent", "reason": "elasticsearch_unreachable"},
                ],
            },
        },
    ]


def _build_priors() -> list[dict[str, Any]]:
    """One row per agent so the priors UI has data to render."""
    agents = [
        ("log_agent", 0.62),
        ("metrics_agent", 0.71),
        ("k8s_agent", 0.55),
        ("code_agent", 0.48),
        ("network_agent", 0.40),
    ]
    return [
        {
            "agent_name": name,
            "prior_pos": prior,
            "n_observations": 14,
            "updated_at": _now_iso(),
        }
        for name, prior in agents
    ]


# ─── Database I/O ────────────────────────────────────────────────────────────


async def _clear() -> int:
    from sqlalchemy import delete

    from src.database.engine import get_session
    from src.database.models import DagSnapshot

    async with get_session() as session:
        async with session.begin():
            stmt = delete(DagSnapshot).where(
                DagSnapshot.run_id.like(f"{SEED_RUN_ID_PREFIX}%")
            )
            result = await session.execute(stmt)
            return result.rowcount or 0


async def _insert_snapshots(rows: list[dict[str, Any]]) -> int:
    from src.database.engine import get_session
    from src.database.models import DagSnapshot

    async with get_session() as session:
        async with session.begin():
            for row in rows:
                session.add(DagSnapshot(run_id=row["run_id"], payload=row["payload"]))
    return len(rows)


async def _insert_priors(rows: list[dict[str, Any]]) -> int:
    """Best-effort priors insert — silently skips if the table doesn't exist
    yet (Phase 4 priors migration may not have been applied in dev)."""
    try:
        from sqlalchemy import text

        from src.database.engine import get_session

        async with get_session() as session:
            async with session.begin():
                # Use upsert so re-runs are idempotent without a clear step.
                for row in rows:
                    await session.execute(
                        text("""
                            INSERT INTO agent_priors (agent_name, prior_pos, n_observations, updated_at)
                            VALUES (:name, :prior, :n, :updated_at)
                            ON CONFLICT (agent_name) DO UPDATE
                              SET prior_pos = EXCLUDED.prior_pos,
                                  n_observations = EXCLUDED.n_observations,
                                  updated_at = EXCLUDED.updated_at
                        """),
                        {
                            "name": row["agent_name"],
                            "prior": row["prior_pos"],
                            "n": row["n_observations"],
                            "updated_at": row["updated_at"],
                        },
                    )
        return len(rows)
    except Exception as e:  # noqa: BLE001
        logger.warning("priors seed skipped (%s) — agent_priors table may not exist yet", type(e).__name__)
        return 0


# ─── Entrypoint ──────────────────────────────────────────────────────────────


async def _amain(clear_only: bool) -> int:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")

    cleared = await _clear()
    logger.info("removed %d previously-seeded snapshot(s)", cleared)

    if clear_only:
        return 0

    snapshots = _build_snapshots()
    n_snap = await _insert_snapshots(snapshots)
    logger.info("inserted %d demo investigation snapshot(s)", n_snap)

    priors = _build_priors()
    n_priors = await _insert_priors(priors)
    if n_priors:
        logger.info("inserted/updated %d agent prior(s)", n_priors)

    logger.info("✓ seed complete — browse to /sessions to see the demo runs")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo fixtures into Postgres.")
    parser.add_argument("--clear", action="store_true", help="Remove previously-seeded fixtures and exit")
    args = parser.parse_args()
    return asyncio.run(_amain(clear_only=args.clear))


if __name__ == "__main__":
    sys.exit(main())

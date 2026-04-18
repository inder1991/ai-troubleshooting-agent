"""Periodic populator for the ``trace_latency_baseline`` table.

Reads recent ``investigation_dag_snapshot`` rows, extracts span durations
per (service, operation) from each snapshot's ``call_chain``, aggregates
a rolling 7-day P99 + sample count, and upserts into
``trace_latency_baseline``.

Run by ``src/workers/main.py`` on a 5-minute cadence.

Design notes
------------
- Pure aggregation; no LLM. 100% deterministic.
- Reads from the same outbox-backed snapshot store the supervisor writes
  to — no separate ingestion pipeline.
- Uses Postgres ``ON CONFLICT DO UPDATE`` so the populator is
  idempotent (multiple instances on different replicas are safe).
- Requires ≥ ``MIN_SAMPLE_COUNT`` observations per (service, op) before
  emitting a row; below threshold the baseline is unreliable and the
  detector returns no findings for that key.
"""
from __future__ import annotations

import asyncio
import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.database.engine import get_session
from src.database.models import DagSnapshot, TraceLatencyBaseline
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Tunables.
WINDOW_DAYS = 7
MIN_SAMPLE_COUNT = 10          # baselines with < N samples are excluded
MAX_SNAPSHOTS_PER_RUN = 2000   # safety valve for huge backfills
DEFAULT_INTERVAL_S = 300       # 5 minutes between runs


async def populate_once() -> dict:
    """One aggregation pass. Returns stats dict for observability.

    Returns ``{"rows_upserted": N, "services_seen": N, "ops_seen": N,
    "snapshots_scanned": N, "error": Optional[str]}``.
    """
    stats = {
        "rows_upserted": 0,
        "services_seen": 0,
        "ops_seen": 0,
        "snapshots_scanned": 0,
        "error": None,
    }
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)

    # (service, operation) -> list[duration_ms]
    buckets: dict[tuple[str, str], list[float]] = {}

    try:
        async with get_session() as session:
            # Read snapshot payloads from the last WINDOW_DAYS worth.
            result = await session.execute(
                sa.select(DagSnapshot.payload)
                .where(DagSnapshot.updated_at >= cutoff)
                .limit(MAX_SNAPSHOTS_PER_RUN)
            )
            for (payload,) in result:
                stats["snapshots_scanned"] += 1
                _harvest_spans(payload, buckets)

        # Compute P99 per bucket; skip under-sampled keys.
        rows: list[dict] = []
        services: set[str] = set()
        ops: set[str] = set()
        for (service, operation), durations in buckets.items():
            if len(durations) < MIN_SAMPLE_COUNT:
                continue
            p99 = _p99(durations)
            rows.append({
                "service_name": service,
                "operation_name": operation,
                "p99_ms_7d": float(p99),
                "sample_count": len(durations),
                "updated_at": datetime.now(timezone.utc),
            })
            services.add(service)
            ops.add(operation)

        stats["services_seen"] = len(services)
        stats["ops_seen"] = len(ops)

        if rows:
            async with get_session() as session:
                async with session.begin():
                    stmt = pg_insert(TraceLatencyBaseline).values(rows)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["service_name", "operation_name"],
                        set_={
                            "p99_ms_7d": stmt.excluded.p99_ms_7d,
                            "sample_count": stmt.excluded.sample_count,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )
                    await session.execute(stmt)
                    stats["rows_upserted"] = len(rows)

        logger.info("trace_baseline_populator pass complete", extra={
            "action": "populate_complete",
            "extra": stats,
        })
    except Exception as e:
        logger.exception("trace_baseline_populator pass failed")
        stats["error"] = str(e)

    return stats


async def run_forever(interval_s: int = DEFAULT_INTERVAL_S) -> None:
    """Long-running loop that runs ``populate_once`` every ``interval_s``.

    Cancellation propagates immediately. Other exceptions are logged and
    the loop continues on the next tick — one bad pass doesn't kill the
    populator.
    """
    logger.info("trace_baseline_populator starting (interval_s=%d)", interval_s)
    while True:
        try:
            await populate_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("populate_once crashed; continuing")
        await asyncio.sleep(interval_s)


# ── Pure-logic helpers ──────────────────────────────────────────────────


def _harvest_spans(
    snapshot_payload: Optional[dict], buckets: dict[tuple[str, str], list[float]]
) -> None:
    """Extract (service, op) → duration_ms pairs from a DAG-snapshot payload.

    The payload shape comes from TraceAnalysisResult.model_dump() when
    tracing_agent succeeded; absent traces contribute nothing.
    """
    if not isinstance(snapshot_payload, dict):
        return
    trace = snapshot_payload.get("trace_analysis")
    if not isinstance(trace, dict):
        return
    for span in trace.get("call_chain") or []:
        if not isinstance(span, dict):
            continue
        service = span.get("service_name") or span.get("service")
        operation = span.get("operation_name") or span.get("operation")
        duration = span.get("duration_ms")
        if not service or not operation:
            continue
        if not isinstance(duration, (int, float)) or duration <= 0:
            continue
        buckets.setdefault((str(service), str(operation)), []).append(float(duration))


def _p99(durations: list[float]) -> float:
    """Inclusive P99. Falls back to ``max`` when sample count is tiny."""
    if len(durations) <= 2:
        return max(durations)
    sorted_d = sorted(durations)
    idx = max(0, int(0.99 * len(sorted_d)) - 1)
    return sorted_d[idx]


# ── Fetcher API consumed by TracingAgent (sync wrapper for baseline_fetcher arg) ──


def build_baseline_fetcher():
    """Return a sync fetcher suitable for passing to ``TracingAgent`` as
    ``config.baseline_fetcher``.

    The ``BaselineRegressionDetector`` expects a callable with signature
    ``(service, operation) -> Optional[tuple[p99_ms, sample_count]]``.
    The table is small enough that a simple per-call SELECT is fine; if
    latency becomes a concern we can add a TTL cache.
    """
    import threading

    _cache: dict[tuple[str, str], tuple[float, int]] = {}
    _cache_lock = threading.Lock()
    _cache_expiry: dict[str, datetime] = {"at": datetime.now(timezone.utc)}
    CACHE_TTL_S = 60  # refresh per-process cache once a minute

    def fetcher(service_name: str, operation_name: str) -> Optional[tuple[float, int]]:
        with _cache_lock:
            now = datetime.now(timezone.utc)
            if (now - _cache_expiry["at"]).total_seconds() > CACHE_TTL_S:
                _cache.clear()
                _cache_expiry["at"] = now
            if (service_name, operation_name) in _cache:
                return _cache[(service_name, operation_name)]

        # Need a DB lookup. This is synchronous to match the detector's
        # signature; runs once per unique (service, op) per minute per
        # process.
        try:
            # Lazy sync-engine import — not all call sites can await.
            from sqlalchemy import create_engine
            from src.database.engine import DATABASE_URL

            sync_url = DATABASE_URL.replace("+asyncpg", "")
            engine = create_engine(sync_url, echo=False, future=True)
            with engine.connect() as conn:
                row = conn.execute(
                    sa.text(
                        "SELECT p99_ms_7d, sample_count "
                        "FROM trace_latency_baseline "
                        "WHERE service_name = :svc AND operation_name = :op"
                    ),
                    {"svc": service_name, "op": operation_name},
                ).fetchone()
            engine.dispose()
        except Exception:
            logger.exception("baseline fetcher DB lookup failed")
            return None

        if row is None:
            return None
        result = (float(row[0]), int(row[1]))
        with _cache_lock:
            _cache[(service_name, operation_name)] = result
        return result

    return fetcher

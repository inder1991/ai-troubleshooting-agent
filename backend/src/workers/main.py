"""Worker dispatcher — collapses every long-running background loop into a
single process so production runs ``backend-worker`` as one Deployment.

Subsystems brought up:

  - **OutboxRelay** (``src.workflows.outbox_relay``) — drains the Postgres
    outbox table to Redis Streams + SSE sinks. Long-running.
  - **Resume scan** (``src.workflows.resume.resume_all_in_progress``) — one-
    shot on startup; gated by ``DIAGNOSTIC_RESUME_ON_STARTUP=on``. Picks up
    orphaned runs left behind by a crashed pod.
  - **Drain handler** — SIGTERM/SIGINT trigger graceful shutdown via
    ``DrainState`` so in-flight investigations checkpoint before SIGKILL.

Operational contract:

  - Process exits 0 on clean drain, 1 on uncaught exception.
  - On SIGTERM, drain flag flips immediately. New work is rejected. The
    process waits up to ``WORKER_DRAIN_GRACE_S`` (default 110s — paired
    with the chart's ``terminationGracePeriodSeconds: 120``) for in-flight
    work to checkpoint.
  - All subsystem failures log at ``error`` level but do NOT crash the
    process — the relay/scanner restart on the next iteration.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

# Ensure repo-root paths resolve when invoked from anywhere (compose, k8s, dev).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# Side-effect: load .env when running outside docker (e.g. local pytest).
try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND_ROOT.parent / ".env")
except Exception:  # noqa: BLE001 — .env is optional
    pass


logger = logging.getLogger("workers")

# ─── Configuration ───────────────────────────────────────────────────────────

DRAIN_GRACE_S = int(os.environ.get("WORKER_DRAIN_GRACE_S", "110"))
RESUME_ON_STARTUP = os.environ.get("DIAGNOSTIC_RESUME_ON_STARTUP", "off").lower() == "on"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def _setup_logging() -> None:
    """JSON-ish single-line logging suitable for stdout pickup."""
    logging.basicConfig(
        level=LOG_LEVEL,
        format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)r}',
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


# ─── Subsystem launchers ─────────────────────────────────────────────────────


async def _start_outbox_relay() -> asyncio.Task[None]:
    """Boot the OutboxRelay → Redis Streams sink.

    The Redis sink is the production transport; SSE fan-out is per-pod and
    happens in the web process, not here.
    """
    from src.workflows.outbox_relay import OutboxRelay, RedisStreamSink

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    import redis.asyncio as redis_async

    client = redis_async.from_url(redis_url, decode_responses=False)
    relay = OutboxRelay(sink=RedisStreamSink(client))
    logger.info("starting outbox relay (redis_url=%s)", _redact(redis_url))
    return asyncio.create_task(_supervised(relay.run_forever, "outbox_relay"))


async def _start_trace_baseline_populator() -> asyncio.Task[None]:
    """Boot the TA-PR2b baseline populator.

    Aggregates P99 latency per (service, operation) from recent
    DagSnapshot rows every 5 minutes. Feeds the
    ``BaselineRegressionDetector`` so it emits real findings.
    """
    from src.workers.trace_baseline_populator import (
        DEFAULT_INTERVAL_S,
        run_forever as baseline_run_forever,
    )
    interval_s = int(os.environ.get("TRACE_BASELINE_INTERVAL_S", str(DEFAULT_INTERVAL_S)))
    logger.info("starting trace baseline populator (interval_s=%d)", interval_s)
    async def _loop() -> None:
        await baseline_run_forever(interval_s=interval_s)
    return asyncio.create_task(_supervised(_loop, "trace_baseline_populator"))


async def _run_resume_scan() -> None:
    """Log-only scan for orphaned runs (Stage K subset).

    Real dispatch (calling supervisor.run on each orphan) is the deferred
    work captured in the orchestration-swap verification doc. Until then,
    operators see which runs WOULD have been picked up.
    """
    if not RESUME_ON_STARTUP:
        logger.info("resume scan disabled (set DIAGNOSTIC_RESUME_ON_STARTUP=on to enable)")
        return

    from src.workflows.resume import select_orphaned_running

    try:
        orphans = await select_orphaned_running()
    except Exception:
        logger.exception("resume scan: failed to query orphaned runs")
        return

    if not orphans:
        logger.info("resume scan: no orphaned runs found")
        return

    for run in orphans:
        logger.warning(
            "resume scan: orphaned run found — would dispatch (real dispatch pending route-layer factory): run_id=%s",
            run.run_id,
        )


async def _supervised(coro_factory: Any, name: str) -> None:
    """Run a long-lived coroutine; restart with backoff on unexpected exit.

    Cancellation (drain) propagates immediately. Other exceptions are logged
    and the loop restarts after a backoff to keep the process up.
    """
    backoff_s = 1.0
    max_backoff_s = 30.0

    while True:
        try:
            await coro_factory()
            # Clean return → unexpected for run_forever; treat as restart.
            logger.warning("%s exited cleanly; restarting in %.1fs", name, backoff_s)
        except asyncio.CancelledError:
            logger.info("%s cancelled; exiting subsystem cleanly", name)
            raise
        except Exception:
            logger.exception("%s crashed; restarting in %.1fs", name, backoff_s)

        await asyncio.sleep(backoff_s)
        backoff_s = min(backoff_s * 2, max_backoff_s)


def _redact(url: str) -> str:
    """Mask passwords in connection strings for safe logging."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        creds, host = rest.rsplit("@", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            return f"{scheme}://{user}:***@{host}"
    return url


# ─── Drain orchestration ─────────────────────────────────────────────────────


class _Lifecycle:
    """Holds the single drain event the signal handler flips."""

    def __init__(self) -> None:
        self._drain_event = asyncio.Event()

    def request_drain(self) -> None:
        if not self._drain_event.is_set():
            logger.info("drain requested — finishing in-flight work, will exit on completion")
            self._drain_event.set()
            # Flip the process-wide drain flag so the supervisor stops accepting new runs.
            try:
                from src.workflows.resume import get_drain_state

                get_drain_state().start_drain()
            except Exception:  # noqa: BLE001
                logger.exception("could not flip global drain state")

    async def wait_for_drain(self) -> None:
        await self._drain_event.wait()


def _install_signal_handlers(lifecycle: _Lifecycle, loop: asyncio.AbstractEventLoop) -> None:
    """Wire SIGTERM + SIGINT to drain. SIGKILL can't be caught — that's the
    job of ``terminationGracePeriodSeconds`` on the chart."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lifecycle.request_drain)


# ─── Main ────────────────────────────────────────────────────────────────────


async def _amain() -> int:
    _setup_logging()
    logger.info("worker dispatcher starting (drain_grace_s=%d, resume_on_startup=%s)",
                DRAIN_GRACE_S, RESUME_ON_STARTUP)

    lifecycle = _Lifecycle()
    _install_signal_handlers(lifecycle, asyncio.get_running_loop())

    # 1. One-shot startup work.
    await _run_resume_scan()

    # 2. Long-running subsystems.
    relay_task = await _start_outbox_relay()
    baseline_task = await _start_trace_baseline_populator()
    long_running: list[asyncio.Task[None]] = [relay_task, baseline_task]

    # 3. Block until drain requested.
    await lifecycle.wait_for_drain()

    # 4. Drain — cancel subsystems, then await with grace.
    for t in long_running:
        t.cancel()

    drain_deadline = asyncio.get_running_loop().time() + DRAIN_GRACE_S
    for t in long_running:
        remaining = max(0.0, drain_deadline - asyncio.get_running_loop().time())
        with suppress(asyncio.CancelledError):
            try:
                await asyncio.wait_for(t, timeout=remaining)
            except asyncio.TimeoutError:
                logger.warning("subsystem %s exceeded drain grace (%ds); force-killing", t.get_name(), DRAIN_GRACE_S)

    logger.info("worker dispatcher exited cleanly")
    return 0


def main() -> int:
    """Entry point — ``python -m src.workers.main``."""
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 0
    except Exception:
        logging.getLogger("workers").exception("worker dispatcher crashed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

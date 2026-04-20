"""Nightly reconciliation — compares ledger.txns vs. bank settlements.

Storyboard role:
    This file houses BUG #3 — the signal suppressor. At roughly line
    88 (see the guard below) a $0.02 auto-round threshold silently
    absorbs any diff smaller than two cents.

    The threshold was added 3 years ago to paper over Bug #2's
    floating-point drift (see reconcile.money). It is doing exactly
    what it was designed to do. Unfortunately the duplicate-charge
    diffs ALSO come in as sub-cent values after the float-based sum,
    so they get swallowed too. The bug has been running silently for
    ~6 weeks of the storyboard timeline.

    The fix (PR-K6 RemediationCampaign): lower threshold to $0.001
    and escalate any sub-cent diff ≥ $0.01 as a P3 alert. Deferred
    so the bug runs live.

Entry points:
    · run_once(day: str)           — in-process entry, returns the
                                      per-currency diffs as dicts.
    · main()                        — CronJob entry; reads TZ + day
                                      env vars and calls run_once.
    · /demo/run-now (via reconcile_web.py) — the demo-controller
                                      can trigger a fresh reconcile
                                      mid-demo without waiting for
                                      3am.

Metrics:
    · reconciliation_drift_dollars{currency}   — gauge, raw diff
    · reconciliation_subcent_drift_total       — counter; incremented
      every time the threshold swallows a sub-cent diff (the signal
      we SHOULD be pulling into alerting but aren't)
"""
import logging
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from prometheus_client import Counter, Gauge, CollectorRegistry, generate_latest

from .money import Currency, Money, sum_money
from .bank_mock import fetch_bank_settlements

# Configured via env so the fix-time version can override from $0.02
# → $0.001 without a code change. Default stays broken for the demo.
AUTO_ROUND_THRESHOLD_DOLLARS = float(os.environ.get("RECONCILE_AUTO_ROUND_USD", "0.02"))
MINOR_DRIFT_THRESHOLD_DOLLARS = float(os.environ.get("RECONCILE_MINOR_DRIFT_USD", "1.00"))

log = logging.getLogger("reconciliation-job")

# Per-process registry so run_once() is re-entrant — each web-driven
# invocation creates a fresh set of counters and emits them as its
# own /metrics scrape would see. For the pod-level CronJob the
# default global registry is used instead.
_REGISTRY = CollectorRegistry()
drift_gauge = Gauge(
    "reconciliation_drift_dollars",
    "Per-currency drift between bank settlement and ledger (post-round).",
    labelnames=["currency"],
    registry=_REGISTRY,
)
subcent_drift_counter = Counter(
    "reconciliation_subcent_drift_total",
    "Count of reconciliations where the diff fell under the auto-round "
    "threshold and was silently absorbed. Bug #3 hides behind this "
    "counter — nobody alerts on it.",
    registry=_REGISTRY,
)
processed_counter = Counter(
    "reconciliation_runs_total",
    "Count of reconciliation runs, dimensioned on outcome.",
    labelnames=["outcome"],
    registry=_REGISTRY,
)


def _pg_dsn() -> str:
    return (
        f"host={os.environ.get('PG_HOST', 'postgres')} "
        f"port={os.environ.get('PG_PORT', '5432')} "
        f"user={os.environ.get('PG_USER', 'zepay')} "
        f"password={os.environ.get('PG_PASSWORD', 'zepay-demo-password')} "
        f"dbname={os.environ.get('PG_DB', 'zepay')}"
    )


def _fetch_ledger_sums(day: str) -> dict[str, Money]:
    """Sum debits-per-currency for `day` by walking ledger.txns in
    100-row chunks, adding each row via Money.plus(). This is the
    path that accumulates IEEE-754 drift (Bug #2)."""
    sums: dict[str, list[Money]] = {}
    with psycopg.connect(_pg_dsn(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT currency, amount_cents
                  FROM ledger.txns
                 WHERE direction = 'debit'
                   AND created_at::date = %s::date
                 ORDER BY created_at
                """,
                (day,),
            )
            for currency, amount_cents in cur.fetchall():
                m = Money(amount=amount_cents / 100.0, currency=Currency(currency))
                sums.setdefault(currency, []).append(m)
    return {cur: sum_money(rows) for cur, rows in sums.items()}


# ─────────────────────────────────────────────────────────────────
def run_once(day: str) -> list[dict[str, Any]]:
    """Compare ledger.txns against the bank-side settlement for `day`.

    Returns per-currency result dicts. Writes metrics into the
    per-process registry; a sibling HTTP handler exposes them.
    """
    bank = {s.currency: s for s in fetch_bank_settlements(day)}
    ledger = _fetch_ledger_sums(day)

    currencies = sorted(set(bank) | set(ledger))
    results: list[dict[str, Any]] = []

    for currency in currencies:
        bank_cents = bank[currency].total_cents if currency in bank else 0
        ledger_money = ledger.get(currency, Money(0.0, Currency(currency)))

        # The SAME lossy conversion payment-service performs when it
        # writes to the ledger. Both sides drift identically — which
        # is what makes the diff look like honest floating-point
        # noise instead of a real duplicate-charge signal.
        ledger_cents = ledger_money.to_minor_units()

        diff_cents = bank_cents - ledger_cents
        diff_dollars = diff_cents / 100.0
        drift_gauge.labels(currency=currency).set(diff_dollars)

        # ─── Lines ~82-96 — this is where Bug #3 lives ────────────
        # Storyboard §2 calls this out verbatim; keep the prose in
        # sync with the file the code_agent will read.
        if abs(diff_dollars) < AUTO_ROUND_THRESHOLD_DOLLARS:
            # Line 88 of the storyboard. Swallows the signal.
            log.info(
                "reconciled within tolerance: diff=$%.4f currency=%s "
                "(auto-round threshold=$%.4f)",
                diff_dollars, currency, AUTO_ROUND_THRESHOLD_DOLLARS,
            )
            subcent_drift_counter.inc()
            processed_counter.labels(outcome="auto_rounded").inc()
            results.append({
                "currency": currency,
                "diff_dollars": diff_dollars,
                "outcome": "auto_rounded",
                "bank_cents": bank_cents,
                "ledger_cents": ledger_cents,
            })
            continue

        if abs(diff_dollars) < MINOR_DRIFT_THRESHOLD_DOLLARS:
            log.warning(
                "minor drift detected: diff=$%.4f currency=%s; auto-adjusting",
                diff_dollars, currency,
            )
            _adjust_drift(currency, diff_cents)
            processed_counter.labels(outcome="minor_adjusted").inc()
            results.append({
                "currency": currency,
                "diff_dollars": diff_dollars,
                "outcome": "minor_adjusted",
                "bank_cents": bank_cents,
                "ledger_cents": ledger_cents,
            })
            continue

        # Real drift → escalate.
        log.error(
            "RECONCILIATION DRIFT: diff=$%.4f currency=%s bank=$%d ledger=$%d",
            diff_dollars, currency, bank_cents / 100, ledger_cents / 100,
        )
        _alert_finance_oncall(currency, diff_dollars)
        processed_counter.labels(outcome="alerted").inc()
        results.append({
            "currency": currency,
            "diff_dollars": diff_dollars,
            "outcome": "alerted",
            "bank_cents": bank_cents,
            "ledger_cents": ledger_cents,
        })

    return results


def _adjust_drift(currency: str, diff_cents: int) -> None:
    """Mock — in real Zepay this would create a compensating ledger entry."""
    log.info("adjust_drift: currency=%s cents=%d (mock)", currency, diff_cents)


def _alert_finance_oncall(currency: str, diff_dollars: float) -> None:
    """Mock — in real Zepay this would page the finance-ops on-call."""
    log.error("alert_finance_oncall: currency=%s diff=$%.4f (mock)", currency, diff_dollars)


def metrics_bytes() -> bytes:
    """Snapshot the current per-process registry for /metrics."""
    return generate_latest(_REGISTRY)


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format='{"ts":"%(asctime)s","service":"reconciliation-job","level":"%(levelname)s","msg":"%(message)s"}',
    )
    day = os.environ.get("RECONCILE_DAY", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    log.info("reconciliation start day=%s threshold=$%.4f",
             day, AUTO_ROUND_THRESHOLD_DOLLARS)
    results = run_once(day)
    log.info("reconciliation done day=%s results=%s", day, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

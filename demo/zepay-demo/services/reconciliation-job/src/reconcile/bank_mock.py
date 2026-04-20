"""Mock card-network / bank settlement feed.

In production this module would call the bank's daily settlement
API (e.g. ACH file ingest, Visa Base II feed). For the demo we
synthesize the bank's view by reading the Postgres ledger we wrote
ourselves — EXCEPT we inflate the total by the amount of each
confirmed duplicate charge, so the mock "bank" sees the second
debit that the in-app transaction history hides.

That inflation is what produces the real drift the reconciliation
job is supposed to catch (and then fails to, because of Bug #3).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg


@dataclass(frozen=True)
class BankSettlement:
    """Daily settlement as reported by the card network."""
    day: str                 # YYYY-MM-DD in UTC
    currency: str
    total_cents: int         # bank's view of the sum of debits


def _pg_dsn() -> str:
    import os
    return (
        f"host={os.environ.get('PG_HOST', 'postgres')} "
        f"port={os.environ.get('PG_PORT', '5432')} "
        f"user={os.environ.get('PG_USER', 'zepay')} "
        f"password={os.environ.get('PG_PASSWORD', 'zepay-demo-password')} "
        f"dbname={os.environ.get('PG_DB', 'zepay')}"
    )


def fetch_bank_settlements(day: str) -> list[BankSettlement]:
    """Return bank-reported settlements for `day`.

    The mock reads every row in ledger.txns — including the ghost
    debits from the retry bug — and sums by currency. The in-app
    total (computed from payment-service's own counters) will be
    smaller than this by exactly the sum of the ghost debits.
    """
    sql = """
        SELECT currency, COALESCE(SUM(amount_cents), 0) AS total_cents
          FROM ledger.txns
         WHERE direction = 'debit'
           AND created_at::date = %s::date
         GROUP BY currency
    """
    settlements: list[BankSettlement] = []
    with psycopg.connect(_pg_dsn(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (day,))
            for currency, total in cur.fetchall():
                settlements.append(BankSettlement(day=day, currency=currency, total_cents=int(total)))
    return settlements


def _window_for(day: str) -> tuple[datetime, datetime]:
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return d, d + timedelta(days=1)

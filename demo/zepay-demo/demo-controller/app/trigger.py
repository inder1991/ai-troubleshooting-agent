"""Deterministic race-trigger — Option B from the storyboard.

Three of the 47 customers are named (Acme Logistics, Sarah Chen,
@sarah_trades_btc) so they show up in BlastRadiusList's
notable_affected_accounts. The remaining 44 come from the seeded
`C-POOL-*` pool k6 is already hammering.

Steps per customer, in order:
  1. Top up their wallet so balance >= amount (both debits will
     pass the `balance >= :amount` guard in wallet-service).
  2. Trigger a checkout. Because Istio fault is active on 20% of
     /v1/inventory/reserve calls, ~10 of the 47 naturally land in
     the fault window and double-debit. That's too few for a
     dramatic demo — so we explicitly schedule the 3 named
     customers through an Idempotency-Key-absent path that is
     GUARANTEED to hit the 15s fault via an override header the
     VirtualService matches on (the fault YAML's `match` clause
     in PR-K6-fault is extended to include header matches).
  3. Mid-flight, issue a concurrent /v1/topup on the customer 10s
     into the 15s fault window so the retry's second `wallets.UPDATE`
     passes the balance-check.

For this first PR we implement the simpler path: send 47 checkouts
against the existing 20% fault and accept ~9-10 double-charges.
That is enough of a signal for the workflow to detect and is
honest — in production the real bug fires roughly at that rate.
The demo still works because log_agent clusters at 9-10 occurrences;
if we want the full 47 we can enable the header-match path in a
follow-up.
"""
from __future__ import annotations

import logging
import random
import time
import uuid
from typing import List

import httpx

from .state import STATE

log = logging.getLogger("demo-controller.trigger")

# Named customers surfaced on the BlastRadiusList — this list mirrors
# the storyboard narrative so the row labels line up.
NAMED_CUSTOMERS = [
    "C-CORP-ACME-LOG-0042",      # Acme Logistics ($2.1M/month, SLA-tier-1)
    "C-CHEN-SARAH-8741",          # Sarah Chen (184K-follower food blogger)
    "C-INFLUENCER-BTC-2291",      # @sarah_trades_btc (340K crypto followers)
]


def _gateway_url() -> str:
    import os
    return os.environ.get(
        "GATEWAY_URL_FROM_LAPTOP",
        # Default assumes operator port-forwarded api-gateway separately;
        # if not set, the demo-controller hits it via Istio ingress.
        "http://api-gateway.payments-prod.svc.cluster.local:8080",
    )


def trigger_race(count: int = 47) -> list[str]:
    """Fire `count` checkouts at api-gateway, returning the txn_ids used.

    Most go through the background k6 pool; the 3 named customers are
    always included so the BlastRadiusList always has them.
    """
    ids: List[str] = []
    customers = list(NAMED_CUSTOMERS)
    while len(customers) < count:
        customers.append(f"C-POOL-{random.randint(1, 500):04d}")

    url = _gateway_url() + "/api/v1/checkout"
    amount_cents = 8741   # Sarah Chen's $87.41 Nobu order.

    with httpx.Client(timeout=45.0) as client:
        for cid in customers:
            txn_id = f"demo-{uuid.uuid4().hex[:8]}"
            # Top up first so both debits pass the balance guard.
            try:
                client.post(
                    # Seeds balance via wallet-service direct — the
                    # demo-controller happens to have port-forward
                    # access from the operator's laptop.
                    _wallet_url() + "/v1/topup",
                    json={"customer_id": cid, "amount_cents": amount_cents * 3, "currency": "USD"},
                )
            except Exception as e:
                log.warning("pre-trigger topup failed cid=%s err=%s", cid, e)

            try:
                resp = client.post(
                    url,
                    json={
                        "customer_id":   cid,
                        "cart_id":       f"cart-{txn_id}",
                        "amount_cents":  amount_cents,
                        "currency":      "USD",
                    },
                    # Intentionally NO Idempotency-Key — matches the
                    # pre-fix Zepay code path that produces Bug #1.
                )
                ids.append(txn_id)
                log.info("checkout fired cid=%s txn=%s http=%d",
                         cid, txn_id, resp.status_code)
            except Exception as e:
                log.error("checkout failed cid=%s err=%s", cid, e)

            # Small jitter so the 47 don't land all at once.
            time.sleep(0.05 + random.random() * 0.1)

    incident_id = f"INC-{time.strftime('%Y%m%d', time.gmtime())}-payment-ledger-ghost-debits"
    STATE.mark_triggered(incident_id, ids)
    return ids


def _wallet_url() -> str:
    import os
    return os.environ.get(
        "WALLET_URL_FROM_LAPTOP",
        "http://wallet-service.payments-prod.svc.cluster.local:8087",
    )

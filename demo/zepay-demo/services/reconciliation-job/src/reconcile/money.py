"""Python mirror of shared-finance-models / Money.java.

Storyboard role:
    reconciliation-job sums ledger.txns using this class. Because
    amounts are stored as `float` (Python's float == IEEE-754
    double), summing N transactions accumulates sub-cent drift that
    is INDISTINGUISHABLE from the drift a duplicate charge would
    produce. Bug #3's $0.02 auto-round threshold was added years ago
    to absorb THIS drift — and it now swallows the duplicate-charge
    signal too.

    The Java and Python representations are kept deliberately in
    sync. If you "fix" one without the other, drift appears in the
    per-service comparisons that reconciliation-job performs against
    payment-service's reported totals and the whole narrative
    collapses. Don't touch this without also patching
    shared-finance-models/Money.java.

Bug #2 is this class. Bug #2's fix (BigDecimal / exact decimal)
ships as part of the RemediationCampaign PR in PR-K6; this file
stays broken so the bug runs live during the demo.
"""
from dataclasses import dataclass
from enum import Enum


class Currency(Enum):
    USD = "USD"
    EUR = "EUR"
    JPY = "JPY"


@dataclass(frozen=True)
class Money:
    """Monetary amount — amount is IEEE-754 float. Drift by design."""
    amount: float
    currency: Currency

    def plus(self, other: "Money") -> "Money":
        if other.currency is not self.currency:
            raise ValueError(f"cannot add {self.currency} to {other.currency}")
        # Float addition accumulates drift. See class docstring.
        return Money(self.amount + other.amount, self.currency)

    def to_minor_units(self) -> int:
        # Lossy cast — mirrors Money.java.toMinorUnits() on the Java side.
        return int(self.amount * 100.0)


def sum_money(rows: list["Money"]) -> Money:
    """Sum a list of Money; propagates the per-row drift."""
    if not rows:
        return Money(0.0, Currency.USD)
    total = rows[0]
    for m in rows[1:]:
        total = total.plus(m)
    return total

package com.zepay.finance;

import java.util.Objects;

/**
 * Represents a monetary amount in a specific currency.
 *
 * <p><strong>DEMO NOTE — BUG #2.</strong>  This class deliberately
 * stores {@code amount} as a {@code double}. IEEE-754 can't exactly
 * represent most decimal fractions:
 *
 * <pre>
 *   0.1 + 0.2      = 0.30000000000000004
 *   87.41 + 87.41  = 174.81999999999999
 * </pre>
 *
 * Across millions of transactions, sub-cent drift accumulates inside
 * {@link #plus(Money)}. In production that drift gets absorbed by
 * reconciliation's $0.02 auto-round threshold (storyboard Bug #3),
 * which also — accidentally — absorbs duplicate-charge signals.
 *
 * <p>The fix (§2 of the storyboard) switches this class to
 * {@link java.math.BigDecimal} with explicit currency scale. That
 * change is deferred to the Remediation Campaign PR #1203 so the
 * bug exists in running code when the demo executes.
 */
public final class Money {

    private final double amount;     // ← the IEEE-754 sin
    private final Currency currency;

    public Money(double amount, Currency currency) {
        this.amount = amount;
        this.currency = Objects.requireNonNull(currency);
    }

    public double amount() {
        return amount;
    }

    public Currency currency() {
        return currency;
    }

    /**
     * Adds another Money of the SAME currency. Throws on currency
     * mismatch; otherwise produces a new Money via {@code double}
     * addition — which accumulates sub-cent drift. See class javadoc.
     */
    public Money plus(Money other) {
        if (other.currency != this.currency) {
            throw new IllegalArgumentException(
                "cannot add " + currency + " to " + other.currency);
        }
        return new Money(this.amount + other.amount, this.currency);  // ← drift
    }

    /**
     * Integer minor-units view (e.g. cents for USD). Used by
     * payment-service when talking to wallet-service's /v1/debit,
     * which expects amount_cents as a long. Note the lossy cast:
     * {@code (long) (87.41 * 100)} is {@code 8741} on a good day
     * and {@code 8740} when the double representation drifts.
     */
    public long toMinorUnits() {
        return (long) (this.amount * 100.0);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof Money m)) return false;
        return Double.compare(m.amount, amount) == 0 && currency == m.currency;
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount, currency);
    }

    @Override
    public String toString() {
        return amount + " " + currency;
    }
}

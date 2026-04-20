package com.zepay.payment.ledger;

import com.zepay.finance.Currency;
import com.zepay.finance.Money;
import com.zepay.payment.http.PaymentRequest;
import com.zepay.payment.http.PaymentResult;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Recover;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Orchestrates a single payment: debit the customer's wallet, then
 * reserve inventory.
 *
 * <h2>DEMO NOTE — BUG #1 (primary cause)</h2>
 *
 * <p>{@link #execute(PaymentRequest)} is annotated {@code @Retryable}
 * catching {@link UpstreamTimeoutException}. When Istio's fault
 * injection delays the {@link InventoryClient#reserve} call past the
 * 15-second read-timeout, the method re-runs — including the already-
 * successful call to {@link LedgerClient#debit}. The customer is
 * debited twice with two different {@code txn_id}s.
 *
 * <p>The fix (§2 of the storyboard, PR-K4-fix): pass an idempotency
 * key that makes {@code ledger.debit} return the existing txn when
 * called with the same key; OR move the mutation outside the retry
 * boundary and retry only the non-mutating reserve. Both changes
 * are deferred; we want the bug to be live when the demo runs.
 */
@Service
public class PaymentExecutor {

    private static final Logger log = LoggerFactory.getLogger(PaymentExecutor.class);

    private final LedgerClient    ledger;
    private final InventoryClient inventoryClient;

    /** Every attempt bumps this — visible in the retry log lines. */
    private final AtomicInteger retryAttempt = new AtomicInteger(1);

    private final Counter paymentLedgerWriteTotal;
    private final Counter paymentLedgerWriteRetry;

    public PaymentExecutor(
        LedgerClient ledger,
        InventoryClient inventoryClient,
        MeterRegistry meters
    ) {
        this.ledger = ledger;
        this.inventoryClient = inventoryClient;

        // metrics_agent queries these names verbatim. Don't rename.
        this.paymentLedgerWriteTotal = Counter.builder("payment_ledger_write_total")
            .tag("retry", "false")
            .register(meters);
        this.paymentLedgerWriteRetry = Counter.builder("payment_ledger_write_total")
            .tag("retry", "true")
            .register(meters);
    }

    // ───────────────────────────────────────────────────────────────
    //      ⚠ BUG #1 lives here (storyboard §2, file:line 127) ⚠
    // ───────────────────────────────────────────────────────────────
    @Retryable(
        retryFor   = { UpstreamTimeoutException.class },
        maxAttempts = 2,
        backoff    = @Backoff(delay = 200)
    )
    public PaymentResult execute(PaymentRequest req) {
        int attempt = retryAttempt.get();
        if (attempt > 1) {
            // This is the INFO log line log_agent clusters against:
            //   "RetryAttempt=2 for inventory-reserve"
            log.info(
                "RetryAttempt={} for inventory-reserve customer_id={} cart_id={}",
                attempt, req.customer_id(), req.cart_id());
            paymentLedgerWriteRetry.increment();
        } else {
            paymentLedgerWriteTotal.increment();
        }

        // Money construction via the double-based shared library (Bug #2).
        // We don't USE the Money arithmetic here; what matters is that
        // reconciliation-job sums these amounts later using the same
        // double-based class, and THAT's where Bug #2's drift masks the
        // duplicate-charge signal. Keeping the construction realistic.
        Money amount = new Money(req.amount_cents() / 100.0, Currency.valueOf(req.currency()));
        log.debug("payment amount constructed: {}", amount);

        // ── Line 127: the mutation, inside the retry boundary. ──
        LedgerTxn txn = ledger.debit(req.customer_id(), req.amount_cents(), req.currency());

        // The call Istio's fault delays 15s; throws UpstreamTimeoutException
        // on ~20% of requests while fault is active. The @Retryable above
        // catches it and re-runs this whole method — including ledger.debit.
        inventoryClient.reserve(req.cart_id(), List.of(
            Map.of("sku", "ITEM", "qty", 1)
        ));

        retryAttempt.incrementAndGet();
        return PaymentResult.success(txn.id());
    }

    /**
     * Spring Retry calls this when all attempts are exhausted.
     * Rethrows so the HTTP layer returns 5xx; in the demo we rely
     * on the SECOND attempt succeeding (because the Istio fault only
     * delays 20% of requests, the retry almost always passes).
     */
    @Recover
    public PaymentResult recover(UpstreamTimeoutException e, PaymentRequest req) {
        log.error("payment recover: retries exhausted customer_id={} cause={}",
            req.customer_id(), e.getMessage());
        throw e;
    }
}

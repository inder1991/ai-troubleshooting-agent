package com.zepay.payment.ledger;

/**
 * Thrown when an upstream HTTP call takes longer than our configured
 * 15-second read-timeout. Spring's {@code @Retryable} is wired to
 * catch this exact type (see {@link PaymentExecutor}), which is the
 * defect that re-runs the ledger mutation.
 */
public class UpstreamTimeoutException extends RuntimeException {
    public UpstreamTimeoutException(String message, Throwable cause) {
        super(message, cause);
    }
}

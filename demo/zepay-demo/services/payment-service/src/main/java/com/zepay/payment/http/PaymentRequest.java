package com.zepay.payment.http;

/**
 * Inbound JSON from checkout-service. No validation annotations —
 * this is a demo; real Zepay would have @Valid here.
 */
public record PaymentRequest(
    String customer_id,
    String cart_id,
    long   amount_cents,
    String currency
) {}

package com.zepay.payment.http;

public record PaymentResult(String txn_id, String status) {
    public static PaymentResult success(String txnId) {
        return new PaymentResult(txnId, "SUCCESS");
    }
}

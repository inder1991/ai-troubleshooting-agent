package com.zepay.payment.ledger;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;

/**
 * Thin HTTP client for wallet-service's /v1/debit. Every call mints
 * a fresh {@code txn_id}; deduplication is the CALLER's responsibility
 * (storyboard §2 Bug #1: the caller, {@link PaymentExecutor}, forgets
 * to pass an idempotency key, so the retry bug produces two debits
 * with two different txn_ids).
 */
@Component
public class LedgerClient {

    private static final Logger log = LoggerFactory.getLogger(LedgerClient.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final HttpClient http;
    private final String walletUrl;

    public LedgerClient(@Value("${zepay.wallet-url:http://wallet-service:8087}") String walletUrl) {
        this.walletUrl = walletUrl;
        this.http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    }

    public LedgerTxn debit(String customerId, long amountCents, String currency) {
        String txnId = "T-" + UUID.randomUUID();
        try {
            String body = MAPPER.writeValueAsString(Map.of(
                "customer_id",  customerId,
                "amount_cents", amountCents,
                "currency",     currency,
                "txn_id",       txnId
            ));

            HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(walletUrl + "/v1/debit"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());

            if (resp.statusCode() >= 400) {
                throw new RuntimeException(
                    "ledger debit " + resp.statusCode() + ": " + resp.body());
            }

            log.info("ledger debit OK customer_id={} txn_id={} amount_cents={}",
                customerId, txnId, amountCents);
            return new LedgerTxn(txnId);

        } catch (java.io.IOException | InterruptedException e) {
            throw new RuntimeException("ledger debit IO error", e);
        } catch (Exception e) {
            throw new RuntimeException("ledger debit error", e);
        }
    }
}

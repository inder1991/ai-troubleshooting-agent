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
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * HTTP client for inventory-service's /v1/reserve — the call that
 * the Istio fault-injection VirtualService delays 15 seconds. We set
 * an explicit 15-second read-timeout; Istio's 15s delay trips it
 * reliably, turning the upstream call into an
 * {@link UpstreamTimeoutException}, which Spring's {@code @Retryable}
 * on {@link PaymentExecutor#execute} catches and re-runs.
 */
@Component
public class InventoryClient {

    private static final Logger log = LoggerFactory.getLogger(InventoryClient.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final HttpClient http;
    private final String inventoryUrl;

    public InventoryClient(
        @Value("${zepay.inventory-url:http://inventory-service:8086}") String inventoryUrl
    ) {
        this.inventoryUrl = inventoryUrl;
        this.http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    }

    public void reserve(String orderId, List<Map<String, Object>> items) {
        try {
            String body = MAPPER.writeValueAsString(Map.of(
                "order_id", orderId,
                "items",    items
            ));

            HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(inventoryUrl + "/v1/reserve"))
                // 15s — the precise boundary Istio's fault trips at.
                .timeout(Duration.ofSeconds(15))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());

            if (resp.statusCode() >= 500) {
                throw new UpstreamTimeoutException(
                    "inventory 5xx (" + resp.statusCode() + ")", null);
            }
            if (resp.statusCode() >= 400) {
                throw new RuntimeException(
                    "inventory reserve " + resp.statusCode() + ": " + resp.body());
            }
            log.info("inventory reserve OK order_id={}", orderId);

        } catch (HttpTimeoutException e) {
            // HttpConnectTimeoutException extends HttpTimeoutException,
            // so this catch covers both the read-timeout (Istio's 15s
            // fault) and connect-timeout cases.
            // This is the exception @Retryable catches. When Istio's
            // 15s fault fires, we end up here; Spring re-runs
            // PaymentExecutor.execute() and the ledger.debit above
            // runs a second time with a fresh txn_id.
            throw new UpstreamTimeoutException(
                "inventory reserve timeout (15s) order_id=" + orderId, e);
        } catch (java.io.IOException | InterruptedException e) {
            throw new UpstreamTimeoutException(
                "inventory reserve IO error order_id=" + orderId, e);
        }
    }
}

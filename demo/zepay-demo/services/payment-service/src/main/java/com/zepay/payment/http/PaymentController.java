package com.zepay.payment.http;

import com.zepay.payment.ledger.PaymentExecutor;
import com.zepay.payment.ledger.UpstreamTimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/payment")
public class PaymentController {

    private static final Logger log = LoggerFactory.getLogger(PaymentController.class);
    private final PaymentExecutor executor;

    public PaymentController(PaymentExecutor executor) {
        this.executor = executor;
    }

    @PostMapping("/execute")
    public ResponseEntity<PaymentResult> execute(@RequestBody PaymentRequest req) {
        try {
            return ResponseEntity.ok(executor.execute(req));
        } catch (UpstreamTimeoutException e) {
            // Retries exhausted — bubble up as 504. In the demo this
            // rarely happens (fault is 20% so retry almost always wins).
            log.warn("payment execute gave up: {}", e.getMessage());
            return ResponseEntity.status(504).build();
        }
    }
}

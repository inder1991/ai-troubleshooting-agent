package com.zepay.payment;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.retry.annotation.EnableRetry;

/**
 * Spring Boot entry for payment-service.
 *
 * {@code @EnableRetry} is what activates Spring Retry's AOP proxying
 * for {@code @Retryable} — without it the annotation on
 * PaymentExecutor.execute() would be a no-op. Keeping the annotation
 * here on the entry class mirrors the real-world Zepay codebase
 * (storyboard §2) where the retry wiring is enabled application-wide.
 */
@SpringBootApplication
@EnableRetry
public class PaymentServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(PaymentServiceApplication.class, args);
    }
}

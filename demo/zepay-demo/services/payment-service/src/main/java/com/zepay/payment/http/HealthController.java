package com.zepay.payment.http;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Kubernetes-probe endpoints mirroring the Go services' /livez + /readyz.
 * Keeps the zepay-service Helm chart uniform — every service, Java or
 * Go, answers the same two paths for probes.
 */
@RestController
public class HealthController {
    @GetMapping("/livez")  public String livez() { return "ok"; }
    @GetMapping("/readyz") public String readyz() { return "ok"; }
}

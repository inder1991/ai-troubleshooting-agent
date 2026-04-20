// checkout-service — orchestrates a customer checkout.
//
// Storyboard role:
//   This is the INNOCENT VICTIM. User-perceived spinner lives here;
//   PagerDuty points here; on-call investigates here first. The
//   service's own code is correct — it delegates money-movement to
//   payment-service and waits. When payment-service's retry wrapper
//   fires, checkout sits behind it for 15+ seconds, which is why
//   checkout_payment_latency_seconds p95 spikes to 15.2s.
//
// Endpoints:
//   POST /pay   {customer_id, cart_id, amount_cents, currency}
//     → 200 {txn_id, status: "SUCCESS"}
//     → 5xx propagated from payment-service
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/zepay/go-common/zepay"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const serviceName = "checkout-service"
const defaultPort = "8083"
const defaultPaymentURL = "http://payment-service:8084"

// This is the p95 metric §1.2 cites ("checkout_payment_latency_seconds
// p95: 1.8s baseline → 15.2s during incident").
var checkoutPaymentLatency = promauto.NewHistogram(prometheus.HistogramOpts{
	Name:    "checkout_payment_latency_seconds",
	Help:    "End-to-end latency of the checkout→payment round-trip.",
	Buckets: []float64{0.1, 0.5, 1, 2, 5, 10, 15, 20, 30},
})

type server struct {
	paymentURL string
	client     *http.Client
}

type payReq struct {
	CustomerID  string `json:"customer_id"`
	CartID      string `json:"cart_id"`
	AmountCents int64  `json:"amount_cents"`
	Currency    string `json:"currency"`
}

func (s *server) pay(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	start := time.Now()
	defer func() {
		checkoutPaymentLatency.Observe(time.Since(start).Seconds())
	}()

	var req payReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad json: "+err.Error(), http.StatusBadRequest)
		return
	}

	body, _ := json.Marshal(req)
	upstream, err := http.NewRequestWithContext(ctx, http.MethodPost,
		s.paymentURL+"/v1/payment/execute", bytes.NewReader(body))
	if err != nil {
		http.Error(w, "build request: "+err.Error(), http.StatusInternalServerError)
		return
	}
	upstream.Header.Set("Content-Type", "application/json")
	if k := r.Header.Get("Idempotency-Key"); k != "" {
		upstream.Header.Set("Idempotency-Key", k)
	}

	resp, err := s.client.Do(upstream)
	if err != nil {
		slog.ErrorContext(ctx, "payment upstream failed", "err", err.Error())
		http.Error(w, "upstream: "+err.Error(), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	elapsed := time.Since(start)
	slog.InfoContext(ctx, "checkout pay complete",
		"customer_id", req.CustomerID, "cart_id", req.CartID,
		"elapsed_ms", elapsed.Milliseconds(),
		"upstream_status", resp.StatusCode)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

func envOr(k, dflt string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return dflt
}

func main() {
	zepay.Init(serviceName)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	shutdownTracing := zepay.InitTracing(ctx, serviceName)
	defer func() { _ = shutdownTracing(context.Background()) }()

	s := &server{
		paymentURL: envOr("PAYMENT_URL", defaultPaymentURL),
		client: &http.Client{
			// Longer than payment-service's internal timeout so we wait
			// for its retry to either succeed or fail cleanly.
			Transport: otelhttp.NewTransport(http.DefaultTransport),
			Timeout:   45 * time.Second,
		},
	}

	mux := http.NewServeMux()
	mux.HandleFunc("POST /pay", s.pay)

	port := envOr("PORT", defaultPort)
	shutdown := zepay.Serve(serviceName, port, mux, nil)

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	slog.Info("shutdown requested")
	shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancelShutdown()
	_ = shutdown(shutdownCtx)
}

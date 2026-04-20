// fraud-adapter — stubbed 3rd-party fraud-scoring client.
//
// Storyboard role:
//   CONVINCING FALSE LEAD. Per §1.3, during the incident fraud-adapter's
//   p95 rises from 140ms → 380ms (2.7× baseline). Topology lights it
//   up red. A human on-call investigates this first; the workflow's
//   critic correctly eliminates it because its latency contribution is
//   only ~1.6% of incident latency (real bottleneck: 15s at inventory).
//
//   The elevated-latency mode is toggleable so the signal is REAL
//   (actually slower; traces show it) but bounded.
//
// Env vars:
//   FRAUD_MODE = normal | elevated       (default normal)
//     normal   → sleep 120-160ms (baseline)
//     elevated → sleep 340-420ms (2.7× baseline — decoy)
//
// Endpoints:
//   POST  /v1/score  {customer_id, amount_cents}
//     → 200 {risk_score, decision, mode}
//   PATCH /v1/mode   {mode:"normal"|"elevated"}
//     (demo-controller flips this without a pod restart)
package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/zepay/go-common/zepay"
)

const serviceName = "fraud-adapter"
const defaultPort = "8085"

// Atomic bool → demo-controller can flip mode at runtime.
var elevated atomic.Bool

var fraudScoreLatency = promauto.NewHistogramVec(prometheus.HistogramOpts{
	Name:    "fraud_score_duration_seconds",
	Help:    "Duration of fraud-score requests.",
	Buckets: []float64{0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 1.0},
}, []string{"mode"})

type scoreReq struct {
	CustomerID  string `json:"customer_id"`
	AmountCents int64  `json:"amount_cents"`
}

func simulateLatency(ctx context.Context) (mode string, waited time.Duration) {
	if elevated.Load() {
		mode = "elevated"
		waited = time.Duration(340+rand.Intn(80)) * time.Millisecond
	} else {
		mode = "normal"
		waited = time.Duration(120+rand.Intn(40)) * time.Millisecond
	}
	select {
	case <-time.After(waited):
	case <-ctx.Done():
	}
	return
}

func score(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req scoreReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad json: "+err.Error(), http.StatusBadRequest)
		return
	}

	mode, waited := simulateLatency(ctx)
	fraudScoreLatency.WithLabelValues(mode).Observe(waited.Seconds())

	if mode == "elevated" {
		// WARN cluster log_agent picks up as the H1 decoy cluster.
		slog.WarnContext(ctx, "FraudScoreProviderSlowdown",
			"customer_id", req.CustomerID,
			"amount_cents", req.AmountCents,
			"waited_ms", waited.Milliseconds())
	}

	// Deterministic score — reproducible runs.
	risk := 10 + int(req.AmountCents/1000)%80
	decision := "approve"
	if risk > 80 {
		decision = "review"
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"risk_score": risk,
		"decision":   decision,
		"mode":       mode,
	})
}

func setMode(w http.ResponseWriter, r *http.Request) {
	var body struct{ Mode string `json:"mode"` }
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "bad json: "+err.Error(), http.StatusBadRequest)
		return
	}
	switch body.Mode {
	case "normal":
		elevated.Store(false)
	case "elevated":
		elevated.Store(true)
	default:
		http.Error(w, `mode must be "normal" or "elevated"`, http.StatusBadRequest)
		return
	}
	slog.Info("fraud-adapter mode set", "mode", body.Mode)
	_ = json.NewEncoder(w).Encode(map[string]string{"mode": body.Mode})
}

func main() {
	zepay.Init(serviceName)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	shutdownTracing := zepay.InitTracing(ctx, serviceName)
	defer func() { _ = shutdownTracing(context.Background()) }()

	if os.Getenv("FRAUD_MODE") == "elevated" {
		elevated.Store(true)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/score", score)
	mux.HandleFunc("PATCH /v1/mode", setMode)

	port := defaultPort
	if v := os.Getenv("PORT"); v != "" {
		port = v
	}
	shutdown := zepay.Serve(serviceName, port, mux, nil)

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	slog.Info("shutdown requested")
	shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancelShutdown()
	_ = shutdown(shutdownCtx)
}

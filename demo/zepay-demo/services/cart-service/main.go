// cart-service — STUB (PR-K3). Real business logic lands in PR-K3.5.
//
// Boots with the shared zepay scaffolding: structured JSON logs,
// OTel trace propagation, /metrics + /livez + /readyz. Primary
// route returns a placeholder 200 so other services can address
// this one without connection errors.
package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/zepay/go-common/zepay"
)

const serviceName = "cart-service"
const defaultPort = "8082"

func ok(w http.ResponseWriter, r *http.Request) {
	slog.InfoContext(r.Context(), "stub request",
		"route", r.URL.Path, "method", r.Method)
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"service": serviceName,
		"status":  "stub",
		"note":    "PR-K3 scaffolding; real business logic lands in PR-K3.5",
	})
}

func main() {
	zepay.Init(serviceName)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	shutdownTracing := zepay.InitTracing(ctx, serviceName)
	defer func() { _ = shutdownTracing(context.Background()) }()

	mux := http.NewServeMux()
	mux.HandleFunc("/", ok)

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

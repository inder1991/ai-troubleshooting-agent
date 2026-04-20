package zepay

// HTTP server scaffolding:
//   - Wraps the user's mux with OTel middleware so every inbound
//     request becomes a span.
//   - Mounts /metrics (Prometheus) + /livez + /readyz unconditionally.
//   - Starts the server in a goroutine; returns a shutdown func that
//     waits for in-flight requests to drain (SIGTERM handling).
//
// Not a "framework" — just the three boilerplate steps every demo
// service needs to behave uniformly in the cluster.

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

// Serve starts an HTTP server on :port with the user's handlers,
// plus /metrics + /livez + /readyz. Returns a shutdown function.
//
// ready is an optional readiness probe — called on /readyz; nil means
// "always ready." Use it to gate readiness on DB/Redis/downstream health.
func Serve(service string, port string, userMux http.Handler, ready func() error) func(context.Context) error {
	mux := http.NewServeMux()
	// User routes under / — wrapped in OTel middleware so each inbound
	// request gets a span and trace-context is extracted from headers.
	mux.Handle("/", otelhttp.NewHandler(userMux, service))

	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/livez", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if ready != nil {
			if err := ready(); err != nil {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte("not-ready: " + err.Error()))
				return
			}
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		slog.Info("http server starting", "port", port)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("http server failed", "err", err.Error())
		}
	}()

	return srv.Shutdown
}

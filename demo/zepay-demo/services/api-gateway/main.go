// api-gateway — entry service for all external traffic.
//
// Responsibility in the storyboard (§3):
//   - Terminates k6 traffic at the Istio Gateway.
//   - Forwards /api/v1/checkout → checkout-service.
//   - Forwards /api/v1/health   → each upstream for liveness fan-out.
//   - First span of every trace; propagates W3C trace-context.
//
// Nothing else. The gateway is deliberately dumb.
package main

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/zepay/go-common/zepay"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const (
	serviceName        = "api-gateway"
	defaultPort        = "8080"
	defaultCheckoutURL = "http://checkout-service:8083"
)

type gateway struct {
	checkoutURL string
	client      *http.Client
}

func (g *gateway) proxyCheckout(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "read body: "+err.Error(), http.StatusBadRequest)
		return
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, g.checkoutURL+"/pay", nil)
	if err != nil {
		http.Error(w, "build request: "+err.Error(), http.StatusInternalServerError)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	if k := r.Header.Get("Idempotency-Key"); k != "" {
		req.Header.Set("Idempotency-Key", k)
	}
	if a := r.Header.Get("Authorization"); a != "" {
		req.Header.Set("Authorization", a)
	}
	req.Body = io.NopCloser(bytesReader(body))

	resp, err := g.client.Do(req)
	if err != nil {
		slog.ErrorContext(ctx, "upstream checkout failed", "err", err.Error())
		http.Error(w, "upstream: "+err.Error(), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

func (g *gateway) ok(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"service": serviceName, "status": "ok"})
}

// bytesReader is a tiny io.Reader over a []byte so we don't pull in
// bytes.NewReader for one use.
func bytesReader(b []byte) *byteReader { return &byteReader{b: b} }

type byteReader struct {
	b []byte
	i int
}

func (r *byteReader) Read(p []byte) (int, error) {
	if r.i >= len(r.b) {
		return 0, io.EOF
	}
	n := copy(p, r.b[r.i:])
	r.i += n
	return n, nil
}

func main() {
	zepay.Init(serviceName)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	shutdownTracing := zepay.InitTracing(ctx, serviceName)
	defer func() { _ = shutdownTracing(context.Background()) }()

	g := &gateway{
		checkoutURL: envOr("CHECKOUT_URL", defaultCheckoutURL),
		client: &http.Client{
			// 30s covers the 15s Istio fault + retry + return path.
			Transport: otelhttp.NewTransport(http.DefaultTransport),
			Timeout:   30 * time.Second,
		},
	}

	mux := http.NewServeMux()
	mux.HandleFunc("POST /api/v1/checkout", g.proxyCheckout)
	mux.HandleFunc("GET /api/v1/health", g.ok)

	port := envOr("PORT", defaultPort)
	shutdown := zepay.Serve(serviceName, port, mux, nil)

	// Wait for SIGTERM / Ctrl-C.
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig

	slog.Info("shutdown requested")
	shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancelShutdown()
	_ = shutdown(shutdownCtx)
}

func envOr(k, dflt string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return dflt
}

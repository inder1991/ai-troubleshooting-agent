// inventory-service — reserves items for a checkout order.
//
// Storyboard role:
//   This service is the TARGET of the Istio fault-injection
//   VirtualService in demo/zepay-demo/istio/inventory-timeout-fault.yaml.
//   When fault is ON, 20% of incoming /v1/reserve requests are delayed
//   15s by Istio's sidecar BEFORE they reach this service's handler.
//   The caller (payment-service) sees a 504, throws
//   UpstreamTimeoutException, and @Retryable fires — reproducing the bug.
//
// Why this service has NO bug:
//   When requests actually reach us, we handle them correctly:
//   atomic INSERT into inventory.items with reserved_at. The timeout
//   is purely at the infrastructure layer; our handler is fast.
//
// Endpoints:
//   POST /v1/reserve  {order_id, items: [{sku, qty}, ...]}
//     → 200 {reserved_at}
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

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/zepay/go-common/zepay"
)

const serviceName = "inventory-service"
const defaultPort = "8086"

var inventoryReserves = promauto.NewCounterVec(prometheus.CounterOpts{
	Name: "inventory_reserves_total",
	Help: "Count of inventory reservations; dimensioned by outcome.",
}, []string{"outcome"})

type server struct{ pg *pgxpool.Pool }

type reserveReq struct {
	OrderID string            `json:"order_id"`
	Items   []json.RawMessage `json:"items"`
}

func (s *server) reserve(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req reserveReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad json: "+err.Error(), http.StatusBadRequest)
		return
	}

	itemsJSON, err := json.Marshal(req.Items)
	if err != nil {
		http.Error(w, "items encode: "+err.Error(), http.StatusBadRequest)
		return
	}

	now := time.Now().UTC()
	if _, err := s.pg.Exec(ctx, `
		INSERT INTO inventory.items (order_id, items, reserved_at)
		VALUES ($1, $2, $3)
		ON CONFLICT (order_id) DO UPDATE
		  SET items       = EXCLUDED.items,
		      reserved_at = EXCLUDED.reserved_at
	`, req.OrderID, itemsJSON, now); err != nil {
		inventoryReserves.WithLabelValues("error").Inc()
		slog.ErrorContext(ctx, "inventory reserve pg error",
			"err", err.Error(), "order_id", req.OrderID)
		http.Error(w, "pg: "+err.Error(), http.StatusInternalServerError)
		return
	}

	inventoryReserves.WithLabelValues("ok").Inc()
	slog.InfoContext(ctx, "inventory reserve ok",
		"order_id", req.OrderID, "item_count", len(req.Items))

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"order_id":    req.OrderID,
		"reserved_at": now.Format(time.RFC3339Nano),
	})
}

func main() {
	zepay.Init(serviceName)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	shutdownTracing := zepay.InitTracing(ctx, serviceName)
	defer func() { _ = shutdownTracing(context.Background()) }()

	pg := zepay.NewPool(ctx)
	defer pg.Close()
	s := &server{pg: pg}

	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/reserve", s.reserve)

	port := defaultPort
	if v := os.Getenv("PORT"); v != "" {
		port = v
	}
	ready := func() error { return pg.Ping(ctx) }
	shutdown := zepay.Serve(serviceName, port, mux, ready)

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	slog.Info("shutdown requested")
	shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancelShutdown()
	_ = shutdown(shutdownCtx)
}

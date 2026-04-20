// notification-service — Postgres outbox writer.
//
// Storyboard role:
//   Healthy background. A trailing span after payment success. When
//   payment-service's retry fires, notification-service correctly
//   only emits ONE notification (the second retry-attempt returns
//   the same cached response at the API boundary, so from
//   notification's perspective there was one txn). This is PART of
//   why the user sees "Payment successful" once despite being
//   double-charged.
//
// Endpoints:
//   POST /v1/notify   {customer_id, kind, payload}  → 200 {msg_id}
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
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

const serviceName = "notification-service"
const defaultPort = "8088"

var notifSent = promauto.NewCounterVec(prometheus.CounterOpts{
	Name: "notifications_sent_total",
	Help: "Count of notifications enqueued to the outbox.",
}, []string{"kind"})

type server struct{ pg *pgxpool.Pool }

type notifyReq struct {
	CustomerID string          `json:"customer_id"`
	Kind       string          `json:"kind"`
	Payload    json.RawMessage `json:"payload"`
}

func newMsgID() string {
	var b [8]byte
	_, _ = rand.Read(b[:])
	return "msg-" + hex.EncodeToString(b[:])
}

func (s *server) notify(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req notifyReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad json: "+err.Error(), http.StatusBadRequest)
		return
	}
	id := newMsgID()
	if _, err := s.pg.Exec(ctx, `
		INSERT INTO notif.outbox (msg_id, customer_id, kind, payload, sent_at)
		VALUES ($1, $2, $3, $4, now())
	`, id, req.CustomerID, req.Kind, req.Payload); err != nil {
		http.Error(w, "pg: "+err.Error(), http.StatusInternalServerError)
		return
	}
	notifSent.WithLabelValues(req.Kind).Inc()
	slog.InfoContext(ctx, "notification enqueued",
		"msg_id", id, "customer_id", req.CustomerID, "kind", req.Kind)
	_ = json.NewEncoder(w).Encode(map[string]string{"msg_id": id})
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
	mux.HandleFunc("POST /v1/notify", s.notify)

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

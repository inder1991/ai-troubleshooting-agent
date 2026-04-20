// cart-service — Redis-backed cart state.
//
// Storyboard role:
//   Healthy background. Its only job is to confirm the cart exists
//   before checkout. It reads & writes a per-customer cart key in
//   Redis. No bugs here. The storyboard cites this service as "healthy"
//   in the blast-radius list.
//
// Endpoints:
//   GET  /v1/cart/{customer_id}              → current cart JSON
//   POST /v1/cart/{customer_id}              → overwrite cart
//   POST /v1/cart/{customer_id}/checkout     → validate + freeze
package main

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/zepay/go-common/zepay"
)

const serviceName = "cart-service"
const defaultPort = "8082"

type server struct{ rdb *redis.Client }

func cartKey(cid string) string { return "cart:" + cid }

func (s *server) get(w http.ResponseWriter, r *http.Request) {
	cid := strings.TrimPrefix(r.URL.Path, "/v1/cart/")
	cid = strings.Split(cid, "/")[0]
	if cid == "" {
		http.Error(w, "missing customer_id", http.StatusBadRequest)
		return
	}
	val, err := s.rdb.Get(r.Context(), cartKey(cid)).Result()
	if errors.Is(err, redis.Nil) {
		_ = json.NewEncoder(w).Encode(map[string]any{"customer_id": cid, "items": []any{}})
		return
	}
	if err != nil {
		http.Error(w, "redis: "+err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(val))
}

func (s *server) set(w http.ResponseWriter, r *http.Request) {
	cid := strings.TrimPrefix(r.URL.Path, "/v1/cart/")
	cid = strings.Split(cid, "/")[0]
	if cid == "" {
		http.Error(w, "missing customer_id", http.StatusBadRequest)
		return
	}
	body, err := readAll(r)
	if err != nil {
		http.Error(w, "read body: "+err.Error(), http.StatusBadRequest)
		return
	}
	// 30-minute TTL — realistic cart lifetime.
	if err := s.rdb.Set(r.Context(), cartKey(cid), body, 30*time.Minute).Err(); err != nil {
		http.Error(w, "redis: "+err.Error(), http.StatusInternalServerError)
		return
	}
	slog.InfoContext(r.Context(), "cart set", "customer_id", cid, "bytes", len(body))
	w.WriteHeader(http.StatusNoContent)
}

func (s *server) checkout(w http.ResponseWriter, r *http.Request) {
	// Strip the `/checkout` suffix.
	path := strings.TrimPrefix(r.URL.Path, "/v1/cart/")
	cid := strings.TrimSuffix(path, "/checkout")
	if cid == "" || cid == path {
		http.Error(w, "bad path", http.StatusBadRequest)
		return
	}
	val, err := s.rdb.Get(r.Context(), cartKey(cid)).Result()
	if errors.Is(err, redis.Nil) {
		http.Error(w, `{"error":"EMPTY_CART"}`, http.StatusConflict)
		return
	}
	if err != nil {
		http.Error(w, "redis: "+err.Error(), http.StatusInternalServerError)
		return
	}
	slog.InfoContext(r.Context(), "cart checkout", "customer_id", cid)
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(val))
}

func readAll(r *http.Request) ([]byte, error) {
	var buf [1 << 15]byte
	n, err := r.Body.Read(buf[:])
	if err != nil && err.Error() != "EOF" {
		return nil, err
	}
	return buf[:n], nil
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

	rdb := redis.NewClient(&redis.Options{
		Addr:            envOr("REDIS_ADDR", "redis:6379"),
		ReadTimeout:     3 * time.Second,
		WriteTimeout:    3 * time.Second,
	})
	defer rdb.Close()

	s := &server{rdb: rdb}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/cart/", s.get)
	mux.HandleFunc("POST /v1/cart/", func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/checkout") {
			s.checkout(w, r)
			return
		}
		s.set(w, r)
	})

	port := envOr("PORT", defaultPort)
	ready := func() error { return rdb.Ping(ctx).Err() }
	shutdown := zepay.Serve(serviceName, port, mux, ready)

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	slog.Info("shutdown requested")
	shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancelShutdown()
	_ = shutdown(shutdownCtx)
}

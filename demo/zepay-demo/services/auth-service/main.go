// auth-service — opaque bearer-token mint/verify for the demo.
//
// Storyboard role:
//   Healthy background noise. Adds a realistic 4-8ms span to every
//   trace (§3 says this is the auth span a CXO expects to see).
//   Validates Authorization: Bearer <token> against auth.tokens;
//   mints new tokens on POST /v1/auth/login.
//
//   Not using real JWT/JWS — just a random token persisted in
//   Postgres. Keeps the dependency footprint small; the demo doesn't
//   need real crypto for its auth surface.
//
// Endpoints:
//   POST /v1/auth/login   {customer_id}      → 200 {token, expires_at}
//   GET  /v1/auth/verify  (header Authorization: Bearer X)
//                                            → 200 {customer_id}  |  401
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/zepay/go-common/zepay"
)

const serviceName = "auth-service"
const defaultPort = "8081"
const tokenTTL = 8 * time.Hour

type server struct{ pg *pgxpool.Pool }

type loginReq struct {
	CustomerID string `json:"customer_id"`
}

func newToken() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}

func (s *server) login(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req loginReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad json: "+err.Error(), http.StatusBadRequest)
		return
	}
	if req.CustomerID == "" {
		http.Error(w, "customer_id required", http.StatusBadRequest)
		return
	}
	tok := newToken()
	exp := time.Now().UTC().Add(tokenTTL)

	if _, err := s.pg.Exec(ctx, `
		INSERT INTO auth.tokens (token_id, customer_id, expires_at)
		VALUES ($1, $2, $3)
	`, tok, req.CustomerID, exp); err != nil {
		http.Error(w, "pg: "+err.Error(), http.StatusInternalServerError)
		return
	}

	slog.InfoContext(ctx, "auth login", "customer_id", req.CustomerID)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"token":      tok,
		"expires_at": exp.Format(time.RFC3339),
	})
}

func (s *server) verify(w http.ResponseWriter, r *http.Request) {
	authz := r.Header.Get("Authorization")
	tok := strings.TrimPrefix(authz, "Bearer ")
	if tok == "" || tok == authz {
		http.Error(w, `{"error":"missing token"}`, http.StatusUnauthorized)
		return
	}
	var cid string
	var exp time.Time
	err := s.pg.QueryRow(r.Context(),
		`SELECT customer_id, expires_at FROM auth.tokens WHERE token_id=$1`, tok,
	).Scan(&cid, &exp)
	if errors.Is(err, pgx.ErrNoRows) {
		http.Error(w, `{"error":"invalid token"}`, http.StatusUnauthorized)
		return
	}
	if err != nil {
		http.Error(w, "pg: "+err.Error(), http.StatusInternalServerError)
		return
	}
	if time.Now().UTC().After(exp) {
		http.Error(w, `{"error":"expired"}`, http.StatusUnauthorized)
		return
	}
	_ = json.NewEncoder(w).Encode(map[string]any{"customer_id": cid})
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
	mux.HandleFunc("POST /v1/auth/login", s.login)
	mux.HandleFunc("GET /v1/auth/verify", s.verify)

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

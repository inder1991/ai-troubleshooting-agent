// wallet-service — holds per-customer balance + ledger txn log.
//
// Storyboard role:
//   This is the service the double-debit lands ON. payment-service
//   calls POST /v1/debit once; when @Retryable re-issues after the
//   15s Istio timeout, payment-service calls POST /v1/debit AGAIN
//   with the SAME inputs but a DIFFERENT txn_id — because the buggy
//   retry wrapper doesn't include an idempotency key.
//
//   Two "wallets.UPDATE" spans land in Jaeger. ledger.txns grows by
//   two rows per customer complaint. That is the evidence
//   tracing_agent and the Postgres-level proof both rely on.
//
// Why wallet-service itself has NO bug:
//   It correctly implements the debit: atomic UPDATE with a
//   balance-check. It is NOT responsible for deduplicating txn_ids
//   on behalf of its callers — the caller (payment-service) owns
//   idempotency. wallet-service faithfully records both debits
//   because both debits were legitimately requested.
//
// Endpoints:
//   POST /v1/debit     {customer_id, amount_cents, currency, txn_id}
//     → 200 {txn_id, new_balance_cents}   on success
//     → 402 {error:"INSUFFICIENT_FUNDS"}
//   POST /v1/topup     {customer_id, amount_cents, currency}
//     (demo-controller uses this to seed the concurrent top-up that
//     lets the retry's second debit pass the balance-check)
//   GET  /v1/balance/{customer_id}
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

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/zepay/go-common/zepay"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

const serviceName = "wallet-service"
const defaultPort = "8087"

// Counter tracing_agent + metrics_agent correlate against customer-
// complaint txn_ids. Dimensioned on direction so metrics_agent can
// separate debits from credits.
var walletBalanceChanges = promauto.NewCounterVec(prometheus.CounterOpts{
	Name: "wallet_balance_changes_total",
	Help: "Count of wallet balance changes; dimensioned by direction.",
}, []string{"direction"})

type server struct {
	pg     *pgxpool.Pool
	tracer trace.Tracer
}

type debitReq struct {
	CustomerID  string `json:"customer_id"`
	AmountCents int64  `json:"amount_cents"`
	Currency    string `json:"currency"`
	TxnID       string `json:"txn_id"`
}

type topupReq struct {
	CustomerID  string `json:"customer_id"`
	AmountCents int64  `json:"amount_cents"`
	Currency    string `json:"currency"`
}

func (s *server) debit(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req debitReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad json: "+err.Error(), http.StatusBadRequest)
		return
	}

	// Explicit "wallets.UPDATE" span so it lands in Jaeger under the
	// exact name tracing_agent looks for. Two of these with the same
	// customer_id but different txn_ids within one trace is the
	// smoking gun.
	ctx, span := s.tracer.Start(ctx, "wallets.UPDATE",
		trace.WithAttributes(
			attribute.String("zepay.customer_id", req.CustomerID),
			attribute.String("zepay.txn_id", req.TxnID),
			attribute.Int64("zepay.amount_cents", req.AmountCents),
		),
	)
	defer span.End()

	tx, err := s.pg.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		http.Error(w, "tx begin: "+err.Error(), http.StatusInternalServerError)
		return
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// Atomic balance check + debit. This is the storyboard's
	// "WHERE balance >= :amount" guard. Correct here; bug is in
	// payment-service, which retries the whole wrapper.
	var newBalance int64
	err = tx.QueryRow(ctx, `
		UPDATE wallet.balances
		   SET balance_cents = balance_cents - $2,
		       updated_at    = now()
		 WHERE customer_id = $1
		   AND balance_cents >= $2
		RETURNING balance_cents
	`, req.CustomerID, req.AmountCents).Scan(&newBalance)

	if errors.Is(err, pgx.ErrNoRows) {
		http.Error(w, `{"error":"INSUFFICIENT_FUNDS"}`, http.StatusPaymentRequired)
		return
	}
	if err != nil {
		slog.ErrorContext(ctx, "wallet debit pg error", "err", err.Error(),
			"customer_id", req.CustomerID, "txn_id", req.TxnID)
		http.Error(w, "pg: "+err.Error(), http.StatusInternalServerError)
		return
	}

	if _, err = tx.Exec(ctx, `
		INSERT INTO ledger.txns (txn_id, customer_id, amount_cents, currency, direction)
		VALUES ($1, $2, $3, $4, 'debit')
	`, req.TxnID, req.CustomerID, req.AmountCents, req.Currency); err != nil {
		// No UNIQUE constraint on idempotency_key in PR-K2's schema
		// (intentional). Retry lands here with a fresh txn_id and
		// inserts a second row. Bug reproduces.
		slog.ErrorContext(ctx, "ledger insert pg error", "err", err.Error())
		http.Error(w, "pg: "+err.Error(), http.StatusInternalServerError)
		return
	}

	if err := tx.Commit(ctx); err != nil {
		http.Error(w, "tx commit: "+err.Error(), http.StatusInternalServerError)
		return
	}

	walletBalanceChanges.WithLabelValues("debit").Inc()
	slog.InfoContext(ctx, "wallet debit ok",
		"customer_id", req.CustomerID, "txn_id", req.TxnID,
		"amount_cents", req.AmountCents, "new_balance_cents", newBalance)

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"txn_id":            req.TxnID,
		"new_balance_cents": newBalance,
	})
}

func (s *server) topup(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req topupReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad json: "+err.Error(), http.StatusBadRequest)
		return
	}
	if _, err := s.pg.Exec(ctx, `
		INSERT INTO wallet.balances (customer_id, balance_cents, currency)
		VALUES ($1, $2, $3)
		ON CONFLICT (customer_id) DO UPDATE
		  SET balance_cents = wallet.balances.balance_cents + $2,
		      updated_at    = now()
	`, req.CustomerID, req.AmountCents, req.Currency); err != nil {
		http.Error(w, "pg: "+err.Error(), http.StatusInternalServerError)
		return
	}
	walletBalanceChanges.WithLabelValues("credit").Inc()
	slog.InfoContext(ctx, "wallet topup ok",
		"customer_id", req.CustomerID, "amount_cents", req.AmountCents)
	w.WriteHeader(http.StatusOK)
}

func (s *server) balance(w http.ResponseWriter, r *http.Request) {
	cid := strings.TrimPrefix(r.URL.Path, "/v1/balance/")
	if cid == "" {
		http.Error(w, "missing customer_id", http.StatusBadRequest)
		return
	}
	var amt int64
	var cur string
	err := s.pg.QueryRow(r.Context(),
		`SELECT balance_cents, currency FROM wallet.balances WHERE customer_id=$1`, cid,
	).Scan(&amt, &cur)
	if errors.Is(err, pgx.ErrNoRows) {
		_ = json.NewEncoder(w).Encode(map[string]any{"customer_id": cid, "balance_cents": 0, "currency": "USD"})
		return
	}
	if err != nil {
		http.Error(w, "pg: "+err.Error(), http.StatusInternalServerError)
		return
	}
	_ = json.NewEncoder(w).Encode(map[string]any{"customer_id": cid, "balance_cents": amt, "currency": cur})
}

func main() {
	zepay.Init(serviceName)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	shutdownTracing := zepay.InitTracing(ctx, serviceName)
	defer func() { _ = shutdownTracing(context.Background()) }()

	pg := zepay.NewPool(ctx)
	defer pg.Close()

	s := &server{pg: pg, tracer: otel.Tracer(serviceName)}

	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/debit", s.debit)
	mux.HandleFunc("POST /v1/topup", s.topup)
	mux.HandleFunc("GET /v1/balance/", s.balance)

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

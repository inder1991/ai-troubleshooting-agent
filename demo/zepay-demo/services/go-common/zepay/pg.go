package zepay

// Postgres pool helper. Thin wrapper around pgxpool so each service
// can say one line in main() and get a connection pool back.
//
// Env vars consumed:
//   PG_HOST     default: postgres
//   PG_PORT     default: 5432
//   PG_USER     default: zepay
//   PG_PASSWORD default: zepay-demo-password   (MUST be overridden in real deploys)
//   PG_DB       default: zepay
//   PG_SCHEMA   REQUIRED — per-service schema (wallet, ledger, etc.)

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func envOr(key, dflt string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return dflt
}

// NewPool opens a pgx pool scoped to the caller's schema via search_path.
// Panics on connection failure — services that need graceful fallback
// should skip this helper and build their own.
func NewPool(ctx context.Context) *pgxpool.Pool {
	schema := os.Getenv("PG_SCHEMA")
	if schema == "" {
		panic("PG_SCHEMA env var is required")
	}
	dsn := fmt.Sprintf(
		"postgres://%s:%s@%s:%s/%s?sslmode=disable&search_path=%s",
		envOr("PG_USER", "zepay"),
		envOr("PG_PASSWORD", "zepay-demo-password"),
		envOr("PG_HOST", "postgres"),
		envOr("PG_PORT", "5432"),
		envOr("PG_DB", "zepay"),
		schema,
	)
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		panic(fmt.Sprintf("pg: parse DSN: %v", err))
	}
	cfg.MaxConns = 10
	cfg.MaxConnLifetime = 30 * time.Minute

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		panic(fmt.Sprintf("pg: connect: %v", err))
	}
	return pool
}

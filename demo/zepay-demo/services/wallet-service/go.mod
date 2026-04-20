module github.com/zepay/wallet-service

go 1.22

require (
	github.com/jackc/pgx/v5 v5.6.0
	github.com/prometheus/client_golang v1.19.1
	github.com/zepay/go-common v0.0.0
	go.opentelemetry.io/otel v1.28.0
	go.opentelemetry.io/otel/trace v1.28.0
)

replace github.com/zepay/go-common => ../go-common

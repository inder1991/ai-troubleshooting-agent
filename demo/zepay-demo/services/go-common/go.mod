module github.com/zepay/go-common

go 1.22

require (
	github.com/jackc/pgx/v5 v5.6.0
	github.com/redis/go-redis/v9 v9.6.1
	github.com/prometheus/client_golang v1.19.1
	go.opentelemetry.io/otel v1.28.0
	go.opentelemetry.io/otel/exporters/otlp/otlptrace v1.28.0
	go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc v1.28.0
	go.opentelemetry.io/otel/propagation v1.28.0
	go.opentelemetry.io/otel/sdk v1.28.0
	go.opentelemetry.io/otel/trace v1.28.0
	go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp v0.53.0
	golang.org/x/exp v0.0.0-20240613232115-7f521ea00fb8
)

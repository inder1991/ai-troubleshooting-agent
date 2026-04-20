module github.com/zepay/api-gateway

go 1.22

require (
	github.com/zepay/go-common v0.0.0
	go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp v0.53.0
	go.opentelemetry.io/otel v1.28.0
	go.opentelemetry.io/otel/trace v1.28.0
)

replace github.com/zepay/go-common => ../go-common

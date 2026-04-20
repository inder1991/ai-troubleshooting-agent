module github.com/zepay/checkout-service

go 1.22

require (
	github.com/prometheus/client_golang v1.19.1
	go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp v0.53.0
	github.com/zepay/go-common v0.0.0
)

replace github.com/zepay/go-common => ../go-common

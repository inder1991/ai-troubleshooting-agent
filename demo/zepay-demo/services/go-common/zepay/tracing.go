package zepay

// OpenTelemetry bootstrap — every service opens a gRPC OTLP exporter
// pointed at the Istio-installed OpenTelemetry Collector (or direct
// to Jaeger's OTLP endpoint — the default address below matches the
// standard Jaeger-Operator deployment in the `observability` namespace).
//
// Why this matters for the storyboard:
//   tracing_agent reads Jaeger and walks span waterfalls. If any of
//   the 8 Go services skip OTel propagation, traces fragment and the
//   "double wallets.UPDATE in one trace" evidence disappears.
//   Everything here is deliberately uniform — if you edit it, edit it
//   in all 8 services at once or traces break unevenly.

import (
	"context"
	"log/slog"
	"os"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/resource"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

// InitTracing wires up an OTLP/gRPC tracer provider and sets the
// global propagator to W3C tracecontext + baggage. Returns a shutdown
// func — defer it from main() so buffered spans flush on SIGTERM.
func InitTracing(ctx context.Context, service string) func(context.Context) error {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = "jaeger-collector.observability.svc.cluster.local:4317"
	}

	exp, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint(endpoint),
		otlptracegrpc.WithInsecure(),
		otlptracegrpc.WithTimeout(3*time.Second),
	)
	if err != nil {
		// Non-fatal. Services MUST stay up even if the tracing backend
		// is down — the demo's k8s_agent assertion is "pods healthy";
		// crashing on a collector hiccup would invalidate that.
		slog.Warn("otlp exporter init failed; continuing without traces", "err", err.Error())
		return func(context.Context) error { return nil }
	}

	res, _ := resource.Merge(resource.Default(), resource.NewWithAttributes(
		semconv.SchemaURL,
		semconv.ServiceNameKey.String(service),
		attribute.String("zepay.demo.scenario", "INC-2026-0419-payment-ledger-ghost-debits"),
	))

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.AlwaysSample()), // demo — capture every span
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))
	return tp.Shutdown
}

// Services call otel.Tracer("service-name") directly — no wrapper needed.

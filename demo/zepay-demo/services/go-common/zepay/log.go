// Package zepay — shared scaffolding for the Zepay demo Go services.
//
// Why this exists:
//   The workflow's log_agent clusters log entries by exception_type,
//   affected_components, and correlation_ids. For the storyboard to
//   land, EVERY service must emit structured JSON with identical
//   field names so the agent doesn't have to guess at shapes. This
//   module centralizes that.
//
// Fields every log line carries:
//   ts       — RFC3339Nano
//   service  — service name (set at boot)
//   level    — INFO | WARN | ERROR
//   msg      — short human-readable message
//   trace_id — W3C trace_id from the active span, if any
//   span_id  — W3C span_id from the active span, if any
//
// Additional fields are passed via With(...any) — k/v pairs.
package zepay

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"time"

	"go.opentelemetry.io/otel/trace"
)

var serviceName = "unknown"

// SetServiceName fixes the `service` field on every emitted log line.
// Call once from main() at startup; concurrent calls after that are
// undefined, which is fine for this demo.
func SetServiceName(name string) {
	serviceName = name
}

// jsonHandler emits the shape log_agent's clustering expects. We don't
// use slog's built-in JSONHandler directly because:
//   - It emits `time` not `ts`
//   - It emits `level` as "INFO" vs "info" randomly per Go version
//   - It puts trace_id in the wrong place for OTel interop
type jsonHandler struct {
	out   *os.File
	level slog.Level
}

func (h *jsonHandler) Enabled(_ context.Context, lvl slog.Level) bool {
	return lvl >= h.level
}

func (h *jsonHandler) Handle(ctx context.Context, r slog.Record) error {
	obj := map[string]any{
		"ts":      r.Time.UTC().Format(time.RFC3339Nano),
		"service": serviceName,
		"level":   r.Level.String(),
		"msg":     r.Message,
	}
	r.Attrs(func(a slog.Attr) bool {
		obj[a.Key] = a.Value.Any()
		return true
	})
	if span := trace.SpanFromContext(ctx); span.SpanContext().IsValid() {
		obj["trace_id"] = span.SpanContext().TraceID().String()
		obj["span_id"] = span.SpanContext().SpanID().String()
	}
	b, err := json.Marshal(obj)
	if err != nil {
		return err
	}
	_, err = h.out.Write(append(b, '\n'))
	return err
}

func (h *jsonHandler) WithAttrs(_ []slog.Attr) slog.Handler { return h }
func (h *jsonHandler) WithGroup(_ string) slog.Handler       { return h }

// Init sets slog's default logger to our JSON handler and pins the
// service name. Call once from main() before doing anything else.
func Init(service string) {
	SetServiceName(service)
	lvl := slog.LevelInfo
	if os.Getenv("LOG_LEVEL") == "DEBUG" {
		lvl = slog.LevelDebug
	}
	slog.SetDefault(slog.New(&jsonHandler{out: os.Stdout, level: lvl}))
}

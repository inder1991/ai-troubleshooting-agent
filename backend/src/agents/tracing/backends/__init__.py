"""Pluggable TraceBackend implementations — Jaeger + Tempo for v1; Zipkin in v2."""

from .base import TraceBackend, BackendError, BackendUnreachable, TraceNotFound

__all__ = ["TraceBackend", "BackendError", "BackendUnreachable", "TraceNotFound"]

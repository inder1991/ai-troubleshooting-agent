"""PR-J — observability middleware.

Two cross-cutting concerns handled here:

  · Request-ID propagation. Every request gets a `request_id` — either
    the caller-supplied ``X-Request-ID`` (respected so traces can cross
    service boundaries) or a freshly-minted UUID. The ID is:
      - Stashed in a contextvar so every log line inside the request
        frame carries it automatically.
      - Stamped on the response as ``X-Request-ID``.
      - Included in the structured error envelope when something fails.

  · Structured error envelopes. FastAPI's default error JSON is
    ``{"detail": "..."}`` — no status code, no request_id, no error
    class. Add handlers for HTTPException + unhandled Exception that
    emit a consistent shape:

        {
          "error": "HTTPException",
          "detail": "<human-readable reason>",
          "status_code": 400,
          "request_id": "<uuid>"
        }

    Clients (and the frontend's ``extractErrorDetail``) now have a
    single contract to parse against.
"""
from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the active request's ID, or empty string outside a request."""
    return _request_id_ctx.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that stamps each request with a stable request_id."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        # Accept the incoming ID when it looks reasonable; clamp length
        # so an attacker-chosen header can't bloat logs.
        if incoming and 8 <= len(incoming) <= 128 and all(
            c.isalnum() or c in "-_." for c in incoming
        ):
            rid = incoming
        else:
            rid = uuid.uuid4().hex
        token = _request_id_ctx.set(rid)
        try:
            request.state.request_id = rid
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response


def _envelope(
    *,
    error: str,
    detail: str,
    status_code: int,
    request_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": error,
        "detail": detail,
        "status_code": status_code,
        "request_id": request_id,
    }
    if extra:
        body.update(extra)
    return body


def register_error_envelope_handlers(app: FastAPI) -> None:
    """Attach normalized JSON error-envelope handlers to the FastAPI app.

    Three handlers cover the common cases:
      · HTTPException — already carries a status + detail; echo them.
      · RequestValidationError — 422 with Pydantic's `.errors()` list
        under an ``errors`` extra so clients can point at the bad field.
      · Exception — 500 fallback. Log the traceback so ops can
        investigate; client only sees a sanitized detail.
    """

    @app.exception_handler(HTTPException)
    async def _http_exc(request: Request, exc: HTTPException) -> JSONResponse:
        rid = getattr(request.state, "request_id", "") or get_request_id()
        detail_val = exc.detail
        detail = (
            detail_val if isinstance(detail_val, str) else str(detail_val)
        )
        body = _envelope(
            error="HTTPException",
            detail=detail,
            status_code=exc.status_code,
            request_id=rid,
        )
        headers = dict(exc.headers or {})
        if rid:
            headers[REQUEST_ID_HEADER] = rid
        return JSONResponse(status_code=exc.status_code, content=body, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(
        request: Request, exc: RequestValidationError,
    ) -> JSONResponse:
        rid = getattr(request.state, "request_id", "") or get_request_id()
        # Pydantic's errors() may contain bytes (the raw request body)
        # for certain parsing failures; FastAPI's JSON encoder can't
        # serialize those. Sanitize each entry so we always emit
        # pure-JSON + drop oversized `input` values that might leak
        # caller-provided content into logs.
        safe_errors: list[dict[str, Any]] = []
        for err in exc.errors():
            e = dict(err)
            inp = e.get("input")
            if isinstance(inp, (bytes, bytearray)):
                try:
                    e["input"] = inp.decode("utf-8", errors="replace")[:500]
                except Exception:
                    e["input"] = "<binary>"
            elif isinstance(inp, str) and len(inp) > 500:
                e["input"] = inp[:500] + "…"
            # ctx often carries exception classes which aren't JSON-serializable.
            ctx = e.get("ctx")
            if isinstance(ctx, dict):
                e["ctx"] = {k: str(v) for k, v in ctx.items()}
            safe_errors.append(e)
        body = _envelope(
            error="RequestValidationError",
            detail="Request body failed validation.",
            status_code=422,
            request_id=rid,
            extra={"errors": safe_errors},
        )
        return JSONResponse(status_code=422, content=body,
                            headers={REQUEST_ID_HEADER: rid} if rid else {})

    @app.exception_handler(Exception)
    async def _unhandled_exc(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "") or get_request_id()
        logger.exception(
            "Unhandled exception during request",
            extra={"request_id": rid, "path": str(request.url.path)},
        )
        # Do NOT leak the exception string to the client — it may
        # contain secrets pulled from the shell env or stack context.
        body = _envelope(
            error="InternalServerError",
            detail="An unexpected error occurred. See request_id for correlation.",
            status_code=500,
            request_id=rid,
        )
        return JSONResponse(status_code=500, content=body,
                            headers={REQUEST_ID_HEADER: rid} if rid else {})

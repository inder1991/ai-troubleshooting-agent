"""Q17 i — RFC 7807 problem+json helper.

Every error response from a route uses this. Content-Type is
`application/problem+json`. Extensions (code, retry_after, etc.) pass
through as additional JSON fields."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

PROBLEM_JSON = "application/problem+json"


def problem_response(
    *,
    type_: str,
    title: str,
    status: int,
    detail: str,
    instance: str,
    **extensions: Any,
) -> JSONResponse:
    """Construct an RFC 7807 problem+json response.

    Args:
      type_: a URI identifying the problem class
        (e.g., "https://debugduck.dev/errors/budget-exceeded").
      title: short human-readable summary.
      status: HTTP status code.
      detail: human-readable explanation specific to this occurrence.
      instance: URI reference identifying the specific occurrence
        (typically request.url.path).
      **extensions: additional JSON fields for machine-actionable context
        (e.g., code="BUDGET_EXCEEDED", retry_after=30).
    """
    body: dict[str, Any] = {
        "type": type_,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
    }
    body.update(extensions)
    return JSONResponse(content=body, status_code=status, media_type=PROBLEM_JSON)

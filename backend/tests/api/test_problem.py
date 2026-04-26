"""Sprint H.0b Story 10 — RFC 7807 helper (Q17 i)."""

from __future__ import annotations


def test_problem_response_includes_required_fields() -> None:
    from src.api.problem import problem_response

    resp = problem_response(
        type_="https://debugduck.dev/errors/budget-exceeded",
        title="Budget exceeded",
        status=400,
        detail="Tool call budget reached",
        instance="/api/v4/x",
    )
    body = resp.body.decode()
    for required in ("type", "title", "status", "detail", "instance"):
        assert f'"{required}"' in body


def test_problem_response_content_type_is_problem_json() -> None:
    from src.api.problem import problem_response
    resp = problem_response(type_="x", title="y", status=400, detail="z", instance="/")
    assert resp.media_type == "application/problem+json"


def test_problem_response_extensions_passthrough() -> None:
    from src.api.problem import problem_response
    resp = problem_response(
        type_="x", title="y", status=400, detail="z", instance="/",
        code="BUDGET_EXCEEDED",
        retry_after=30,
    )
    body = resp.body.decode()
    assert '"code":"BUDGET_EXCEEDED"' in body
    assert '"retry_after":30' in body

---
scope: backend/
owner: "@platform-team"
priority: high
type: directory
---

# Backend conventions

These rules apply to all code under `backend/`. They override the root
`CLAUDE.md` on conflict.

## Stack
- FastAPI for HTTP. SQLModel for DB. Pydantic v2 for validation.
- pytest + Hypothesis for tests. Async tests via pytest-asyncio.
- mypy strict on `src/{api,storage,models,learning,agents/**/runners}/` and `.harness/`.

## Async posture (Q7)
- `async def` for I/O (httpx, DB, file). `def` for pure compute.
- `httpx.AsyncClient` only — never `requests` or `urllib`.
- Wrap unavoidable blocking work with `asyncio.to_thread`.

## Database (Q8)
- All DB access goes through `StorageGateway` (`src/storage/gateway.py`).
- Routes/services/agents do NOT import `AsyncSession` or `Session` directly.
- `models/db/` holds `table=True` SQLModel classes; never returned from API.
- API responses use `models/api/` (frozen=True). Agent tools use `models/agent/`.
- Schema changes ship with an Alembic migration in `alembic/versions/`.

## Testing (Q9)
- `pytest` + `Hypothesis` (required on `learning/`, `storage/gateway.py`,
  `agents/**/parsers/`, and any `extract_*`/`parse_*`/`resolve_*`/`calibrate_*`/
  `score_*` function).
- ≥ 90 % patch coverage via `diff-cover` (CI gate).
- No live LLM/telemetry calls in tests — mock with `respx` or `pytest-mock`.

## Validation (Q10)
- API request models: `model_config = ConfigDict(extra="forbid")`.
- API response models: `frozen=True`.
- Agent schemas: both.
- Numeric fields on boundaries: `Field(ge=..., le=...)`.
- String fields: `Field(max_length=N)`.
- Confidence/probability fields: `Field(ge=0.0, le=1.0)`.
- Global `strict=True` is BANNED.

## Errors (Q17)
- Expected outcomes return typed `Result[T, E]` from `src/errors/`.
- Unexpected failures raise; let them bubble to FastAPI's global handler.
- API error responses use RFC 7807 (`application/problem+json`) via
  `src/api/problem.py::problem_response()`.
- Outbound HTTP MUST go through `src/utils/http.py::with_retry`
  (max 3 attempts, exponential jitter, explicit timeout).

## Logging (Q16)
- `structlog` only — no `print()`, no bare stdlib logging.
- Every log call carries an `event` snake_case name + context kwargs
  (`session_id`, `tenant_id` when applicable).
- ERROR/CRITICAL include `exc_info=True` (or use `.exception()`).
- Agent runners and workflow steps wrap their bodies in OpenTelemetry
  spans (`tracer.start_as_current_span("agent.<name>.run", attributes={...})`).

## Imports & naming (Q18)
- Absolute imports only (`from src.x import y`). No relative imports
  outside test files.
- Files: `snake_case.py`. Classes: `PascalCase`. Functions: `snake_case`.
- Tests live in `backend/tests/<mirrored-tree>/test_<module>.py`.

# DebugDuck API — operator guide

This is the human-curated companion to the auto-generated OpenAPI spec
at `/openapi.json`. The OpenAPI spec is the canonical source of truth
for endpoint shapes; this document explains intent, error model, and
conventions.

## Authentication

All mutating endpoints (POST/PUT/PATCH/DELETE) require an authenticated
user via `Depends(require_user)`. Elevated scopes are gated by
`Depends(require_admin)` or `Depends(require_tenant_admin)`.

A small set of read endpoints is intentionally public (health, version,
metrics) — see the `rate_limit_exempt` allowlist in
`.harness/security_policy.yaml` for the full list. Authentication is
enforced by the `security_policy_b` check (Q13.B) at pre-commit; the
generated truth file `.harness/generated/security_inventory.json` shows
the live ratio of routes with auth coverage.

## Endpoints

Endpoints are organized under `/api/v4/<domain>/...`. Each domain owns its
own tag in OpenAPI. The complete generated list (with handler names,
request/response types, and protection flags) lives at
`.harness/generated/backend_routes.json` — regenerated on `make harness`.

To add a new endpoint:
1. Add the handler in `backend/src/api/<domain>_endpoints.py`.
2. Wire up `Depends(require_user)` (or scope-elevated equivalent).
3. Wire up `@limiter.limit(...)` per Q13.
4. Add a Pydantic request model under `backend/src/models/api/...` with
   `model_config = ConfigDict(extra="forbid", frozen=True)`.
5. Run `make harness` to refresh the route inventory.
6. Run `make validate-fast` — security_policy_b will flag missing auth /
   rate-limit / CSRF.

## Error model

All errors are returned as `application/problem+json` per RFC 7807:

```json
{
  "type": "https://debugduck.example/errors/<code>",
  "title": "Human-readable title",
  "status": 400,
  "detail": "Specifics for this occurrence",
  "instance": "/api/v4/incidents/abc123"
}
```

Expected outcomes (validation failures, lookups, idempotent retries) return
typed `Result[T, E]` server-side and translate `Err(...)` into problem+json
with the appropriate status code. Unexpected failures raise a domain
exception that the global handler also renders as problem+json. The
`error_handling_policy` check (Q17) enforces:
- `HTTPException` calls must include a `detail=` kwarg.
- `raise NewError(...)` inside `except E as exc:` must use `from exc` to
  preserve the cause chain.
- `raise Exception(...)` is too broad — use a specific subclass.

Domain exception classes + `Result` aliases inventoried at
`.harness/generated/error_taxonomy.json`.

## Rate limits

Per Q13.B, every mutating endpoint must declare a
`@limiter.limit("<spec>")` decorator (slowapi). The default spec is
`10/minute` per IP per route; high-volume endpoints (webhooks) declare
their own.

Exempt routes — health, metrics, version — are explicitly listed in
`.harness/security_policy.yaml.rate_limit_exempt`. Adding to this list
requires an ADR per Q15.

## CSRF

Per Q13.B, mutating endpoints reachable from the browser require the
`CsrfProtect` dependency annotation. Webhook receivers and machine-to-
machine endpoints (where the caller cannot present a CSRF token) are
listed under `.harness/security_policy.yaml.csrf_exempt`.

## Where to look next

- `/openapi.json` — canonical endpoint shapes.
- `.harness/generated/backend_routes.json` — current route inventory.
- `.harness/generated/security_inventory.json` — auth/rate-limit/CSRF coverage.
- `.harness/generated/error_taxonomy.json` — exception classes + Result aliases.
- `.harness/README.md` — harness contributor guide.

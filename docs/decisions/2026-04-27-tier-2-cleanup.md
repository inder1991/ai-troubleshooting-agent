# Tier 2 cleanup — generator/check correctness fixes

Status: Accepted
Date: 2026-04-27
Owner: @inder

## Context

The awesome-harness-engineering audit identified 8 documented-but-unfixed
correctness/quality bugs in the harness substrate (Tier 2). This ADR lands
all of them in one batch since they're independent + small.

## Decision

### #6 — Tighten `extract_outbound_http_inventory`

Replace the broad "any `.get/.post/...` in any file mentioning httpx" filter
with receiver-chain analysis. New `_httpx_aliases_in(tree)` discovers every
binding that aliases `httpx` or an httpx client (catches `import httpx`,
`import httpx as hx`, `from httpx import AsyncClient`, `client = httpx.Async
Client(...)`, `async with httpx.AsyncClient() as c:`). The call detector
then walks the receiver attribute chain and only fires when the leftmost
Name is one of those aliases.

**Before:** 1609 callsites on DebugDuck (catches `dict.get()` everywhere).
**After:** 32 callsites (real httpx usage only).

### #7 — Replace pyproject.toml regex with `tomllib`

`extract_dependency_inventory._parse_pyproject` now uses Python 3.11+
stdlib `tomllib` instead of the line-by-line regex. Handles multi-line
specs, comments, `extras_require`, and PEP 631 syntax correctly.

### #8 — Tighten 3 most-touched policy schemas

Replaced `additionalProperties: true` with explicit shapes for:
- `logging_policy.schema.json` (spine_paths, logger_attr_names, secret_log_patterns)
- `error_handling_policy.schema.json` (spine_paths, http_exception_names, generic_exception_names)
- `documentation_policy.schema.json` (spine_python_paths, frontend_jsdoc_paths, adr_required_on_change)

Also added pattern constraints (`^[a-z_]+$` for logger attrs, `^[A-Z][A-Za-z0-9_]+$`
for exception class names). Other policy schemas (dependencies, performance_budgets,
security_policy, accessibility_policy, typecheck_policy) deliberately stay
permissive — they're less load-bearing and have unstable shapes. Tighten in
follow-up sprints as patterns stabilize.

### #9 — CSRF middleware detection

`security_policy_b._module_has_csrf_middleware(tree)` walks for `app.add_middleware(*Csrf*Middleware, ...)`
calls. When detected, the per-route CsrfProtect dependency check is skipped
for that module — middleware enforces CSRF globally, requiring it per-route
is redundant.

### #10 — Consumer-overridable spine paths (mechanism + 1 PoC migration)

Added `.harness/spine_paths.yaml` (with matching schema) declaring a stable
set of role → paths mappings (backend_src, backend_api, frontend_src, etc.).

New `_common.spine_paths(role, fallback)` helper reads the yaml; falls back
to the hardcoded default (preserves backward compat). Cached per-process.

Migrated `accessibility_policy.py` as proof-of-concept:
```python
DEFAULT_ROOTS = spine_paths("frontend_src", ("frontend/src",))
```

The other 11 checks with hardcoded backend/frontend paths remain on the old
mechanism. Migrating them all is a follow-up sprint; this commit ships the
mechanism so future check authors use it from day one.

### #11 — `harness_rule_coverage` skips code blocks

New `_strip_code_blocks(markdown)` removes fenced ` ``` ` blocks AND inline
` `code` ` spans before the rule-reference regex runs. Catches `H-N` /
`Q<N>` tokens inside example commit messages, sample yaml, etc., which are
not real rule references.

### #12 — `refresh_baselines.py` warns on growth

After writing a refreshed baseline, compare entry count vs. the pre-existing
baseline (if any). If new > old, emit `[WARN] baseline grew N → M (+delta)`
to stderr. Doesn't fail; surfaces silent widening for human review.

### #13 — `refresh_baselines.py` atomic per-check writes

Each baseline now stages to `<check>_baseline.json.new`, then atomic-renames
onto the canonical path. A mid-run crash leaves the previous baseline intact
instead of producing a half-written file.

## Consequences

- Positive — `outbound_http_inventory.json` shrinks 50× (1609 → 32 entries)
  on DebugDuck, making the file actually useful for AI consumption.
- Positive — pyproject.toml parsing is now correct on every standard layout.
- Positive — schema drift on the 3 most-edited policy yamls surfaces at
  pre-commit instead of at runtime.
- Positive — CSRF middleware false positives go away; security_policy_b
  no longer over-counts violations on apps with global CSRF.
- Positive — JS-only / Python-only / non-monorepo consumers can override
  spine paths in one yaml file.
- Positive — `harness_rule_coverage` no longer flags rules quoted in
  example commit messages.
- Positive — `refresh_baselines` is now safe to interrupt mid-flight.
- Negative — #10 only covers 1 of 12 hardcoded checks. Full migration
  is its own sprint; the mechanism is live so it's incremental.
- Negative — 5 policy schemas remain permissive. Same — incremental.
- Neutral — the spine_paths.yaml ships under `.harness/` and is overlay-
  preserved by sync_harness (consumer overrides survive `make harness-sync`).

## Alternatives considered

- **Migrate all 12 hardcoded checks in one commit (#10)** — rejected:
  too large to review in one ADR; mechanism + PoC is the safer split.
- **Tighten all 8 policy schemas** — rejected: 5 of them have unstable
  shapes (security/perf/a11y are still actively evolving). Premature
  tightening = false rejections.
- **Use `pyproject.toml.uv` parser instead of `tomllib`** — rejected:
  uv-specific; we want vanilla PEP 631.

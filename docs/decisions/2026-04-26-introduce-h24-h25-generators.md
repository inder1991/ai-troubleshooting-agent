# H.2.4 + H.2.5 generators (a11y, docs, logging, errors, outbound_http, conventions)

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

H.2.4 + H.2.5 land six more generators that complete the AI-readable
inventory surface. After this, the only remaining generator is H.2.6
(typecheck_inventory), and the orchestrator (`tools/run_harness_regen.py`)
ties them all together.

Bundling H.2.4 (a11y + docs) and H.2.5 (logging + errors + outbound_http +
conventions) into a single PR/ADR because they share the same template,
no cross-generator dependencies, and would otherwise generate six tiny
repetitive ADRs.

## Decision

Add six generators:

- **`extract_accessibility_inventory`** — `frontend/src/components/ui/*.tsx`
  paired with `*.test.tsx` axe presence; `accessibility_policy.yaml`
  incident_critical pages cross-referenced with `frontend/e2e/a11y/<page>.spec.ts`
  presence; soft_warn rule list.
- **`extract_documentation_inventory`** — every public Python symbol in
  `documentation_policy.yaml.spine_python_paths` with `has_docstring` flag;
  every TS/TSX export in `frontend_jsdoc_paths` with `has_jsdoc` flag; every
  ADR under `docs/decisions/*.md` with title.
- **`extract_logging_inventory`** — `backend/src/observability/logging.py`
  structlog processors + tracing init flag; per-file `log.<level>(...)` calls
  in spine python with their correlation kwargs.
- **`extract_error_taxonomy`** — public exception classes under
  `backend/src/{errors,exceptions}/**/*.py` with parent classes and
  truncated docstring; `Result*` type aliases.
- **`extract_outbound_http_inventory`** — every `.get/.post/.put/.patch/
  .delete/.request(...)` call in spine python files that mention `httpx`,
  with `retry_decorated` (enclosing function has `@with_retry`) and
  `timeout_explicit` (`timeout=` kwarg present) flags.
- **`extract_conventions_inventory`** — projection of `pyproject.toml [tool.ruff]`,
  `frontend/eslint.config.js` (regex), and `commitlint.config.{js,cjs,mjs}`.

Each generator: paired schema under `.harness/schemas/generated/`,
deterministic write via `_common.write_generated`, `--print`/`--root`
flags. Combined smoke test under
`tests/harness/generators/test_h24_h25_generators.py`.

## Consequences

- Positive — full AI-readable surface coverage: routes (H.2.2), models
  (H.2.3), a11y, docs, logging, errors, outbound_http, conventions.
- Positive — `extract_documentation_inventory` surfaces 770 python +
  343 frontend symbols on this repo, immediately usable as a "fix-loop"
  worklist by the AI.
- Negative — `extract_outbound_http_inventory` is over-broad: it counts
  every `.get()` in any file that imports `httpx`, including dict
  `.get()` calls. 1609 callsites on this repo. Acceptable today; the
  consumer can filter further. Tighten by requiring the call's receiver
  chain to reference `httpx` in a follow-up.
- Negative — `extract_logging_inventory` mistakes any `.info()` /
  `.warning()` etc. on any object as a log call (no import resolution).
  Acceptable; the AI loader cares about the count + correlation_kwargs
  ratio, not perfect identification.
- Neutral — emit-time on the live repo: ~7s aggregate across the six.
  None individually slow enough to need a fast/full split.

## Alternatives considered

- **Separate ADR per generator** — rejected: six near-identical
  decisions with the same shape would crowd `docs/decisions/` and add
  no signal.
- **Use full TypeScript / mypy AST for higher accuracy** — rejected:
  pulls in heavy dependencies; the regex/Python-AST tradeoff is well
  inside acceptable false-positive rate.
- **Defer outbound_http_inventory until httpx receiver tracking is
  precise** — rejected: even noisy data is useful for the AI to
  spot-check; perfect is the enemy of shipped.

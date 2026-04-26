# Frontend generators (H.2.1) — api_endpoints, ui_primitives, routes, test_coverage_targets

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

Sprint H.2 ships 18 generators that extract canonical truth from source
code into `.harness/generated/*.json` for downstream consumption by
checks and the AI loader. H.2.1 covers the four frontend extractors.
Each generator collapses a per-file regex scan into a single sorted
JSON document so the AI sees a single source of truth instead of
re-scanning code on every prompt.

## Decision

Add four generators under `.harness/generators/`:

- **`extract_api_endpoints.py`** — walks `frontend/src/services/api/*.ts`
  (skipping `client.ts`, `index.ts`, `*.test.ts`) and emits per
  `apiClient<T>(...)` call: `{name, url_template, method, response_type, file}`.
  Output: `.harness/generated/api_endpoints.json`.
- **`extract_ui_primitives.py`** — walks `frontend/src/components/ui/*.tsx`
  and emits per file: `{name, exports, file, uses_radix}`. Sets
  `uses_radix=true` when any `from "@radix-ui/..."` import appears.
  Output: `.harness/generated/ui_primitives.json`.
- **`extract_routes.py`** — reads `frontend/src/router.tsx` and emits per
  `createBrowserRouter([{path, element: <X/>}])` entry: `{path, page_module,
  lazy_imported}`. Cross-references `lazy(() => import())` and sync
  `import X from` declarations to set `lazy_imported`. Output:
  `.harness/generated/routes.json`.
- **`extract_test_coverage_targets.py`** — reads `frontend/vitest.config.ts`
  and emits per glob in `coverage.thresholds`: `{glob, branches, functions,
  lines, statements}`. Output: `.harness/generated/test_coverage_targets.json`.

Each generator:
- Uses `write_generated(name, payload)` from H.2.0 (sort_keys + indent +
  trailing newline → byte-deterministic).
- Sorts results before writing for stable output across runs.
- Has a paired JSON Schema at `.harness/schemas/generated/<name>.schema.json`
  enforcing `additionalProperties: false` on every entry — schema regression
  surfaces at pre-commit.
- Supports `--print` for hermetic test invocation; `--root <dir>` lets the
  test driver point at a fixture tree instead of the live repo.

A shared smoke test under `tests/harness/generators/test_h21_frontend_generators.py`
exercises all four against a synthetic frontend tree at
`tests/harness/fixtures/generators/frontend/src/...` and asserts:
1. The expected entries are extracted (names, methods, types, lazy flags).
2. Two consecutive runs produce byte-identical output (determinism gate).

## Consequences

- Positive — checks and the AI loader can read a single sorted JSON file
  for each domain instead of re-walking source on every invocation.
- Positive — schema validation gates the generator outputs; a regex tweak
  that drops `request_type` would fail the schema rather than silently shrink
  the data surface.
- Positive — generators are pure functions of the source tree, so
  `make harness` is byte-idempotent (re-running with no source changes
  produces empty `git diff`).
- Negative — regex-based parsers will miss exotic call shapes (e.g. spread
  request options). Acceptable today; tighten as patterns emerge.
- Neutral — five new files in `.harness/generated/` (4 outputs + the
  pre-existing README); reviewers see the data surface alongside the
  generator changes.

## Alternatives considered

- **Use the TypeScript compiler API to parse .ts/.tsx** — rejected: would
  introduce a node subprocess in the harness hot path, balloon wall time,
  and add a TypeScript version pin to the harness's deps.
- **Inline the extraction logic into the consumers (checks)** — rejected:
  duplicates the regex per consumer and breaks the H-4 contract that
  generators are the single source of truth.
- **One test file per generator** — rejected: the four generators share the
  same harness pattern; one combined test file keeps the test code DRY and
  signals that they are siblings.

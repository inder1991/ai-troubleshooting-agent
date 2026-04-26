# Generator substrate — write_generated helper + generated/ schema gate (H.2.0)

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

Sprint H.2 lands 18 generators that read source code and emit JSON
"truth files" under `.harness/generated/` for downstream consumption by
checks and the AI loader. Without a shared write helper and a schema
gate for the outputs, each generator would re-implement deterministic
serialization and we'd have no way to catch a generator that drifts
from its declared shape.

## Decision

Two minimal substrate pieces:

- **`.harness/generators/_common.py::write_generated(name, payload)`** —
  writes `payload` (any JSON-serializable value) to
  `.harness/generated/<name>.json` with `sort_keys=True`, `indent=2`,
  trailing newline. Plus iterator helpers `iter_python_files` and
  `iter_tsx_files` so each generator stays short.
- **`.harness/checks/harness_policy_schema.py`** — extended to also
  validate every `.harness/generated/*.json` against
  `.harness/schemas/generated/<name>.schema.json` (warn-only when schema
  is missing, ERROR on validation violation). Mirrors the policy yaml
  validator added in H.1d.4.

The pre-existing `write_generated(target, schema_version, payload)`
signature is dropped (no live callers); the new signature matches the
H.2 plan and has cleaner ergonomics for the per-generator code.

## Consequences

- Positive — every H.2.1–H.2.6 generator can be ~30 LoC of "extract +
  emit" since serialization and the path convention are centralized.
- Positive — schema drift surfaces at pre-commit, not at runtime when a
  consumer tries to read the wrong shape.
- Negative — schema-missing is WARN today, not ERROR. Allows H.2.1–H.2.6
  to land generators incrementally before all schemas exist. Tighten to
  ERROR after H.2.6.
- Neutral — `_common.py` grows from 25 to ~50 LoC; the iterator
  helpers anticipate H.2.1+ usage.

## Alternatives considered

- **Keep the `$schema_version` envelope in every generated file** —
  rejected: simpler-is-better. Schema versioning lives in the schema
  file's `$schema` URL plus git history of the schema file itself.
- **Defer the generated/ schema validation until a separate H.2 story**
  — rejected: validating one generator's output is the same code as
  validating one yaml; folding it into harness_policy_schema costs less
  than another check file.

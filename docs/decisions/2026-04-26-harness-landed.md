# 2026-04-26 — AI harness GA

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

Sprints H.0a → H.2 land the full harness substrate as designed in
`docs/plans/2026-04-26-ai-harness.md`:

- 25 H-rules (process + structural contracts).
- 19 Q-decisions (locked stack/style/security/etc choices).
- 24 active checks under `.harness/checks/` (covering frontend,
  backend, cross-stack, security, accessibility, documentation,
  logging, error handling, conventions, typecheck, plus four
  harness self-tests and an output-format gate).
- 18 generators under `.harness/generators/` emitting deterministic
  JSON inventories under `.harness/generated/`.
- A two-phase orchestrator (`tools/run_harness_regen.py`) that
  parallelizes independents and sequences dependents.
- A SessionStart hook (`.claude/settings.json` →
  `tools/_session_start_hook.sh` → `tools/load_harness.py`) that
  bootstraps AI sessions with the canonical harness context.
- `tools/init_harness.py` to scaffold the harness into a fresh repo.
- Inner-loop pre-commit budget kept at H-17's 30s wall via the
  fast/full tier partition.

## Decision

The harness becomes the contract for AI-assisted development in this
repo:

- Every commit runs `make validate-fast` via the pre-commit hook
  (installed by `make harness-install`).
- Every CI run executes `make validate-full` — adds tests + heavyweight
  checks (output_format_conformance, backend_testing, frontend_testing,
  backend_async_correctness, backend_db_layer, typecheck_policy).
- Adding/changing any `.harness/*_policy.yaml`,
  `.harness/dependencies.yaml`, or `.harness/checks/*.py` requires an
  ADR (enforced by Q15.adr-required-on-change).
- Type-check baseline growth requires an ADR (enforced by
  Q19.baseline-grew-without-adr).
- Adding a new H-rule reference to the plan requires either a check
  or a `rule_coverage_exemptions.yaml` entry (enforced by H-21).
- Adding a new check requires paired
  `tests/harness/fixtures/<rule>/{violation,compliant}/` (enforced by
  H-24).

## Consequences

- Positive — AI suggestions get richer context via the per-domain
  generated inventories; policy violations caught locally before
  review; contributors have a single source of truth ("see
  .harness/README.md") for "how things work here".
- Positive — every check ships with paired fixtures and an H-25
  docstring; future contributors see the template clearly.
- Positive — `init_harness.py` makes the harness portable: another
  repo can adopt this contract in one command.
- Negative — initial suite of checks produces noise on legacy code;
  mitigated via per-rule baselines under `.harness/baselines/` (see
  `_TICKETS.md` for ownership of each grandfathered debt list).
- Negative — soft enforcement of the ADR rule (Q15) means a contributor
  can technically add an unrelated ADR to satisfy the gate. Acceptable
  trade-off for now; tighten if abused.
- Neutral — the harness adds ~30 files under `tools/`, `.harness/`,
  and `tests/harness/`. Reviewers should treat these as substrate, not
  per-PR concerns.

## Follow-up

- Promote tickets in `.harness/baselines/_TICKETS.md` to issues with
  owners and dates.
- Tighten generated-file schemas (currently permissive
  `additionalProperties: true`) as fixture coverage grows.
- Tighten `extract_outbound_http_inventory` (currently over-broad —
  catches dict `.get()` calls).
- Convert `extract_dependency_inventory` from regex-based pyproject.toml
  parsing to `tomllib` once the repo standardizes on Python 3.11+.
- Sprint H.3 (extraction): publish the harness as a standalone
  `ai-harness` repo so it can be consumed by other projects without
  forking debugduck.

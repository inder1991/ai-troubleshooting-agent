# Releases

## v1.0.4 — Enforcement + telemetry batch (signed)

Four awesome-harness audit follow-ups, all $0 / no API spend:

- **CI workflow** — `.github/workflows/validate.yml` runs `make validate-full`
  on every PR + push to main. Closes the `git commit -n` bypass loophole.
- **`.gitattributes`** — `eol=lf` on all text extensions; prevents Windows
  checkout from breaking the `make harness` byte-deterministic regen gate.
- **HarnessCard** — `.harness/HARNESS_CARD.yaml` declares at-a-glance what
  this harness covers using the CAR (Control / Agency / Runtime) decomposition.
  Includes `coverage.covered` + `coverage.not_covered` (honest about gaps),
  `consumer_fit` profiles, distribution commands. Schema-validated.
- **Rolling failure log** — `tools/run_validate.py` appends every `[ERROR]`
  to `.harness/.failure-log.jsonl` with timestamp + commit + session UUID +
  host. 10 MB rotation cap, gitignored. Gives the AI trend visibility ("rule
  X fired 47 times this week") with zero API cost — closest thing to "evals"
  we can build for free.

## v1.0.3 — Tier 2 completion (signed)

Closes the Tier 2 partial completions from v1.0.2:

- **Every check now resolves spine paths via `.harness/spine_paths.yaml`.**
  14 module-level migrations + 5 inline migrations. Adds 9 new roles
  (backend_models_api, backend_models_agent, backend_storage_gateway,
  backend_contracts, backend_learning_sidecars, backend_tests_learning,
  backend_pyproject, frontend_package_json, plus existing). Non-monorepo
  / Python-only / JS-only consumers can adopt the harness with one
  `spine_paths.yaml` override — no check forks needed.
- **5 remaining policy schemas tightened** to `additionalProperties: false`
  with explicit `required` arrays, type constraints, and pattern
  constraints (e.g. `^[A-Z]+:.+$` for `verb:path` exempt entries).
  Schema typos in policy yamls now fail fast at pre-commit.

145/145 check tests pass; harness_policy_schema clean against all
9 policy yamls.

## v1.0.2 — Hardening sweep (signed)

First **signed** release. Consumers no longer need `--no-verify-tag`.

Includes everything from v1.0.1 plus the awesome-harness audit fixes:

- **`load_harness` budget cap** (point 1). New `--max-bytes` flag (default 32 KB)
  caps total emitted bytes. Mandatory tier (root + policies) always emits;
  larger files drop with `[TRUNCATED] <path>` pointers the AI can `cat`. Also
  fixes the long-standing argparse-crash on no-target invocation (which is
  what the SessionStart hook does).
- **GPG signing infrastructure** (point 5). New `tools/setup_signing.sh` +
  `tools/sign_release.sh`. v1.0.2 is signed with key `73A7AF8F04F40EC9`
  (`ai-harness signer`). Public key + import instructions live at
  `docs/keys.md`.
- **Tier 2 cleanup** (8 correctness/quality fixes):
  - `extract_outbound_http_inventory` 1609 → 32 callsites via receiver-chain analysis
  - `extract_dependency_inventory` regex → tomllib (handles multi-line specs + extras)
  - 3 most-touched policy schemas tightened (logging, error_handling, documentation)
  - `security_policy_b` skips per-route CsrfProtect when global CSRF middleware present
  - `.harness/spine_paths.yaml` mechanism for consumer-overridable spine paths (PoC migration)
  - `harness_rule_coverage` strips ` ``` ` blocks + inline `code` before regex
  - `refresh_baselines` warns on baseline growth + atomic per-check writes

## v1.0.1 — Maintenance

Three harness-engineering hardening fixes:

- Stripped DebugDuck-specific tests from carve (218/218 self-tests now green)
- `_session_start_hook.sh` surfaces `load_harness.py` failures with
  `[HARNESS_WARN]` instead of silent degradation
- `sync_harness.py` verifies signed git tags (`--no-verify-tag` escape hatch)

`extract.sh` also strips stale `.harness/{baselines,generated}/*.json` (consumer
regenerates) but preserves the README + `_TICKETS.md` documentation.

## v1.0.0 — initial GA

Seven-sprint substrate for AI-assisted development:

- **H.0a** — schema & substrate (loader, Makefile, root CLAUDE.md, orchestrator).
- **H.0b** — stack-foundation scaffolding (Q5/Q8/Q9/Q11–Q19 configs, gitleaks
  install, mypy/tsc strict baselines).
- **H.1a** — backend basic checks (Q7–Q12 + 4 self-learning invariants).
- **H.1b** — frontend checks (Q1–Q6, Q14, Q18 + meta-validator).
- **H.1c** — cross-stack policy checks (Q13 secrets/auth/rate-limit/CSRF, Q15
  documentation, Q16 logging, Q17 error handling).
- **H.1d** — typecheck enforcement (Q19) + four harness self-tests
  (rule coverage, fixture pairing, policy schema, perf regression) +
  baseline buffer + refresh tool.
- **H.2** — 18 generators emitting deterministic JSON inventories +
  `run_harness_regen` two-phase orchestrator + Claude Code SessionStart hook +
  `init_harness` bootstrap + full contributor docs.

**By the numbers:**
- 24 deterministic checks under `.harness/checks/`.
- 18 deterministic generators under `.harness/generators/`.
- 25 H-rules (process + structural contracts).
- 19 Q-decisions (locked stack/style/security choices).
- `validate-fast` settles at ~18s wall on a representative repo (well within
  H-17's 30s budget).

**Distribution:** scaffold into a fresh repo via
`tools/init_harness.py --target <path> --owner <handle> --tech-stack <python|typescript|polyglot>`,
or pull a pinned version into an existing repo via
`tools/sync_harness.py` (reads `.harness-version`).

See `docs/plans/2026-04-26-ai-harness.md` for the full design and the
seven sprint plans (`2026-04-26-harness-sprint-h*-tasks.md`) for per-task
implementation history.

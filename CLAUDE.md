---
scope: repo
owner: "@platform-team"
priority: highest
type: root
---

# Repo guardrails (always loaded)

You are working in DebugDuck. These behavioral rules apply on every
session. Per-area rules in nearest `CLAUDE.md` override these on conflict
(see Precedence below).

## The one rule that compounds

- Run `make validate-fast` before declaring any task complete.
- If it fails: parse the structured output, fix the violations, re-run.
- Loop until pass or you have an explicit blocker to surface.

## Behavioral guardrails

- Production-grade code only. No placeholders, no `TODO` comments in
  shipped paths. If you cannot complete a task fully, surface a blocker.
- Fix root causes, not symptoms.
- Do not introduce new dependencies without justification (Q11). Spine
  paths require a whitelist update + ADR.
- Do not bypass `make validate-fast`. `--no-verify` on commits is the
  rare exception, not the rule.
- Tests come before code. Red commit, then green commit, then refactor.
  PRs without a preceding `test(red):` commit are rejected at review.

## Precedence (H-5)

When rules conflict, the local-most one wins:

    Root rules  <  Cross-cutting harness  <  Generated facts  <  Directory rules

## Rule Loading Contract (H-11)

For any file under edit at `<target>`, the loader walks:

    1. Load this CLAUDE.md (root).
    2. Walk up <target>'s directory tree; load every CLAUDE.md found.
    3. Load all `.harness/generated/*.json` (machine-readable truth).
    4. Match `.harness/*.md` rule files whose `applies_to` glob matches <target>.
    5. Resolve conflicts via the precedence above. Conflicts surface as
       lint errors, not silent overrides.

The reference implementation lives at `tools/load_harness.py`.

## Output format every check emits (H-16, H-23)

    [SEVERITY] file=<path>:<line> rule=<rule-id> message="..." suggestion="..."

`SEVERITY` is `ERROR`, `WARN`, or `INFO`. ERROR fails `make validate*`.

## Where to look

- Full design: `docs/plans/2026-04-26-ai-harness.md` (the 25 H-rules
  and 19 Q-decisions).
- Per-area conventions: nearest `CLAUDE.md` to the file you're editing.
- Cross-cutting rules: `.harness/*.md` (loaded if `applies_to` matches).
- Current truth (registered checks, valid tokens, contract names):
  `.harness/generated/*.json`.

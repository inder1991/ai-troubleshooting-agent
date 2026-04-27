# load_harness budget cap (point 1)

Status: Accepted
Date: 2026-04-27
Owner: @inder

## Context

Two related bugs:

1. **No budget cap.** `tools/load_harness.py` emits root CLAUDE.md +
   policies + cross-cutting *.md + every `.harness/generated/*.json` in
   one blob. On DebugDuck this is ~700 KB. Claude Code's session-context
   has a finite budget; a 700 KB blob either truncates silently or
   displaces useful conversation context.
2. **`--target` was REQUIRED.** The session-start hook calls
   `python3 tools/load_harness.py` with no flags — argparse crashed,
   `_session_start_hook.sh` swallowed the failure (Point 4 fix now
   surfaces it as `[HARNESS_WARN]`, but the underlying bug remained).

## Decision

Rewrite `tools/load_harness.py`:

### Mode dispatch
- `--target <path>` — per-file mode (existing): walks directory CLAUDE.mds
  + matches cross-cutting files via `applies_to`.
- (no `--target`) — **new global mode** for SessionStart hook: emits root
  + every cross-cutting *.md + every policy + every generated JSON,
  without per-file walk.

### Budget cap
New `--max-bytes <N>` flag, default `32_768` (~8k tokens). Emission order
is priority-based:

| Priority | Source | Behavior under budget |
|---|---|---|
| 1 (must) | Root CLAUDE.md | always emit (overrides budget) |
| 2 (must) | `.harness/*.yaml` policies | always emit |
| 3 (should) | `.harness/*.md` cross-cutting | emit if fits, else `[TRUNCATED]` pointer |
| 4 (should) | Directory CLAUDE.mds (target mode) | same |
| 5 (nice) | `.harness/generated/*.json`, smallest first | emit if fits, else `[TRUNCATED]` pointer |

`[TRUNCATED]` lines look like:
```
[TRUNCATED] .harness/generated/documentation_inventory.json (197975 bytes ~7875 lines) — read with: cat .harness/generated/documentation_inventory.json
```

The AI sees the data exists and where to fetch it on demand. A
`[BUDGET] N / M bytes used` footer surfaces the cap when truncation
happened.

`--max-bytes 0` disables the cap (CI-agent mode).

### Tests added
4 new tests in `tests/harness/test_loader.py`:
- `test_loader_default_budget_caps_output` — global-mode output < 64 KB
  (proves capping is active; was 700 KB before).
- `test_loader_emits_truncated_pointer_when_over_budget` — at 8 KB cap,
  at least one `[TRUNCATED]` pointer appears.
- `test_loader_unlimited_budget_includes_everything` — `--max-bytes 0`
  emits more than the default; no `[TRUNCATED]` lines.
- Updated `test_loader_emits_precedence_order` to include the new
  `policies` tier in the precedence array.

## Consequences

- Positive — SessionStart hook no longer dumps 700 KB. On DebugDuck,
  default cap settles at ~28 KB (5 generated files included, 5
  truncated with pointers).
- Positive — argparse doesn't crash on no-target invocation; the hook
  works as designed for the first time since H.2.7.
- Positive — every truncated file gives the AI a `cat <path>` command
  to fetch on demand. Moves cost from session-start to "only when needed."
- Positive — `--max-bytes 0` preserves the existing CI-agent path
  where full context is wanted.
- Negative — the `[BUDGET]` footer + `[TRUNCATED]` lines themselves
  consume ~500-1000 bytes when the cap is hit. Acceptable.
- Negative — mandatory tier (root + policies) currently runs ~12 KB on
  DebugDuck. If the consumer's mandatory tier alone exceeds `max_bytes`,
  we still emit it (overriding the cap). Documented; acceptable given
  policies are stable and reviewed.
- Neutral — `precedence_order` array gained a new `"policies"` entry.
  One existing test updated; no consumer code reads this array yet.

## Future work (deferred)

- **Layer 4** content-hash caching: emit a hash of the budget-shaped
  output; future hook invocation skips re-emission if hash matches a
  prior session. Would compound with Anthropic's prompt-cache TTL.
- **Tool masking**: per-target filter that hides irrelevant generated
  files. Not implemented; the `applies_to` mechanism on cross-cutting
  *.md is the closest analog today.

## Alternatives considered

- **Compress the output (gzip + base64)** — rejected: Claude Code
  consumes plain text; compression would waste context on the
  ~30 bytes of overhead per file without saving net bytes.
- **Stream the output across multiple SessionStart hook calls** —
  rejected: SessionStart fires once per session; no streaming protocol.
- **Move generated/* truth files OUT of SessionStart entirely** and
  let the AI fetch on demand — rejected: too far in the other
  direction; small generated files (typecheck_inventory at 200 bytes)
  are cheap and high-signal. The smallest-first policy already gets
  most of them in.

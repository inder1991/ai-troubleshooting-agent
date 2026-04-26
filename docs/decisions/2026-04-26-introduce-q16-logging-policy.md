# Introduce Q16 logging_policy check (no print, no silent except, lazy format, no secret literals)

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

The harness lacked enforcement for logging discipline. Spine modules used
`print(...)` instead of structured loggers; broad `except Exception:` blocks
silently swallowed errors with no log line; logger calls used f-strings
(forcing format work even when the level is disabled); occasional log
messages contained secret-shaped literals (e.g. "Authorization: Bearer …",
"password=…"). All of these are detectable via AST without runtime tracing.

## Decision

Add `.harness/checks/logging_policy.py` enforcing four rules under Q16:

- **Q16.no-print-in-spine** — `print(...)` calls inside paths listed under
  `spine_paths` in `.harness/logging_policy.yaml`
  (default: `backend/src/{api,services,storage,agents}/**`).
- **Q16.bare-except-no-log** — `except:` or `except Exception|BaseException:`
  whose body contains no logger method call (`info`/`warning`/`error`/
  `debug`/`critical`/`exception`).
- **Q16.f-string-in-log** — first positional arg to a logger method is an
  `ast.JoinedStr` (f-string). Lazy `%`-style format defers work past level
  filtering.
- **Q16.secret-shaped-log-literal** — first positional arg is a string literal
  containing one of the patterns in `secret_log_patterns` (case-insensitive
  substring match).

Existing violations (207: 152 bare-except, 35 f-string, 19 print, 1 bearer
literal) are grandfathered into
`.harness/baselines/logging_policy_baseline.json`.

## Consequences

- Positive — new code in spine paths must use structured loggers; broad
  excepts must explain via a log call; logger call sites stay performant; one
  more line of defence against secrets sneaking into log streams.
- Positive — pure AST, ~0.9s wall, no external binaries; no degraded mode
  needed.
- Negative — `Q16.secret-shaped-log-literal` is substring-based and will
  occasionally false-positive on benign descriptive text (e.g. "with bearer
  token: %s"). Grandfathered today; fixable by tightening pattern format.
- Neutral — baseline grows by 207 entries.

## Alternatives considered

- **Use `logging` plugin from flake8/ruff** — rejected: harness must be
  zero-extra-deps and produce H-16 unified output; bolting on linters means
  shape adapters and another binary to install/version.
- **Detect logger calls by import alias rather than attr name** — rejected as
  premature complexity; AST attr-name match catches >95% of real call sites
  (`log.info`, `logger.info`, `LOG.info`) without import resolution.

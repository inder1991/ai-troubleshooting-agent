# AI Harness — Second-Pass Audit (Rule Semantics)

**Date:** 2026-04-28
**Scope:** Logic correctness of the 29 individual checks under
`.harness/checks/`. Complements the v1.0.x→v1.2.1 SDET audit
(`docs/plans/2026-04-27-harness-sdet-audit.md`), which covered
orchestration, tooling, signing, and emit-format. This pass asks:
*for each check, does the rule actually catch what its docstring
claims it catches, and does it avoid firing on common idioms that
aren't violations?*

**Method:** Read the implementation of each check; cross-reference
against its module docstring's stated rule list; identify regex/AST
shapes that miss equivalent forms and shapes that over-match common
idioms. Did **not** run each check against synthetic violations —
that would be a third-pass exercise (fuzz the fixture set).

**Status:** **30 new findings** across 7 checks I audited closely.
The remaining 22 checks weren't read line-by-line — a third pass is
likely to produce another ~30 findings of similar shape.

**Severity convention** (different from B-IDs to keep audits separate):
- **S-A1..S-Bn** = `security_policy_a` / `security_policy_b`
- **S-AS, S-DB, S-CV, S-DP** = topic-prefixed for other checks
- **All P3.** None are exploitable bugs — they're rule-semantics
  drift, false positives, or false negatives. Schedule between v1.3.0
  and v2.0.0 depending on consumer pain.

---

## security_policy_a (Q13.A) — 9 findings

### S-A1 (P3) — `LOG_CALL_RE` misses non-canonical logger names

**File:** `.harness/checks/security_policy_a.py:75`

```python
LOG_CALL_RE = re.compile(r'\b(log|logger)\.\w+\s*\(([^)]*)\)', re.DOTALL)
```

Only matches `log.` or `logger.`. Misses `LOG.info(...)`, `_log.info(...)`,
`self.log.info(...)`, custom logger names (the project's own
`logging_policy.yaml.logger_attr_names` lists more). The
`Q13.log-secret-leak` rule under-covers files that follow the policy.

**Fix:** consume `logger_attr_names` from `logging_policy.yaml` (same
source `logging_policy.py` already uses).

### S-A2 (P3) — log body capture truncates on inner parens

**File:** same line as S-A1, `[^)]*)` in the body capture.

A call like `log.info("user", extra={"foo": (1, 2)})` truncates the body at
the first `)`. The secret-shaped substring may live in the truncated
remainder. False negatives.

**Fix:** AST-walk for `Call` whose `func.attr` is in the logger-method
set; iterate `node.args` directly.

### S-A3 (P3) — `httpx` context heuristic fails on long files

**File:** `.harness/checks/security_policy_a.py:149`

```python
if m and "httpx" in source.lower()[:5000]:
```

A long handler (5000+ chars) where `httpx` is imported on line 5001+
won't trigger `Q13.outbound-timeout-required`. False negative.

**Fix:** scan imports up front; cache `imports_httpx: bool` per file.

### S-A4 (P3) — dangerous-pattern misses aliased forms

**File:** `.harness/checks/security_policy_a.py:59-61`

`DANGEROUS_PYTHON_RE` matches literal `eval(`, `exec(`, etc. Misses
`_eval = eval; _eval(x)` and `getattr(__builtins__, 'eval')(x)`.
Acceptable for a static check, but worth documenting in the rule
description.

### S-A5 (P3) — `SHELL_TRUE_RE` misses multi-line subprocess calls

**File:** `.harness/checks/security_policy_a.py:64`

```python
SHELL_TRUE_RE = re.compile(r'[,(]\s*shell\s*=\s*True\b')
```

Requires preceding `,` or `(` on the same line. Misses

```python
subprocess.run(
    cmd,
    shell=True,
)
```

because `shell=True` starts on its own indented line — the `,` is on
the previous line. Common formatting; real false negatives.

**Fix:** AST scan — `Call` whose func is in the subprocess module set,
keyword `shell` with constant value `True`.

### S-A6 (P3) — `TIMEOUT_NONE_RE` misses wrapped + over-fires on attrs

**File:** `.harness/checks/security_policy_a.py:73`

`r'\btimeout\s*=\s*None\b'` misses `timeout=httpx.Timeout(None)` and
fires on `request.timeout = None` (different attribute, not an httpx
arg). Both wrong directions.

### S-A7 (P3) — `UTILS_HTTP_PREFIX` exempts more than it should

**File:** `.harness/checks/security_policy_a.py:82`

```python
UTILS_HTTP_PREFIX = "backend/src/utils/http"
```

No trailing slash → `backend/src/utils/httpx_client.py` is also
exempted. A new file named `http_helpers_v2.py` slips through.

**Fix:** require `"backend/src/utils/http.py"` exact match or
`"backend/src/utils/http/"` prefix (with trailing slash).

### S-A8 (P3) — comment-strip is line-prefix only

**File:** `.harness/checks/security_policy_a.py:103`

`if stripped.startswith("#")` only catches whole-line comments. A
trailing comment containing `shell=True` (e.g.
`x = "demo"  # shell=True example`) still fires. False positive,
relatively rare.

### S-A9 (P3) — docstring claims "six rules"; only **five** are implemented

**File:** `.harness/checks/security_policy_a.py:4-18`

Docstring lists `Q13.secret-detected`, `Q13.dangerous-pattern`,
`Q13.tls-verify-required`, `Q13.outbound-timeout-required`,
`Q13.log-secret-leak`, `Q13.secret-shaped-literal`. The last is
defined nowhere in the file body. Either implement
`Q13.secret-shaped-literal` or remove the claim.

---

## security_policy_b (Q13.B) — 7 findings

### S-B1 (P3) — `_route_decorator_info` only matches `router`/`app`

**File:** `.harness/checks/security_policy_b.py:67`

```python
if node.func.value.id not in {"router", "app"}:
    return None
```

Real-world FastAPI projects use `v1_router`, `users_router`,
`internal_app`, `api_v2`, etc. None of these match — every mutating
route under those routers is silently un-checked.

**Fix:** policy-driven `router_var_names` list, or heuristic
"any `<X>.<verb>(string)` where `X` ends in `_router`/`router`/`app`".

### S-B2 (P3) — `_has_auth_dep` misses `Annotated[]` style

**File:** `.harness/checks/security_policy_b.py:91-100`

Only matches `Depends(<Name>)`. Misses
`Annotated[User, Depends(get_current_user)]` (the FastAPI 0.95+
idiomatic form) and `Depends(<Attribute>)`. Both common; many
modern FastAPI projects will look unauth'd to the check.

**Fix:** also walk `Annotated` annotations; accept `Attribute` as
the auth_fn shape.

### S-B3 (P3) — `_has_csrf_dep` substring match is over-permissive

**File:** `.harness/checks/security_policy_b.py:138-141`

```python
ann_src = ast.dump(arg.annotation)
if "CsrfProtect" in ann_src:
    return True
```

Any annotation containing the substring satisfies the check —
`NoCsrfProtectNeeded`, `MyCsrfProtectStub`, etc. False negatives
that look fine.

**Fix:** require the annotation's class name to *equal* `CsrfProtect`
(or be in a configurable allow-list).

### S-B4 (P3) — `_module_has_csrf_middleware` misses constructor pattern

**File:** `.harness/checks/security_policy_b.py:154-167`

Only checks `app.add_middleware(...)` calls. Misses
`app = FastAPI(middleware=[Middleware(CsrfMiddleware)])` (constructor
pattern is increasingly common). False positive: every per-route
check fires even though CSRF is enforced globally.

### S-B5 (P3) — route paths must be string Constants

**File:** `.harness/checks/security_policy_b.py:72-73`

```python
if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
    return verb, node.args[0].value
```

Misses `router.post(f"/api/{prefix}", ...)` (JoinedStr) and
`router.post(PATH, ...)` (Name reference to a constant). Real
projects often pull route literals into named constants for
testability — those routes go un-checked.

### S-B6 (P3) — early-return only matches `backend/src/api/`

**File:** `.harness/checks/security_policy_b.py:180`

```python
if not (virtual.startswith("backend/src/api/") or path.parent.name == "api"):
    return 0
```

Routers that live elsewhere (`backend/src/services/auth/routes.py`,
`backend/src/v2/handlers/...`) are never scanned. Architecture-
dependent; should consume `spine_paths.yaml`'s `backend_api` role
(which already exists).

### S-B7 (P3) — dead code: `verb != "get"` clause

**File:** `.harness/checks/security_policy_b.py:70`

```python
if verb not in MUTATING_VERBS and verb != "get":
    return None
```

Returns `None` unless verb is mutating *or* `get`. But the only
caller (line 209) immediately filters `verb not in MUTATING_VERBS`.
The `verb != "get"` clause is unreachable — `get` would pass through
this guard then get filtered downstream. Dead branch; the function
should just check `verb in MUTATING_VERBS` and return early
otherwise.

---

## backend_async_correctness (Q7) — 6 findings

### S-AS1 (P3) — docstring claims six rules; **five** are implemented

**File:** `.harness/checks/backend_async_correctness.py:4`

Docstring header says "Six rules enforced" but the body lists only
five: `no-requests`, `no-aiohttp`, `no-asyncio-run-in-handler`,
`no-sync-httpx`, `no-blocking-sleep-in-async`. Off-by-one count.

### S-AS2 (P3) — `import requests` fires inside the canonical wrapper

**File:** `.harness/checks/backend_async_correctness.py:74-79`

`import requests` triggers `Q7.no-requests` even in
`backend/src/utils/http.py` (where the wrapper is supposed to live
*if* it ever needs the sync client). Forces the wrapper file to
baseline its own legitimate import. Should exempt the wrapper path.

### S-AS3 (P3) — `httpx.Client` matcher misses `from httpx import Client`

**File:** `.harness/checks/backend_async_correctness.py:109-115`

Only matches `httpx.Client(...)` literal. `from httpx import Client;
Client(...)` slips through. False negative.

**Fix:** also walk `ImportFrom` to track which name `Client` was
bound to in the file's scope, then match calls to that name.

### S-AS4 (P3) — `time.sleep` matcher misses aliased imports

**File:** `.harness/checks/backend_async_correctness.py:122-136`

`from time import sleep; sleep(1)` doesn't trigger. Same scope-
tracking gap as S-AS3.

### S-AS5 (P3) — `_is_handler_path` over-matches `api_*`

**File:** `.harness/checks/backend_async_correctness.py:50-51`

```python
return "/api/" in virtual or virtual.startswith("api/")
```

`backend/src/utils/api_helpers.py` ↛ matches via `/api_helpers.py`?
No, `/api/` requires the slash after — that one's fine. But
`backend/src/services/api_v2/foo.py` matches via the `/api/` substring
of the parent path? No again, `api_v2` lacks the trailing slash. OK,
this one's actually fine. Striking finding.

### S-AS6 (P3) — renamed imports slip through

**File:** `.harness/checks/backend_async_correctness.py:73-91`

`import requests as r; r.get(...)` doesn't trigger `Q7.no-requests`.
Same gap as S-AS3/4 — no scope tracking.

---

## backend_db_layer (Q8) — 6 findings

### S-DB1 (P3) — docstring claims **eight** rules; **seven** are implemented

**File:** `.harness/checks/backend_db_layer.py:4`

Same off-by-one drift as S-A9 / S-AS1. List enumerates seven; header
says eight.

### S-DB2 (P3) — `RAW_SQL_RE` over-matches docstrings, comments, log messages

**File:** `.harness/checks/backend_db_layer.py:44, 158-167`

```python
RAW_SQL_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\s+\w", re.IGNORECASE)
```

Strips only `#`-prefixed lines. A docstring containing `"INSERT
failed because of …"` or a multiline string template fires the rule.
Real-world false-positive generator.

**Fix:** AST-aware scan that only inspects string literals passed to
`session.execute(...)` / `text(...)` etc., not arbitrary string
content.

### S-DB3 (P3) — justification token has file-level scope

**File:** `.harness/checks/backend_db_layer.py:87`

```python
has_justification = JUSTIFICATION_TOKEN in source
```

One `# RAW-SQL-JUSTIFIED:` comment anywhere in the file silences
*every* raw-SQL warning in that file — even ones added later by a
different developer for unrelated queries. Should require the
justification on the same line or the immediately-preceding line.

### S-DB4 (P3) — `cursor.execute` only matches bare receiver names

**File:** `.harness/checks/backend_db_layer.py:142-149`

`db.cursor.execute(...)`, `self.cursor.execute(...)`,
`await async_cursor.execute(...)` all slip through because the check
requires the receiver to be a single `ast.Name`. Real codebases
rarely keep the cursor at module-name scope.

### S-DB5 (P3) — `text("...")` only matches Name calls

**File:** `.harness/checks/backend_db_layer.py:128-139`

`sqlalchemy.text(...)` and `sa.text(...)` (the typical aliased import
form) slip through. Only `text(...)` literal triggers.

### S-DB6 (P3) — `db-model-needs-table` misses inheritance

**File:** `.harness/checks/backend_db_layer.py:170-189`

If a file's classes inherit from a base that already declared
`table=True`, the subclasses won't carry it explicitly. The check
walks for any class with `table=True` keyword on its own
`ClassDef`. False positive on inheritance-based model patterns.

---

## conventions_policy (Q18) — 4 findings

### S-CV1 (P3) — `DOTDOT_IMPORT_RE` matches single-dot too

**File:** `.harness/checks/conventions_policy.py:43`

```python
DOTDOT_IMPORT_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']\.\.?/[^"']*["']''', re.MULTILINE)
```

`\.\.?/` matches `./` (single dot) OR `../` (double dot). Rule says
"no `../..`"; regex catches `./relative` too. False-positive
generator on a *very* common import pattern.

**Fix:** drop the `?` — use `\.\./`. Also escape correctly:
`\.\./` requires two literal dots followed by slash.

### S-CV2 (P3) — `RELATIVE_IMPORT_RE` catches single-dot bare imports

**File:** `.harness/checks/conventions_policy.py:42`

`r'^\s*from\s+\.+'` catches `from . import x` (single dot, bare
import). Module re-export patterns (`from . import db, schemas`)
are common in `__init__.py`. The rule's spirit is "don't use
relative imports across package boundaries"; same-package re-export
shouldn't fire.

**Fix:** allow single-dot bare-import forms in `__init__.py`.

### S-CV3 (P3) — `PASCAL_CASE_RE` rejects multi-dot stems

**File:** `.harness/checks/conventions_policy.py:40`

`^[A-Z][A-Za-z0-9]*$` disallows dots in the stem. Files like
`MyComponent.test.tsx`, `Component.stories.tsx`, `Hook.types.ts` —
all common modern frontend conventions — fail with a false positive
because `vstem` includes the inner `.test` / `.stories` / `.types`.

**Fix:** strip secondary `.<modifier>` suffixes before applying the
PascalCase regex. Or accept `^[A-Z][A-Za-z0-9.]*$` and require the
*first* dot-segment to be PascalCase.

### S-CV4 (P3) — `SNAKE_CASE_RE` accepts `__dunder__` accidentally

**File:** `.harness/checks/conventions_policy.py:39`

`^[a-z_][a-z0-9_]*$` matches `__init__` ✓ but also matches
`__hidden_unused__`, `__experimental_module__`, etc. The check
silently accepts dunder-named modules at the spine. Probably
intentional, but worth documenting in the rule description.

---

## dependency_policy (Q11) — 4 findings

### S-DP1 (P3) — pyproject parsing only reads `project.dependencies`

**File:** `.harness/checks/dependency_policy.py:81`

```python
deps = data.get("project", {}).get("dependencies", [])
```

Misses:
- `project.optional-dependencies` (extras like `[dev]`, `[test]`).
- `[tool.poetry.dependencies]` for Poetry-format projects.
- `[build-system].requires`.

False negatives in any project not using PEP 621 main format.

### S-DP2 (P3) — `package.json` merges deps + devDependencies

**File:** `.harness/checks/dependency_policy.py:88`

```python
deps = list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys())
```

If the policy ever wants to allow a package only in dev (e.g.
`vitest`, `eslint`), the merge loses that distinction — both go
into the same `allowed` set comparison.

**Fix:** scan each set against its own allow-list:
`policy.npm.runtime_allowed` + `policy.npm.dev_allowed`.

### S-DP3 (P3) — `_bare_dep_name` mishandles git/tarball/alias deps

**File:** `.harness/checks/dependency_policy.py:69-75`

```python
for sep in (">=", "==", "~=", "<=", ">", "<", "[", " "):
```

Doesn't handle `package@1.2.3` (npm version-by-tag), `git+https://…`
(git URL), `package@npm:scoped/...` (npm alias). A git-URL line
becomes a `_bare_dep_name` like `git+https://github.com/...` and
will never match the allow-list — always errors.

### S-DP4 (P3) — `STDLIB_FIRST_PARTY` is hardcoded; missing `tomllib`

**File:** `.harness/checks/dependency_policy.py:45-53`

The set lists stdlib modules explicitly. `tomllib` (Python 3.11+) is
**not** in the list — yet the check itself imports `tomllib` on
line 24. Self-contradictory: any backend file importing `tomllib`
would be flagged as unlisted.

Also missing: `zoneinfo` (3.9+), `graphlib` (3.9+).

**Fix:** use `sys.stdlib_module_names` (3.10+) instead of a hand-
maintained set.

---

## Summary by check (audited so far)

| Check | Findings | Worst |
|-------|----------|-------|
| security_policy_a | 9 | False negatives on log calls + outbound HTTP |
| security_policy_b | 7 | Modern FastAPI `Annotated[]` auth missed |
| backend_async_correctness | 6 | Aliased imports slip every rule |
| backend_db_layer | 6 | Justification-token scope is too wide |
| conventions_policy | 4 | `./relative` flagged as `../..` violation |
| dependency_policy | 4 | `tomllib` imports flagged as unlisted |

**Subtotal: 30 findings across 6 of 29 checks.**

## Not yet audited

23 checks remain unread at line-by-line depth in this pass:

`accessibility_policy`, `audit_emission`, `backend_testing`,
`backend_validation_contracts`, `claude_md_size_cap`,
`contract_typed`, `documentation_policy`, `error_handling_policy`,
`frontend_data_layer`, `frontend_routing`, `frontend_style_system`,
`frontend_testing`, `frontend_ui_primitives`, `harness_card_version`
(new in v1.2.0), `harness_fixture_pairing`, `harness_policy_schema`,
`harness_rule_coverage`, `logging_policy`, `output_format_conformance`,
`owners_present`, `performance_budgets`, `storage_isolation`,
`todo_in_prod`, `typecheck_policy`.

Best estimate from sampled density: another **20–30 findings** of
similar shape lurk in this remainder. A third pass would close them.

## Cross-cutting patterns

The 30 findings cluster into 5 root-cause buckets:

1. **No scope tracking for renamed imports.** `import x as y; y(...)`
   slips every check that matches `x.foo(...)`. Affects backend_async,
   backend_db, dependency_policy. **Fix shape:** small `ImportTracker`
   helper in `_common.py` that returns the canonical module given a
   bound name in a given file.

2. **Regex-only scans miss multi-line and AST-shape variants.**
   `shell=True` on its own line, `from X import Y` instead of
   `X.Y`, `Annotated[T, Depends(f)]` instead of `Depends(f)`.
   **Fix shape:** convert known regex checks to AST.

3. **Substring-style matches over-trigger.** `"CsrfProtect" in
   ann_src`, `"./" matched as "../.."`, `RAW SQL` keyword in any
   string literal. **Fix shape:** require structural equality, not
   substring.

4. **Hand-maintained lists drift from runtime truth.** `STDLIB_FIRST_PARTY`
   missing `tomllib`; `router_var_names` hardcoded to `{router, app}`;
   six-rules-claims that count five. **Fix shape:** consume
   `sys.stdlib_module_names`, policy YAMLs, and add a doc-vs-impl
   conformance test.

5. **File-scope justification/exemption rules.** `RAW-SQL-JUSTIFIED:`
   anywhere in the file silences every SQL warning in it. Same for
   `# noqa` patterns elsewhere. **Fix shape:** require the token on
   the same or preceding line as the violation.

## Recommended cadence

These are P3 polish items, not P0/P1 bugs. Suggested rollout:

- **v1.3.0** — fix the 5 cross-cutting patterns above (especially
  ImportTracker + AST conversions). That alone closes ~20 of the
  30 findings.
- **v1.4.0** — finish the per-check polish (substring → structural,
  scope-tightening, doc-vs-impl drift).
- **v2.0.0** — third-pass audit covering the 23 unread checks +
  fuzz the fixture set.

## Method notes

This pass did NOT:
- Run any check against synthetic violations.
- Audit the 20 generators under `.harness/generators/`.
- Audit the 9 policy YAMLs (`.harness/*.yaml`) for over-permissive
  defaults or schema drift.
- Audit the schemas under `.harness/schemas/`.

Each is a separate audit with its own time budget. None are urgent.

# AI Harness — Consolidated Design & Implementation Plan

**Status:** Finalized 2026-04-26 (supersedes earlier `2026-04-26-ai-harness-design.md`).
**Scope:** Repo-level harness for AI-assisted development. Two consumers, one contract:
  - Consumer 1 — human contributors using Claude Code / Cursor / Copilot in IDE.
  - Consumer 2 — autonomous CI agents that propose PRs without a human in the loop.
**Approach:** TDD (red → green → refactor) on every story. The harness self-tests its own checks (H-24).
**Cadence:** 7 sprints, ~13 weeks at 80% capacity.

---

## 0. Assumptions baked into this plan

| # | Assumption | Default applied |
|---|---|---|
| 1 | Team capacity | 2 engineers (1 backend lead, 1 full-stack), ~26 pts/sprint at 80% load. |
| 2 | Language | All harness scripts in Python (matches backend); calls into TS tooling via subprocess. |
| 3 | Existing tooling | ruff, mypy, pytest (backend); eslint, prettier, tsc, vitest (frontend). Harness wraps these. |
| 4 | CI | None today. Local-first composite enforcement (H-14, H-18). CI is upgrade path running same `make validate` (H-20). |
| 5 | Pre-commit framework | Plain git hook installer for v1; no `pre-commit` framework dependency. |

---

## 1. Locked architectural rules (H-1 through H-25)

These govern HOW the harness works. Stack-specific rules (Q1–Q19) live in §2.

### Rule architecture
| # | Rule |
|---|---|
| **H-1** | Root `CLAUDE.md` ≤ 70 lines. CI-enforced. |
| **H-2** | Per-directory `CLAUDE.md` for local intelligence. Owned by area lead. |
| **H-3** | `.harness/*.md` for cross-cutting rules. Each declares scope via `applies_to` glob. |
| **H-4** | `.harness/generated/` is auto-derived from code. Never hand-edited. Regenerated via `make harness`. |
| **H-5** | Precedence: **Root < Cross-cutting < Generated < Directory**. Local-most wins. |
| **H-6** | Ownership explicit. Every rule file declares `owner:` in front-matter. |
| **H-7** | Progressive rollout — week 1 root + 2-3 directory; week 2 cross-cutting; week 3 generated. |
| **H-8** | Rules reduce prompting overhead, not just enforce quality. |

### Rule contract (E++)
| # | Rule |
|---|---|
| **H-9** | YAML front-matter on every rule file: `scope, owner, priority, applies_to, type`. |
| **H-10** | Generated rules = structured data (JSON/YAML), not markdown. |
| **H-11** | Reference loading algorithm documented in root `CLAUDE.md` ("Rule Loading Contract" section). |
| **H-12** | Conflicts surface as lint errors, not silent overrides. |
| **H-13** | Loader is a real script (`tools/load_harness.py`), used by IDE, CI, validators alike. |

### Enforcement spine — Local-first composite
| # | Rule |
|---|---|
| **H-14** | `make validate` is the harness contract. One entry point, five execution contexts. |
| **H-15** | Root `CLAUDE.md` mandates AI self-validation before declaring done. |
| **H-16** | Validation output structured: `[SEVERITY] file=<path>:<line> rule=<rule-id> message="..." suggestion="..."`. |
| **H-17** | Two tiers. `validate-fast` < 30s (lint + typecheck + custom checks). `validate-full` adds tests + heavy audits. |
| **H-18** | Pre-commit hook (recommended, opt-in via `make harness-install`) wraps `validate-fast`. |
| **H-19** | Discipline is the temporary CI. `CONTRIBUTING.md` documents the human checklist. |
| **H-20** | CI is an upgrade path, not the blocker. Same `make validate` runs verbatim when CI lands. |
| **H-21** | Every rule has a programmatic check. Rules without validators are documentation. |

### Quality discipline (from 15 best-practice principles)
| # | Rule |
|---|---|
| **H-22** | Rules must be specific and measurable. No vague rules. |
| **H-23** | Validator output includes a `suggestion` field — the AI uses it to self-correct. |
| **H-24** | The harness has its own test suite under `tests/harness/`. Every check has paired violation + compliant fixtures. |
| **H-25** | Design for failure first. Every check/generator/loader function answers in its docstring: missing input? malformed input? upstream failed? |

---

## 2. Locked stack decisions (Q1–Q19)

Each decision is the canonical rule reference. Long-form rule text lives in the per-domain `CLAUDE.md` and the `.harness/<topic>_policy.yaml` config files. The check column names the `.harness/checks/<file>.py` that enforces it; the generator column names the `.harness/generators/<file>.py` that produces the truth file the AI reads.

### Frontend
| Q | Decision | Config | Check | Generator |
|---|---|---|---|---|
| **Q1** | **Tailwind only** + dynamic-value escape hatch (`width:`, `height:`, `transform:`, etc.). No CSS imports, no styled-components, no CSS-in-JS. Class merging via `cn()`. | `frontend/CLAUDE.md` | `frontend_style_system.py` | — |
| **Q2** | **TanStack Query for server state** + React Context/`useState` for UI state. **Controlled Zustand** allowed for app-wide UI only with `// JUSTIFICATION:` comment. Redux/MobX/Recoil/Jotai banned. | `frontend/CLAUDE.md` | (consolidated into `frontend_data_layer.py`) | — |
| **Q3** | **Hand-written typed client** under `frontend/src/services/api/`. Single `apiClient<T>()` wrapper in `client.ts`. Components consume via TanStack Query hooks; never import services/api directly. No axios. | `frontend/CLAUDE.md` | `frontend_data_layer.py` (consolidates Q2 + Q3) | `extract_api_endpoints.py` |
| **Q4** | **shadcn/ui pattern**: Radix-based primitives copied locally to `frontend/src/components/ui/`. No business logic in primitives. No raw `<button>`/`<input>`/`<a onClick>` in feature components. No primitive wrappers; edit in place. MUI/Chakra/Mantine banned. | `frontend/CLAUDE.md` | `frontend_ui_primitives.py` | `extract_ui_primitives.py` |
| **Q5** | **Vitest** (unit + integration, colocated `*.test.ts(x)`) + **Playwright** (e2e, quarantined under `frontend/e2e/`). **Hard coverage gate** on `services/api/ ≥ 90%` and `hooks/ ≥ 85%`; ungated elsewhere. Jest/Cypress banned. | `frontend/CLAUDE.md` + `vitest.config.ts` thresholds | `frontend_testing.py` | `extract_test_coverage_targets.py` |
| **Q6** | **React Router v6** with `createBrowserRouter`. Single `frontend/src/router.tsx` route table. No file-based routing; no inline route components; no raw `<a href="/...">` for internal nav. Lazy-imported page components. | `frontend/CLAUDE.md` | `frontend_routing.py` | `extract_routes.py` |
| **Q14** | **WCAG 2.2 AA**. Hard gate: axe-core on every shadcn primitive (Vitest) + on incident-critical pages (Playwright). jsx-a11y eslint plugin at error level. **Required:** semantic HTML + focus management (Radix dialog only) + accessible names on all interactive controls. **Soft warn:** color-only-signal (deferred from hard until rule is non-noisy). | `frontend/CLAUDE.md` + `.harness/accessibility_policy.yaml` | `accessibility_policy.py` | `extract_accessibility_inventory.py` |

### Backend
| Q | Decision | Config | Check | Generator |
|---|---|---|---|---|
| **Q7** | **FastAPI only** + **async strictly at I/O boundaries**, sync for pure compute. No requests/aiohttp; httpx.AsyncClient only. asyncio.run banned in handlers. CPU-bound work in async wrapped with `to_thread`. | `backend/CLAUDE.md` | `backend_async_correctness.py` | `extract_backend_routes.py` |
| **Q8** | **SQLModel** wrapped in `StorageGateway`. **Quarantine**: only storage layer imports `AsyncSession`. **Model separation**: `models/db/` ≠ `models/api/` ≠ `models/agent/`. **Alembic** migrations append-only. **Raw SQL** allowed only in `storage/analytics.py` with `# RAW-SQL-JUSTIFIED:` comment. | `backend/CLAUDE.md` | `backend_db_layer.py` | `extract_db_models.py` + `extract_storage_gateway_methods.py` |
| **Q9** | **pytest** + **Hypothesis** (required on `learning/`, `storage/gateway.py`, `agents/**/parsers/`, and `extract_*`/`parse_*`/`resolve_*`/`calibrate_*`/`score_*` functions). **≥ 90% patch coverage** via `diff-cover`. **No live LLM/telemetry calls** (mock with respx / pytest-mock). | `backend/CLAUDE.md` | `backend_testing.py` | `extract_test_coverage_required_paths.py` + `extract_test_inventory.py` |
| **Q10** | **Pydantic v2 strict at boundaries**. API requests: `extra="forbid"`. API responses: `frozen=True`. Agent schemas: both. Internal models: `extra="ignore"` allowed. **Constraint discipline iv**: bounds (`Field(ge=, le=, max_length=)`) required on all API/agent boundary fields. Confidence/probability fields: `Field(ge=0, le=1)`. Global `strict=True` BANNED. | `backend/CLAUDE.md` | `backend_validation_contracts.py` | `extract_validation_inventory.py` |

### Cross-stack
| Q | Decision | Config | Check | Generator |
|---|---|---|---|---|
| **Q11** | **Hybrid dependency policy**: whitelist on architectural spine (`backend/src/{api,storage,models,agents}`, `frontend/src/{services/api,hooks}`), blacklist global. Audit (`pip-audit`, `npm audit`) **only on dependency-file diffs**. Lockfiles committed. | `.harness/dependencies.yaml` | `dependency_policy.py` | `extract_dependency_inventory.py` |
| **Q12** | **Hard-gate** what's deterministic: agent budgets (`tool_calls_max`, `tokens_max`, `wall_clock_max`), DB query time (≤ 100 ms in fixtures), bundle size (initial ≤ 220 KB gz, route ≤ 100 KB gz, CSS ≤ 50 KB gz). **Soft-track** what's CI-variable: API p99, Lighthouse FCP/TTI/CLS. | `.harness/performance_budgets.yaml` | `performance_budgets.py` | `extract_performance_budgets.py` |
| **Q13** | **Maximum security strictness**: gitleaks on commits + CI (A); Pydantic + auth + per-route rate limit + CSRF on every mutating endpoint (i); banned dangerous patterns: `eval/exec/os.system/shell=True/pickle.loads/yaml.load/dangerouslySetInnerHTML/new Function/document.write` (α); TLS-only outbound HTTP, `verify=False` banned, secret-shaped strings auto-redacted in logs (P). | `.harness/security_policy.yaml` + `.gitleaks.toml` | `security_policy.py` | `extract_security_inventory.py` |
| **Q15** | **Docs**: contract-surface Python docstrings only (B — routes, gateway, models/api, models/agent, agents/runners, harness scripts). **OpenAPI** auto-generated as canonical spec + curated `docs/api.md` (ii). **JSDoc** on hooks/lib/services only (β). **ADRs required** (P) for any PR that adds a spine dep, changes a contract, modifies harness rules, alters a Q1–Q19 decision, or changes performance/security policy. | `.harness/documentation_policy.yaml` + `docs/decisions/_TEMPLATE.md` | `documentation_policy.py` | `extract_documentation_inventory.py` |
| **Q16** | **structlog** backend + browser console + error-reporter SDK on frontend (D + i). **Discipline**: no print/console.log in src (α); mandatory event/level/timestamp/session_id/tenant_id context (β); secret-redaction processor (γ); strict log levels DEBUG/INFO/WARNING/ERROR/CRITICAL (δ); **OpenTelemetry spans** required on agent runners + workflow steps (ε). | `.harness/logging_policy.yaml` | `logging_policy.py` | `extract_logging_inventory.py` |
| **Q17** | **Hybrid error model** (C): expected outcomes return typed `Result[T, E]`; unexpected failures raise. **RFC 7807** problem+json on the wire (i) with `Content-Type: application/problem+json`. **Frontend**: `<ErrorBoundary>` per route + per critical card; errors propagate to TanStack Query `.error` (α). **Mandatory retry + timeout** on every outbound httpx call via `with_retry` decorator: max 3 attempts, exponential jitter, retry on 502/503/504/timeout/network (P). | `.harness/error_handling_policy.yaml` | `error_handling_policy.py` | `extract_error_taxonomy.py` + `extract_outbound_http_inventory.py` |
| **Q18** | **Python imports** (D): ruff isort defaults + absolute imports (no `from .x`) + alphabetized within section. **TypeScript** (iv): `import/order` + `import/no-default-export` (except pages and config files) + path alias `@/` required (no `../`). **File naming** (α): backend snake_case files / PascalCase classes; frontend PascalCase components / camelCase hooks (`useXxx.ts`) / kebab-case dirs. **Commits** (P): Conventional Commits, subject ≤ 72 chars, imperative mood. | `.harness/conventions_policy.yaml` + ruff/eslint/commitlint configs | `conventions_policy.py` | `extract_conventions_inventory.py` |
| **Q19** | **Python type-checking** (B): `mypy --strict` on `storage/`, `learning/`, `models/`, `api/`, `agents/**/runners/`, `.harness/`. **TypeScript** (iii): `strict: true` + `noUncheckedIndexedAccess: true`. **Enforcement** (β — baseline): existing violations grandfathered in `.harness/baselines/{mypy,tsc}_baseline.json`; new violations block merge; baseline growth requires ADR. | `.harness/typecheck_policy.yaml` + `.harness/baselines/` | `typecheck_policy.py` | `extract_typecheck_inventory.py` |

---

## 3. Architecture

### 3.1 File layout

```
debugduck/                                ← repo root
├── CLAUDE.md                             ← root behavioral rules (≤ 70 lines)
├── AGENTS.md                             ← symlink → CLAUDE.md (cross-vendor alias)
├── .cursorrules                          ← pointer: "see CLAUDE.md and CLAUDE.md in subdirectories"
├── Makefile                              ← single contract entry point
├── CONTRIBUTING.md                       ← human discipline checklist (H-19)
│
├── tools/
│   ├── load_harness.py                   ← THE rule loader (H-13)
│   ├── run_validate.py                   ← orchestrator for `make validate*`
│   ├── run_harness_regen.py              ← orchestrator for `make harness`
│   └── install_pre_commit.sh             ← `make harness-install` target
│
├── .harness/
│   ├── README.md                         ← how the harness works (for humans)
│   ├── dependencies.yaml                 ← Q11 spine whitelist + global blacklist
│   ├── performance_budgets.yaml          ← Q12 hard + soft gates
│   ├── security_policy.yaml              ← Q13 secret/auth/dangerous patterns
│   ├── accessibility_policy.yaml         ← Q14 a11y rules + axe scope
│   ├── documentation_policy.yaml         ← Q15 docstring + ADR rules
│   ├── logging_policy.yaml               ← Q16 logger config + tracing rules
│   ├── error_handling_policy.yaml        ← Q17 error model + retry policy
│   ├── conventions_policy.yaml           ← Q18 imports + naming + commits
│   ├── typecheck_policy.yaml             ← Q19 strict paths + baseline
│   │
│   ├── python-style.md                   ← cross-cutting (applies_to: backend/**/*.py)
│   ├── frontend-tokens.md                ← cross-cutting (applies_to: frontend/src/**)
│   ├── security.md                       ← cross-cutting
│   ├── accessibility.md                  ← cross-cutting
│   ├── api-contracts.md                  ← cross-cutting
│   │
│   ├── checks/                           ← 14 custom checks
│   │   ├── _common.py
│   │   ├── claude_md_size_cap.py         (H-1)
│   │   ├── owners_present.py             (H-6)
│   │   ├── frontend_style_system.py      (Q1)
│   │   ├── frontend_data_layer.py        (Q2 + Q3)
│   │   ├── frontend_ui_primitives.py     (Q4)
│   │   ├── frontend_testing.py           (Q5)
│   │   ├── frontend_routing.py           (Q6)
│   │   ├── backend_async_correctness.py  (Q7)
│   │   ├── backend_db_layer.py           (Q8)
│   │   ├── backend_testing.py            (Q9)
│   │   ├── backend_validation_contracts.py  (Q10)
│   │   ├── dependency_policy.py          (Q11)
│   │   ├── performance_budgets.py        (Q12)
│   │   ├── security_policy.py            (Q13)
│   │   ├── accessibility_policy.py       (Q14)
│   │   ├── documentation_policy.py       (Q15)
│   │   ├── logging_policy.py             (Q16)
│   │   ├── error_handling_policy.py      (Q17)
│   │   ├── conventions_policy.py         (Q18)
│   │   ├── typecheck_policy.py           (Q19)
│   │   └── output_format_conformance.py  (H-16/H-23 conformance)
│   │
│   ├── generators/                       ← 14 truth-file generators
│   │   ├── _common.py
│   │   ├── extract_api_endpoints.py
│   │   ├── extract_ui_primitives.py
│   │   ├── extract_routes.py
│   │   ├── extract_test_coverage_targets.py
│   │   ├── extract_backend_routes.py
│   │   ├── extract_db_models.py
│   │   ├── extract_storage_gateway_methods.py
│   │   ├── extract_test_coverage_required_paths.py
│   │   ├── extract_test_inventory.py
│   │   ├── extract_validation_inventory.py
│   │   ├── extract_dependency_inventory.py
│   │   ├── extract_performance_budgets.py
│   │   ├── extract_security_inventory.py
│   │   ├── extract_accessibility_inventory.py
│   │   ├── extract_documentation_inventory.py
│   │   ├── extract_logging_inventory.py
│   │   ├── extract_error_taxonomy.py
│   │   ├── extract_outbound_http_inventory.py
│   │   ├── extract_conventions_inventory.py
│   │   └── extract_typecheck_inventory.py
│   │
│   ├── generated/                        ← machine-readable truth (NEVER hand-edited)
│   │   ├── README.md                     ← warns "DO NOT EDIT"
│   │   └── *.json                        ← one per generator above
│   │
│   └── baselines/                        ← Q19 type-check baselines
│       ├── mypy_baseline.json
│       └── tsc_baseline.json
│
├── backend/
│   ├── CLAUDE.md                         ← backend-wide rules
│   ├── alembic/                          ← migrations (Q8)
│   ├── pyproject.toml                    ← ruff isort, mypy strict overrides, pytest config
│   └── src/
│       ├── CLAUDE.md
│       ├── api/CLAUDE.md
│       ├── agents/CLAUDE.md
│       ├── learning/CLAUDE.md
│       ├── storage/                      ← gateway quarantine (Q8)
│       │   ├── gateway.py
│       │   ├── engine.py
│       │   ├── analytics.py              ← raw-SQL-justified
│       │   └── _timing.py                ← @timed_query (Q12)
│       ├── models/
│       │   ├── db/                       ← SQLModel table=True (Q8)
│       │   ├── api/                      ← request/response (Q10 forbid+frozen+bounded)
│       │   ├── agent/                    ← agent tool schemas (Q10)
│       │   └── internal/                 ← extra=ignore allowed
│       ├── errors/                       ← Q17 typed Result + error classes
│       ├── utils/
│       │   └── http.py                   ← Q17 with_retry + httpx wrappers
│       ├── observability/
│       │   ├── logging.py                ← Q16 structlog config
│       │   └── tracing.py                ← Q16 OpenTelemetry init
│       └── api/
│           └── problem.py                ← Q17 RFC 7807 helper
│
├── frontend/
│   ├── CLAUDE.md                         ← frontend-wide rules
│   ├── tsconfig.json                     ← Q19 strict + noUncheckedIndexedAccess
│   ├── vite.config.ts                    ← Q12 manualChunks per-route
│   ├── vitest.config.ts                  ← Q5 coverage thresholds
│   ├── eslint.config.js                  ← Q14 jsx-a11y + Q18 import rules
│   ├── playwright.config.ts
│   ├── lighthouserc.json                 ← Q14 soft-gate config
│   ├── e2e/
│   │   └── a11y/                         ← Q14 Playwright a11y specs
│   └── src/
│       ├── components/
│       │   ├── ui/                       ← Q4 shadcn primitives (owned locally)
│       │   └── Investigation/CLAUDE.md
│       ├── hooks/                        ← Q3 TanStack Query wrappers; ≥ 85% coverage
│       ├── services/
│       │   └── api/                      ← Q3 typed client; ≥ 90% coverage
│       │       ├── client.ts             ← single apiClient<T> wrapper
│       │       └── <domain>.ts           ← typed functions per domain
│       ├── lib/
│       │   ├── utils.ts                  ← Q4 cn() helper
│       │   └── errorReporter.ts          ← Q16 frontend error reporter wrapper
│       ├── pages/                        ← Q6 lazy-imported, default exports OK
│       ├── stores/                       ← Q2 justified Zustand stores
│       └── router.tsx                    ← Q6 single route table
│
├── docs/
│   ├── plans/                            ← committed plans (this file lives here)
│   ├── decisions/                        ← Q15 ADRs (YYYY-MM-DD-<slug>.md)
│   │   └── _TEMPLATE.md
│   └── api.md                            ← Q15 curated API guide
│
└── tests/
    └── harness/                          ← H-24 harness's own test suite
        ├── checks/
        ├── generators/
        ├── fixtures/
        │   ├── violation/                ← per-rule "this fires"
        │   └── compliant/                ← per-rule "this is silent"
        └── test_loader.py
```

### 3.2 Validation tiers

| Tier | Command | Time budget | Contains |
|---|---|---|---|
| **Fast** | `make validate-fast` | < 30s | Syntax, lint, typecheck (against baseline), all 22 custom checks, harness self-checks |
| **Full** | `make validate-full` | minutes | Fast + pytest (with Hypothesis + diff-cover) + Vitest (with coverage) + bundle-budget + agent-budget tests |
| **Soft** | `make perf-soft` | minutes (CI only) | Lighthouse + API benchmarks (PR comment, no merge block) |

### 3.3 Discovery flow (loader)

```
tools/load_harness.py --target <file>
  ├── 1. Load root CLAUDE.md
  ├── 2. Walk up directory: collect every CLAUDE.md from <file>'s dir up to root
  ├── 3. Load all .harness/generated/*.json
  ├── 4. Match .harness/*.md using `applies_to` patterns against <file>
  └── 5. Resolve conflicts using precedence (Local > Generated > Cross-cutting > Root)
   → outputs single concatenated context block, sorted, deterministic
```

### 3.4 Output format (binding for all checks per H-16, H-23)

```
[SEVERITY] file=<path>:<line> rule=<rule-id> message="<what's wrong>" suggestion="<concrete fix>"
```

`SEVERITY ∈ {ERROR, WARN, INFO}`. ERROR fails `make validate*`. WARN/INFO reported but non-blocking.

### 3.5 Five execution contexts

| Context | What runs | Trigger | On failure |
|---|---|---|---|
| AI session loop (Consumer 1) | `make validate-fast` | Claude Code, before declaring done | AI parses output, fixes, re-runs |
| Terminal | `make validate-full` | Manual, before commit | Operator fixes, re-runs |
| Pre-commit hook | `make validate-fast` | Git, on `git commit` | Commit blocked (bypassable with `--no-verify`) |
| CI (future) | `make validate-full` | GitHub Actions on PR push | PR cannot merge |
| Autonomous agent (Consumer 2) | `make validate-full` | Agent's own loop | Agent parses output, fixes, retries (bounded) |

---

## 4. Foundations

### 4.1 Definition of Ready (DoR)
- [ ] Acceptance criteria as Given/When/Then.
- [ ] Test plan lists ≥ 1 failing-first test per AC.
- [ ] Dependencies on other stories named.
- [ ] Estimate (1, 2, 3, 5, 8) agreed.
- [ ] If story adds a check: violation + compliant fixtures identified (H-24).

### 4.2 Definition of Done (DoD)
- [ ] Every AC has a passing test.
- [ ] Test pyramid respected (unit > integration > e2e).
- [ ] Cyclomatic complexity ≤ 10 per function.
- [ ] H-1 through H-25 not violated (PR checklist).
- [ ] If story added a check: violation/compliant fixtures pass.
- [ ] Output of any new check conforms to H-16/H-23.
- [ ] No `# TODO` in production paths.

### 4.3 TDD discipline (binding)
1. **Red** — failing test first. Commit: `test(red): <story-id> — <test name>`.
2. **Green** — minimum code to pass. Commit: `feat(green): <story-id> — <change>`.
3. **Refactor** — improve structure, tests stay green. Commit: `refactor: <story-id> — <description>`.

PRs without preceding red commit are rejected.

### 4.4 Story-point legend

| Points | Meaning |
|---|---|
| 1 | Trivial, < 0.5 day |
| 2 | Single function/schema change, ~0.5–1 day |
| 3 | Multi-file change, ~1–2 days |
| 5 | Cross-component change with design, ~2–4 days |
| 8 | Significant feature, ~4–8 days; if higher, split |

Sprint capacity: 2 engineers × 13 pts × 80% = **~26 pts/sprint**. Actual loaded plan budgets up to ~32; sprints flagged "tight" mean overrun risk.

### 4.5 Cross-cutting non-negotiables
- Every check ships with violation + compliant fixtures (H-24).
- Output format binding (H-16, H-23). `output_format_conformance.py` enforces.
- Performance budget: `validate-fast` < 30s on 2024-era laptop.
- Discovery rate ≥ 1% for any sampling rule (per the inviolable design rules in the related self-learning plan).

---

## 5. Sprint plan

| Sprint | Length | Focus | Pts |
|---|---|---|---|
| **H.0a** | 2 weeks | Schema + scaffold + loader (ten stories from original plan §3 — Makefile, root CLAUDE.md, loader, run_validate, first per-directory CLAUDE.md, front-matter validator, harness-install, harness test infra, AGENTS.md alias, CONTRIBUTING.md) | ~31 |
| **H.0b** | 2 weeks | Stack-foundation scaffolding for Q5/Q8/Q9/Q11/Q12/Q13/Q14/Q15/Q16/Q17/Q18/Q19 (vitest config, Alembic, pytest config, dependencies.yaml, perf budgets + timer, gitleaks + slowapi, a11y tooling, ADR template + ruff D, structlog + OTel, Result + retry + RFC 7807 helpers, conventions configs, typecheck baselines) | ~30 |
| **H.1a** | 2 weeks | Backend basic checks: storage_isolation, audit_emission, contract_typed, todo_in_prod, backend_async_correctness, backend_db_layer, backend_testing, backend_validation_contracts, dependency_policy, performance_budgets | ~30 |
| **H.1b** | 2 weeks | Frontend checks: frontend_style_system, frontend_data_layer (Q2+Q3), frontend_ui_primitives, frontend_testing, frontend_routing, accessibility_policy, conventions_policy, output_format_conformance | ~30 |
| **H.1c** | 2 weeks | Security + Docs + Logging + Errors checks: security_policy (split into 2 stories), documentation_policy, logging_policy, error_handling_policy | ~30 |
| **H.1d** | 1 week | typecheck_policy + harness self-test convention checks (claude_md_size_cap, owners_present already shipped in H.0a; this sprint adds typecheck enforcement + cross-check harness self-consistency) | ~20 |
| **H.2** | 2 weeks | All 14 generators + Claude Code session-start hook + harness-init template + final docs + onboarding polish | ~32 |

**Total: 7 sprints, ~13 weeks (~3 months).**

### 5.1 Sprint H.0a — Schema & Substrate

Same as the original plan §3 (carried forward verbatim). Ten stories, ~31 pts. Exit criteria:
- Root + 3 directory CLAUDE.md files in place.
- Loader returns deterministic context block for any target file.
- `make harness-install` installs pre-commit hook idempotently.
- Harness test infra (fixtures pattern, `assert_check_fires`, `assert_check_silent` helpers) ready.
- AGENTS.md alias + `.cursorrules` pointer + CONTRIBUTING.md committed.

### 5.2 Sprint H.0b — Stack-foundation scaffolding

Tactical stories that scaffold the configs + helper modules every later check depends on. Each is a small "wire it up" story; no business-logic work.

| ID | Title | Pts |
|---|---|---|
| H.0b.1 | `vitest.config.ts` thresholds + Playwright project skeleton (Q5) | 2 |
| H.0b.2 | Alembic init + first baseline migration matching current state (Q8) | 3 |
| H.0b.3 | `pytest-cov` + `diff-cover` + `Hypothesis` installed; pytest config in `pyproject.toml` (Q9) | 2 |
| H.0b.4 | `.harness/dependencies.yaml` seeded with current spine deps + global blacklist + schema validator (Q11) | 2 |
| H.0b.5 | `.harness/performance_budgets.yaml` seeded + `StorageGateway @timed_query` decorator + agent `assert_within_budget` helper (Q12) | 3 |
| H.0b.6 | gitleaks installed + `.gitleaks.toml` seeded + `slowapi` installed for rate-limit middleware (Q13) | 3 |
| H.0b.7 | `eslint-plugin-jsx-a11y` configured + `vitest-axe` + `@axe-core/playwright` installed (Q14) | 2 |
| H.0b.8 | `docs/decisions/_TEMPLATE.md` scaffolded + ruff `D`-class config + `eslint-plugin-jsdoc` installed (Q15) | 2 |
| H.0b.9 | `structlog` + OpenTelemetry SDKs installed; `backend/src/observability/{logging,tracing}.py`; frontend error reporter wrapper at `lib/errorReporter.ts` (Q16) | 5 |
| H.0b.10 | `src/errors/Result.py` + `src/utils/http.py` (`with_retry`) + `src/api/problem.py` (RFC 7807) + frontend `<ErrorBoundary>` primitive in `components/ui/` + `tenacity` installed (Q17) | 5 |
| H.0b.11 | eslint config + commitlint config + ruff isort config + tsconfig path alias + vite alias resolution wired (Q18) | 3 |
| H.0b.12 | `pyproject.toml` mypy strict per-module config + `tsconfig.json` strict + `noUncheckedIndexedAccess` + initial `mypy_baseline.json` + `tsc_baseline.json` generated and committed (Q19) | 3 |

Each story carries a tiny test asserting "config file exists with required keys" (H-24 fixture pair pattern, miniaturized).

### 5.3 Sprint H.1a — Backend basic checks

10 checks. Each story is the same shape (template):
- AC-1: Check exists at `.harness/checks/<rule_id>.py`
- AC-2: Output conforms to H-16 + H-23
- AC-3: Violation fixture causes ERROR
- AC-4: Compliant fixture is silent
- AC-5: Wired into `make validate-fast`
- AC-6: Completes on full repo in < 2s
- AC-7: H-25 docstring present (missing/malformed/upstream-failed answered)

| ID | Check | Rule families | Pts |
|---|---|---|---|
| H.1a.1 | `backend_async_correctness.py` | 6 | 5 |
| H.1a.2 | `backend_db_layer.py` | 8 | 5 |
| H.1a.3 | `backend_testing.py` | 6 | 5 |
| H.1a.4 | `backend_validation_contracts.py` | 8 | 5 |
| H.1a.5 | `dependency_policy.py` | 5 | 5 |
| H.1a.6 | `performance_budgets.py` | 6 | 3 |
| H.1a.7 | `audit_emission.py` (gateway writes call _audit) | 1 | 2 |
| H.1a.8 | `contract_typed.py` (no Optional[Any] in sidecars; from self-learning plan) | 1 | 2 |
| H.1a.9 | `todo_in_prod.py` | 1 | 1 |
| H.1a.10 | `storage_isolation.py` (cursor.execute outside storage/) | 1 | 2 |

### 5.4 Sprint H.1b — Frontend checks

| ID | Check | Rule families | Pts |
|---|---|---|---|
| H.1b.1 | `frontend_style_system.py` | 4 | 5 |
| H.1b.2 | `frontend_data_layer.py` (Q2 + Q3) | 9 | 5 |
| H.1b.3 | `frontend_ui_primitives.py` | 5 | 5 |
| H.1b.4 | `frontend_testing.py` | 5 | 5 |
| H.1b.5 | `frontend_routing.py` | 5 | 3 |
| H.1b.6 | `accessibility_policy.py` | 6 | 5 |
| H.1b.7 | `conventions_policy.py` (Q18 wraps ruff/eslint/commitlint output) | 9 | 5 |
| H.1b.8 | `output_format_conformance.py` (validates other checks' output shape) | 1 | 2 |

### 5.5 Sprint H.1c — Security + Docs + Logging + Errors

| ID | Check | Rule families | Pts |
|---|---|---|---|
| H.1c.1 | `security_policy.py` part A: secrets + outbound HTTP + dangerous patterns | 5 | 5 |
| H.1c.2 | `security_policy.py` part B: API auth/rate-limit/CSRF detection | 3 | 5 |
| H.1c.3 | `documentation_policy.py` | 7 | 5 |
| H.1c.4 | `logging_policy.py` | 8 | 8 |
| H.1c.5 | `error_handling_policy.py` | 9 | 8 |

### 5.6 Sprint H.1d — Typecheck + harness self-tests

| ID | Title | Pts |
|---|---|---|
| H.1d.1 | `typecheck_policy.py` + `make harness-typecheck-baseline` target + diff-against-baseline logic | 5 |
| H.1d.2 | Cross-check: convention test asserts every H-rule has either a check or a doc reference | 3 |
| H.1d.3 | Cross-check: every `.harness/checks/*.py` has paired violation/compliant fixtures | 3 |
| H.1d.4 | Cross-check: every `.harness/<topic>_policy.yaml` has matching schema validator | 3 |
| H.1d.5 | Performance regression test for `make validate-fast` (assert < 30s on standard fixture repo) | 3 |
| H.1d.6 | Accumulated bug-fix buffer | 3 |

### 5.7 Sprint H.2 — Generators + AI integration

14 generators. Same template per story (parse source → emit structured JSON to `generated/`). Plus integration glue.

| ID | Title | Pts |
|---|---|---|
| H.2.1 | Generators 1–4 (frontend: api_endpoints, ui_primitives, routes, test_coverage_targets) | 5 |
| H.2.2 | Generators 5–8 (backend: backend_routes, db_models, gateway_methods, test_coverage_required_paths + test_inventory) | 5 |
| H.2.3 | Generators 9–12 (cross-stack: validation_inventory, dependency_inventory, performance_budgets, security_inventory) | 5 |
| H.2.4 | Generators 13–14 (a11y_inventory + documentation_inventory) | 3 |
| H.2.5 | Generators 15–17 (logging_inventory, error_taxonomy + outbound_http_inventory, conventions_inventory) | 4 |
| H.2.6 | Generator 18 (typecheck_inventory) + `tools/run_harness_regen.py` orchestrator | 3 |
| H.2.7 | Claude Code `.claude/settings.local.json` session-start hook invoking `tools/load_harness.py` | 3 |
| H.2.8 | `harness-init` bootstrap: `tools/init_harness.py` scaffolds the layout into a new repo | 5 |
| H.2.9 | `.harness/README.md` end-user documentation + `docs/api.md` first cut + onboarding polish | 3 |

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `validate-fast` exceeds 30s budget as 22 checks accumulate | Medium | High | Performance assertion in CI (H.1d.5); profile per check; parallelize where safe; move slow checks to `validate-full`. |
| Custom check has false positives, AI gets stuck in fix-loop | Medium | High | Violation + compliant fixtures (H-24) catch this; AI escape hatch — same check fires after 3 fix attempts → raise blocker. |
| Generated files drift between commits | Low | Medium | `generated_not_handedited.py` check runs in `validate-fast`. |
| Rule file owner unreachable, rules go stale | Medium | Medium | Owners declared in front-matter; quarterly review; fallback owner = @platform-team. |
| AI bypasses `make validate` despite mandate | Low | Critical | Pre-commit hook (H-18); convention test analyzes git log for `feat` commits without preceding `test` commits. |
| Check writes silent failure (exit 0 despite violation) | Low | Critical | H-24 violation fixtures catch this; convention test asserts every check emits ≥ 1 ERROR on its violation fixture. |
| Loader produces non-deterministic output | Low | High | Loader output sorted; test asserts byte-identical output across runs. |
| Front-matter typo silently disables a rule | Low | High | Strict YAML schema validation; unknown front-matter keys raise warning. |
| Mypy/tsc baseline grows silently | Medium | Medium | `baseline-auto-regenerated` rule; baseline growth requires ADR (Q15+Q19). |
| AI proposes new spine dep; whitelist update friction | Medium | Low | Q15 ADR template makes the conversation structured; Claude can draft ADR + whitelist update in same PR. |
| Sentry-style frontend error-reporter SDK choice not yet locked | Medium | Low | H.0b.9 selects an SDK; placeholder until then. |

---

## 7. Glossary

- **Harness** — repo-level scaffolding (rules + checks + generators + loader + Makefile) that makes AI-assisted development productive in *this* codebase.
- **Consumer 1** — human contributor using AI in IDE.
- **Consumer 2** — autonomous CI agent that proposes PRs without human in the loop.
- **Spine** — architectural paths under whitelist enforcement: `backend/src/{api,storage,models,agents}` + `frontend/src/{services/api,hooks}`.
- **Root rules** — root `CLAUDE.md` (≤ 70 lines, always loaded).
- **Directory rules** — per-directory `CLAUDE.md`, scoped to a subtree.
- **Cross-cutting rules** — `.harness/*.md` with `applies_to` glob patterns.
- **Generated rules** — `.harness/generated/*.json`, code-derived structured truth.
- **Loader** — `tools/load_harness.py`, deterministic discovery + precedence resolver.
- **Validate-fast** — `make validate-fast`, < 30s inner-loop gate.
- **Validate-full** — `make validate-full`, pre-commit / CI gate.
- **Check** — script in `.harness/checks/*.py`, detects violations of one rule, emits structured output.
- **Generator** — script in `.harness/generators/*.py`, produces a `.harness/generated/*.json` truth file.
- **Violation/compliant fixture** — paired example files under `tests/harness/fixtures/` proving each check fires correctly.
- **Front-matter** — YAML block at the top of every rule file declaring `scope, owner, priority, applies_to, type`.
- **Precedence** — Local > Generated > Cross-cutting > Root. Conflicts surface as lint errors.
- **Five execution contexts** — AI session loop, terminal, pre-commit, CI, autonomous agent. Same `make validate` runs in all five.
- **Hard gate** — failure blocks merge.
- **Soft gate** — failure reported, doesn't block merge.
- **Baseline** — `.harness/baselines/*.json`, snapshot of pre-existing typecheck violations grandfathered under Q19's "no new errors" mode.
- **Spine path** — code path under stricter rules (whitelist deps, mypy strict, ≥ 90% coverage where applicable).
- **ADR** — Architecture Decision Record at `docs/decisions/YYYY-MM-DD-<slug>.md`. Required for harness-rule changes, spine-dep additions, contract changes (Q15).

---

**Plan finalized 2026-04-26.** This document is the authoritative source. Per the brainstorming-skill terminal flow: invoke `superpowers:writing-plans` if a deeper-than-story-level work-breakdown is needed before execution begins.
